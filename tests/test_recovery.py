import math
from datetime import UTC, date, timedelta

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


def test_hrv_variability_is_missing_with_zero_log_mean(conn):
    _make(conn)
    conn.execute("UPDATE hrv SET last_night_avg=1")
    h = recovery.readiness(conn, END.isoformat())["hrv"]
    assert h["cv_7d_pct"] is None


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


def test_readiness_picks_usable_fallbacks_and_preserves_zero_recovery_time(conn):
    _make(conn)
    day = END.isoformat()
    conn.execute("UPDATE sleep SET avg_respiration=-1 WHERE day=?", (day,))
    conn.execute("UPDATE daily SET resting_hr=0 WHERE day=?", (day,))
    conn.execute("UPDATE hrv SET last_night_avg=? WHERE day=?", (float("inf"), day))
    conn.execute("INSERT INTO health_status(day,respiration,hrv) VALUES (?,16,50)", (day,))
    conn.execute("INSERT INTO readiness(day,score,recovery_time_min) VALUES (?,0,0)", (day,))
    values = recovery.load_series(conn, day, 14)
    assert values["resp"][day] == 16 and values["hrv"][day] == 50
    assert day not in values["rhr"]
    result = recovery.readiness(conn, day)
    assert result["garmin"]["score"] == result["garmin"]["recovery_time_h"] == 0
    assert result["ours"]["signals_used"] == 3


def test_bedtime_consistency_uses_circular_local_time_and_ignores_invalid_start(conn, monkeypatch):
    from garmin_mcp import engine

    _make(conn)
    monkeypatch.setattr(engine, "_tz", lambda _: UTC)
    clocks = ("11:55:00Z", "11:56:00+00:00", "12:04:00Z", "12:06:00Z", "17:30:00+05:30", "?")
    for i, clock in enumerate(clocks):
        day = (END - timedelta(days=i)).isoformat()
        conn.execute("UPDATE sleep SET sleep_start=?, sleep_s=10800 WHERE day=?", (f"{day}T{clock}", day))
    without_time = (END - timedelta(days=len(clocks))).isoformat()
    conn.execute("UPDATE sleep SET sleep_start=?, sleep_s=10800 WHERE day=?", (without_time, without_time))
    assert recovery.bedtime_consistency(conn, END.isoformat()) == 5


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



def test_high_readiness_does_not_add_a_hard_session():
    r = {"ours": {"state": "fresher than usual"}, "garmin": {"level": "HIGH"},
         "illness_flag": {"raised": False}}
    assert recovery.suggestion(r)["suggest"] == "follow your planned session if you feel well"


def test_focus_detects_consistently_short_sleep_and_paired_changes():
    from garmin_mcp.daily_focus import daily_focus

    night = {"sleep_h": 6.2, "need_h": 8.0, "source": "8 h planning fallback"}
    r = {"ours": {"state": "normal"}, "hrv": {"state": "within normal"},
         "sleep": {"debt_inputs": [night] * 5}, "illness_flag": {"raised": False},
         "garmin": {"level": "MODERATE"}}
    signals = {"resting_hr": {"delta": 5, "state": "above"}, "sleep_spo2": {},
               "sleep_h": {"delta": 0, "state": "within"}}
    pair = {"x": "sleep_h", "y": "garmin_readiness", "notable": True, "lag_days": 0,
            "slope": 5.8, "n": 21}
    out = daily_focus(r, signals, {}, training_status="DETRAINING", running_km=4.6, patterns=[pair])
    assert out["title"] == "Follow your planned effort if you feel well."
    sleep, training, pulse = out["findings"]
    assert "108 minutes short" in sleep["detail"] and "5 recorded nights" in sleep["basis"]
    assert "6 more points" in sleep["basis"] and "21 paired days" in sleep["basis"]
    assert "4.6 km" in training["detail"] and "5 bpm" in pulse["detail"]
    signals["sleep_h"] = {"delta": -0.75, "state": "below"}
    assert daily_focus(r, signals, {})["title"] == "Keep today’s effort easy."
    r["activity_status"] = "injured"
    assert daily_focus(r, signals, {})["title"] == "Pause training today."


def test_shortfall_uses_dated_targets_and_requires_coverage_for_comparison(conn):
    _make(conn, days=14)
    conn.execute("UPDATE sleep SET sleep_s=7*3600, sleep_need_min=480")
    conn.execute("UPDATE sleep SET sleep_need_min=NULL,sleep_s=9*3600 WHERE day=?", (END.isoformat(),))
    conn.execute("UPDATE sleep SET sleep_s=3600 WHERE day=?", ((END - timedelta(days=1)).isoformat(),))
    conn.execute("UPDATE sleep SET sleep_need_min=435 WHERE day=?", ((END - timedelta(days=2)).isoformat(),))
    review = recovery.sleep_shortfall_review(conn, END.isoformat())
    assert review["current"]["valid_nights_7d"] == 6
    assert (review["total_min"], review["per_night_min"], review["previous_min"]) == (255, 42, 60)
    assert review["target_met"] == review["fallback"] == 1
    conn.execute("DELETE FROM sleep WHERE day <= ?", ((END - timedelta(days=11)).isoformat(),))
    assert recovery.sleep_shortfall_review(conn, END.isoformat())["previous_min"] is None
