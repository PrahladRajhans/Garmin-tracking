from datetime import UTC

import pytest

from garmin_mcp import scores


def test_strain_calibration_points():
    assert scores.strain_from_trimp(0) == 0
    assert 8.5 <= scores.strain_from_trimp(68) <= 10.5     # easy ~30-min run
    assert 15.5 <= scores.strain_from_trimp(250) <= 17.5   # hard ~2 h
    assert scores.strain_from_trimp(5000) == 21            # capped
    vals = [scores.strain_from_trimp(t) for t in range(0, 900, 25)]
    assert vals == sorted(vals)                            # monotonic


def test_recovery_mapping_and_bands():
    assert scores.phi(0) == pytest.approx(0.5)
    assert round(100 * scores.phi(1)) == 84 and round(100 * scores.phi(-1)) == 16
    assert scores.band(70) == ("green", "recovered")
    assert scores.band(50) == ("yellow", "moderate")
    assert scores.band(20) == ("red", "low")
    assert scores.band(None) == (None, None)


def test_bedtime_uses_14_calendar_dates_and_keeps_explicit_offset(conn, monkeypatch):
    from garmin_mcp import engine
    from garmin_mcp.normalize import rebuild

    rebuild(conn)
    monkeypatch.setattr(engine, "_tz", lambda _: UTC)
    monkeypatch.setattr(scores, "daily_scores", lambda *_: {"sleep": {"need_h": 8, "debt_7d_h": 0}})
    conn.executemany("INSERT INTO sleep(day,sleep_end,sleep_s) VALUES (?,?,25200)",
                     [(f"2026-11-{day:02d}", f"2026-11-{day:02d}T08:30:00+05:30")
                      for day in (1, 11, 12, 13, 15)])
    assert scores.bedtime_suggestion(conn, "2026-11-15")["available"] is False
    conn.execute(
        "INSERT INTO sleep(day,sleep_end,sleep_s) VALUES ('2026-11-14','2026-11-14T08:30:00+05:30',25200)",
    )
    assert scores.bedtime_suggestion(conn, "2026-11-15")["usual_wake"] == "03:00"


def test_bedtime_median_of_wakes_around_midnight_stays_at_midnight(conn, monkeypatch):
    from garmin_mcp import engine
    from garmin_mcp.normalize import rebuild

    rebuild(conn)
    monkeypatch.setattr(engine, "_tz", lambda _: UTC)
    monkeypatch.setattr(scores, "daily_scores", lambda *_: {"sleep": {"need_h": 8, "debt_7d_h": 0}})
    times = ("23:50", "23:58", "23:59", "00:00", "00:06", "00:09")
    for day, clock in enumerate(times, 1):
        stamp = f"2026-11-{day:02d}"
        conn.execute("INSERT INTO sleep(day,sleep_end,sleep_s) VALUES (?,?,25200)", (stamp, f"{stamp}T{clock}"))
    result = scores.bedtime_suggestion(conn, "2026-11-07")
    assert result["usual_wake"] == "00:00"
    assert result["suggested_bedtime"] == "16:00"


def test_scores_treat_bad_sleep_need_and_nonfinite_measurements_as_missing(conn):
    from garmin_mcp.normalize import rebuild

    rebuild(conn)
    day = "2026-11-25"
    conn.execute("INSERT INTO sleep(day,sleep_s,sleep_need_min,score) VALUES (?,25200,'bad',101)", (day,))
    result = scores.daily_scores(conn, day)
    assert (result["sleep"]["pct"], result["sleep"]["need_h"], result["sleep"]["garmin_sleep_score"]) == (88, 8, None)
    conn.execute("UPDATE sleep SET sleep_s=? WHERE day=?", (float("inf"), day))
    result = scores.daily_scores(conn, day)["sleep"]
    assert result["hours"] is None and result["incomplete"] is False


def test_zero_correlation_is_not_treated_as_missing():
    base = {"hrv": {"r": 0.0}, "garmin": {"r": 0.0}}
    assert not scores._beats_on_both({"hrv": {"r": -0.1}, "garmin": {"r": -0.1}}, base)
    assert scores._beats_on_both({"hrv": {"r": 0.1}, "garmin": {"r": 0.1}}, base)
    assert not scores._beats_on_both({"hrv": {"r": None}, "garmin": {"r": 0.2}}, base)


def test_weight_study_keeps_hrv_only_days_and_matches_comparison_days(conn, monkeypatch):
    from datetime import date, timedelta

    from garmin_mcp import recovery
    from garmin_mcp.normalize import rebuild

    rebuild(conn)
    start = date(2026, 1, 1)
    names = ["HRV (7-day vs normal)", "Resting HR (today vs 60-day)",
             "Sleep (last night vs 28-day)", "Respiration (last night vs 60-day)"]
    for i in range(90):
        day = (start + timedelta(days=i)).isoformat()
        conn.execute("INSERT INTO hrv(day,last_night_avg) VALUES (?,?)", (day, 50 + i % 7))
        conn.execute("INSERT INTO readiness(day,score) VALUES (?,?)", (day, 60 + i % 11))

    def readiness(c, day):
        i = (date.fromisoformat(day) - start).days
        return {"ours": {"components": [{"name": n, "contribution": None if i % 5 == 0
                                           and j == 0 else float((i + j) % 7)}
                                          for j, n in enumerate(names)]}}

    monkeypatch.setattr(recovery, "readiness", readiness)
    report = scores.weight_study(conn, (start + timedelta(days=89)).isoformat(), 60)
    comp = report["composites"]
    assert comp["equal weights (current)"]["next_night_hrv"]["n"] >= 30
    for outcome in ("next_night_hrv", "garmin_readiness"):
        assert {v[outcome]["n"] for v in comp.values()} == {48}
