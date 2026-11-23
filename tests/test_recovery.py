import math
from datetime import date, timedelta

from garmin_mcp import recovery
from garmin_mcp.normalize import TABLES

END = date(2026, 11, 20)


def _make(conn, days=70, sick_last=0):
    for t, cols in TABLES.items():
        conn.execute(f"DROP TABLE IF EXISTS {t}")
        conn.execute(f"CREATE TABLE {t} (day TEXT PRIMARY KEY, {', '.join(cols)}, sources TEXT)")
    for i in range(days):
        d = (END - timedelta(days=days - 1 - i)).isoformat()
        sick = i >= days - sick_last
        wobble = (i % 5) - 2  # deterministic day-to-day variation
        conn.execute("INSERT INTO hrv(day, last_night_avg) VALUES (?, ?)",
                     (d, 35.0 if sick else 50.0 + wobble))
        conn.execute("INSERT INTO daily(day, resting_hr) VALUES (?, ?)",
                     (d, 56.0 if sick else 46.0 + wobble * 0.5))
        conn.execute("INSERT INTO sleep(day, sleep_s, avg_respiration, sleep_need_min) "
                     "VALUES (?, ?, ?, 480)",
                     (d, 7 * 3600 + wobble * 600, 18.0 if sick else 14.0 + wobble * 0.2))
    conn.commit()


def test_calibrating_with_short_history(conn):
    _make(conn, days=10)
    r = recovery.readiness(conn, END.isoformat())
    assert r["hrv"]["state"] == "calibrating"


def test_hrv_band_is_baseline_plus_minus_half_sd(conn):
    _make(conn)
    h = recovery.readiness(conn, END.isoformat())["hrv"]
    assert h["state"] == "within normal"
    lo, hi = h["normal_band_ln"]
    vals = [math.log(50.0 + (i % 5) - 2) for i in range(70)][-60:]
    import statistics
    m, sd = statistics.fmean(vals), statistics.stdev(vals)
    assert abs(lo - (m - 0.5 * sd)) < 1e-3 and abs(hi - (m + 0.5 * sd)) < 1e-3


def test_illness_flag_and_low_readiness(conn):
    _make(conn, sick_last=3)
    r = recovery.readiness(conn, END.isoformat())
    assert r["illness_flag"]["raised"] is True
    assert r["ours"]["state"] in ("below usual", "well below usual")
    assert recovery.suggestion(r)["suggest"].startswith("rest")


def test_incomplete_night_excluded(conn):
    _make(conn)
    conn.execute("UPDATE sleep SET sleep_s=840 WHERE day=?", (END.isoformat(),))
    s = recovery.readiness(conn, END.isoformat())["sleep"]
    assert s["last_night_h"] is None and END.isoformat() in s["incomplete_records_7d"]


def test_sleep_fallback_is_shared_and_debt_inputs_are_traceable(conn):
    from garmin_mcp import scores

    _make(conn)
    conn.execute("UPDATE sleep SET sleep_need_min=NULL, sleep_s=7*3600")
    s = scores.daily_scores(conn, END.isoformat())["sleep"]
    r = recovery.readiness(conn, END.isoformat())["sleep"]
    assert s["need_h"] == 8 and s["pct"] == 88 and r["debt_7d_h"] == 7
    assert len(r["debt_inputs"]) == 7
    assert all(x["need_h"] == 8 and x["shortfall_h"] == 1 for x in r["debt_inputs"])


def test_short_sleep_baseline_does_not_generate_reassuring_advice(conn):
    _make(conn, days=10)
    r = recovery.readiness(conn, END.isoformat())
    assert r["ours"]["state"] == "calibrating" and r["sleep"]["z"] is None
    assert "not enough recovery data" in recovery.suggestion(r)["suggest"]


def test_resting_hr_baseline_requires_21_prior_values():
    series = {(END - timedelta(days=i)).isoformat(): float(45 + i % 4) for i in range(21)}
    assert recovery._metric_z(series, END.isoformat()) is None
    series[(END - timedelta(days=21)).isoformat()] = 48.
    assert recovery._metric_z(series, END.isoformat()) is not None


def test_recovery_score_and_strain_target_need_three_signals(conn):
    from garmin_mcp import scores

    _make(conn, sick_last=1)
    day = END.isoformat()
    conn.execute("UPDATE sleep SET avg_respiration=NULL WHERE day=?", (day,))
    assert scores.daily_scores(conn, day)["recovery"]["pct"] is not None
    conn.execute("DELETE FROM daily WHERE day=?", (day,))
    s = scores.daily_scores(conn, day)
    assert s["recovery"]["signals_used"] == 2
    assert s["recovery"]["calibrating"] and s["recovery"]["pct"] is None
    assert s["recovery"]["band"] is None and s["strain"]["target_range"] is None
    assert "not enough recovery data" in recovery.suggestion(recovery.readiness(conn, day))["suggest"]
