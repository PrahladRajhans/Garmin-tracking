from datetime import date, timedelta

from garmin_mcp import athlete, coaching, goals


def _seed_runs(conn, n=6):
    d0 = date(2026, 10, 1)
    for k in range(n):
        aid = 500 + k
        day = (d0 + timedelta(days=3 * k)).isoformat()
        conn.execute("INSERT INTO activities(activity_id, type, start_time_local, distance_m, "
                     "duration_s, avg_hr, fit_parsed, updated_at) VALUES (?, 'running', ?, 5040,"
                     " 1800, 150, 1, 'x')", (aid, f"{day} 07:00:00"))
        for s in range(1800):
            hr = 145 if s < 900 else 155  # drift in second half
            conn.execute(
                "INSERT INTO fit_records(activity_id, ts, heart_rate, speed, distance, altitude, "
                "cadence, step_length, stance_time, vertical_oscillation, power, temperature) "
                "VALUES (?, ?, ?, 2.8, ?, 10, 82, 1020, 270, 90, 300, ?)",
                (aid, f"{day}T07:{s // 60:02d}:{s % 60:02d}", hr, 2.8 * s, 20 + k))
    conn.commit()


def test_run_metrics_units_and_decoupling(conn):
    _seed_runs(conn, 1)
    m = coaching.run_metrics(conn, 500)
    assert m["steady"] is True
    assert m["cadence_spm"] == 164.0  # one-foot 82 x 2
    assert m["step_length_m"] == 1.02 and m["vertical_oscillation_cm"] == 9.0
    assert m["vertical_ratio_pct"] == round(90 / 1020 * 100, 2)
    # EF halves: 2.8*60/145 vs 2.8*60/155 -> decoupling = 1 - 145/155
    assert abs(m["decoupling_pct"] - (1 - 145 / 155) * 100) < 0.3
    assert m["hr_drift_bpm"] == 10.0


def test_run_analysis_matched_pace_and_glossary(conn):
    _seed_runs(conn, 6)
    r = coaching.run_analysis(conn, 505)
    assert r["compared_with_your_norm_at_matched_pace"]["cadence_spm"]["diff"] == 0
    assert "runs within" in r["norm_basis"]
    assert any("decoupling" in f.lower() for f in r["facts_for_recap"])
    assert set(coaching.GLOSSARY) >= {"cadence", "vertical_ratio", "aerobic_decoupling", "swolf"}


def test_athlete_placeholders_and_goal(conn):
    ctx = athlete.context(conn)
    assert any(q["key"] == "hr_max_override" for q in ctx["open_questions"])
    assert goals.goal_check(conn)["needs_input"] is True
    athlete.set_value(conn, "hr_max_override", 198)
    assert athlete.get(conn, "hr_max_override") == 198
    assert all(q["key"] != "hr_max_override" for q in athlete.context(conn)["open_questions"])
    assert goals._parse_time("1:45:00") == 6300 and goals._parse_time("50:00") == 3000
    assert round(athlete.pace_to_speed("5:00"), 3) == 3.333
def test_invalid_athlete_overrides_are_rejected():
    from garmin_mcp import athlete

    for value in (0, -1, float("nan"), float("inf"), "not a number"):
        assert athlete.validate_setting("hr_max_override", value)
    for pace in ("0:00", "5:99", "-1:30", "bad"):
        assert athlete.pace_to_speed(pace) is None
        assert athlete.validate_setting("threshold_pace_override", pace)
    assert athlete.validate_setting("timezone", "Not/A_Timezone")
    assert athlete.validate_setting("timezone", "Asia/Kolkata") is None
    assert athlete.validate_setting("hr_max_override", 188) is None
    assert athlete.validate_setting("weekly_run_km_target", 0) is None
