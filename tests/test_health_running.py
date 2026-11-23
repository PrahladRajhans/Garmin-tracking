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
