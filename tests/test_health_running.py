import sqlite3

from garmin_mcp import health, running


def test_detect_shift_finds_step():
    series = [(f"2026-01-{i:02d}", 50.0 + (i % 3) * 0.5) for i in range(1, 29)]
    series += [(f"2026-02-{i:02d}", 45.0 + (i % 3) * 0.5) for i in range(1, 29)]
    s = health.detect_shift(series)
    assert s and s["date"] == "2026-02-01" and s["change"] < -4


def test_detect_shift_ignores_noise():
    series = [(str(i), 50.0 + (1 if i % 2 else -1)) for i in range(60)]
    assert health.detect_shift(series) is None


def test_gauges_match_garmin_bands():
    assert running.rate("cadence_spm", 150)["colour"] == "red"
    assert running.rate("cadence_spm", 168)["colour"] == "green"
    assert running.rate("cadence_spm", 184)["colour"] == "purple"
    assert running.rate("ground_contact_ms", 273)["colour"] == "green"
    assert running.rate("vertical_ratio_pct", 8.73)["colour"] == "orange"
    assert running.rate("vertical_ratio_pct", 6.0)["colour"] == "purple"


def test_personal_line_fit():
    hist = [{"avg_speed": s, "cadence_spm": 120 + 15 * s} for s in (2.5, 2.8, 3.0, 3.2, 3.5)]
    ln = running.personal_lines(hist)["cadence_spm"]
    assert abs(ln["slope_per_ms"] - 15) < 1e-6 and abs(ln["intercept"] - 120) < 1e-6


def test_pace_of_ageing_needs_span():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE fitness_age (day TEXT, fitness_age REAL, chronological_age REAL)")
    for i in range(1, 31):
        c.execute("INSERT INTO fitness_age VALUES (?,?,29)", (f"2026-11-{i:02d}", 25 + i / 100))
    assert health.pace_of_ageing(c, "2026-11-30")["available"] is False


def test_suggestions_target_cadence():
    form = {"cadence_spm": {"value": 160.0}}
    out = running.suggestions({}, form, None)
    assert "168 spm" in out[0]


def test_status_tag_pauses_advice_and_leaves_baseline(conn):
    from garmin_mcp import athlete, recovery

    athlete.add_note(conn, "tag", "2026-11-10|sick")
    assert health.status_days(conn) == {"2026-11-10": "sick"}
    from garmin_mcp.normalize import rebuild

    rebuild(conn)
    for d in ("2026-11-09", "2026-11-10", "2026-11-11"):
        conn.execute("INSERT OR REPLACE INTO daily (day, resting_hr) VALUES (?, 50)", (d,))
    s = recovery.load_series(conn, "2026-11-12", 10)
    assert "2026-11-10" not in s["rhr"] and "2026-11-09" in s["rhr"]
    r = {"garmin": None, "ours": {"state": "normal"}, "illness_flag": {"raised": False},
         "activity_status": "sick"}
    assert recovery.suggestion(r)["suggest"] == "training advice paused"


def test_test_runs_empty_db(conn):
    from garmin_mcp.normalize import rebuild

    rebuild(conn)
    assert running.test_runs(conn)["available"] is False
    assert running._is_test("FR955 Calibration run") and not running._is_test("Easy run")


def test_pair_points_lag():
    from garmin_mcp import engine

    feat = {f"2026-01-{i:02d}": {"a": float(i % 5), "b": float((i - 1) % 5)}
            for i in range(1, 29)}
    pts = engine.pair_points(feat, "a", "b", lag=1)
    assert pts and all(len(p) == 3 for p in pts)
    assert engine._pearson([p[1] for p in pts], [p[2] for p in pts]) > 0.9


def test_scatter_shows_units_and_lagged_measurement_dates():
    from garmin_mcp import dashboard

    svg = dashboard.scatter([("2026-01-01", -1.0, -2.0), ("2026-01-02", 0.0, 0.0),
                             ("2026-01-03", 1.0, 2.0)], "x", "y", 2.0,
                            x_unit="h", y_unit="ms", lag=1)
    assert svg.count('class="pt"') == 3 and 'class="fit"' in svg
    assert "x (h)" in svg and "y (ms)" in svg and "2026-01-04" in svg


def test_monthly_report_combines_hrv_once_per_night_and_shows_coverage(conn):
    from garmin_mcp.normalize import rebuild

    rebuild(conn)
    conn.execute("INSERT INTO hrv(day,last_night_avg) VALUES ('2024-02-01',60), ('2024-02-03',80)")
    conn.execute("INSERT INTO health_status(day,hrv) VALUES "
                 "('2024-02-01',20), ('2024-02-02',40), ('2024-01-31',30)")
    conn.execute("INSERT INTO sleep(day,sleep_s) VALUES ('2024-02-01',28800), ('2024-02-02',3600)")
    report = health.monthly_report(conn, "2024-02")
    assert report["this_month"]["avg_hrv"] == 60
    assert report["previous_month"]["avg_hrv"] == 30 and report["change"]["avg_hrv"] == 30
    assert report["coverage"]["this_month"]["hrv_nights"] == 3
    assert report["coverage"]["this_month"]["sleep_nights"] == 1
    assert report["coverage"]["this_month"]["calendar_days"] == 29
    history = health.monthly_history(conn, "2024-02", 3)
    assert [m["month"] for m in history] == ["2023-12", "2024-01", "2024-02"]
    assert history[0]["values"]["avg_hrv"] is None


def test_heart_rate_difference_uses_utc_and_has_no_health_cutoff(conn, monkeypatch):
    import time
    from datetime import UTC, datetime

    import pytest

    from garmin_mcp import db
    from garmin_mcp.normalize import rebuild

    if not hasattr(time, "tzset"):
        pytest.skip("host timezone test requires tzset")
    rebuild(conn)
    conn.execute("INSERT INTO sleep(day,sleep_start,sleep_end,sleep_s,avg_hr) VALUES "
                 "('2026-11-21','2026-11-20 20:00:00','2026-11-21 04:00:00',28800,50)")
    conn.execute("INSERT INTO sleep(day,sleep_start,sleep_end,sleep_s,avg_hr) VALUES "
                 "('2026-11-20','2026-11-20 03:00:00','2026-11-20 07:00:00',14400,50)")
    samples = []
    for hour, minute, hr in ((18, 0, 80), (19, 15, 120), (19, 45, 160), (12, 0, -1), (6, 0, 20)):
        ts = datetime(2026, 11, 20, hour, minute, tzinfo=UTC).timestamp() * 1000
        samples.extend([[ts + i * 1000, hr] for i in range(60)])
    db.put_daily(conn, "pa_heart_rate", "2026-11-20", "personal_api", {"heartRateValues": samples})
    results = []
    try:
        with monkeypatch.context() as m:
            for tz in ("UTC", "Asia/Kolkata"):
                m.setenv("TZ", tz)
                time.tzset()
                results.append(health.heart_rate_dip(conn, "2026-11-21"))
    finally:
        time.tzset()
    assert results[0] == results[1]
    assert results[0]["awake_mean_hr"] == 100 and results[0]["dip_pct"] == 50
    assert results[0]["label"] == "lower in sleep" and "not a recovery diagnosis" in results[0]["meaning"]


def test_run_drift_does_not_claim_a_single_cause():
    text = " ".join(running.suggestions({"decoupling_pct": 8.}, {}, None))
    assert "Heat" in text and "noise" in text and "is the limiter" not in text
