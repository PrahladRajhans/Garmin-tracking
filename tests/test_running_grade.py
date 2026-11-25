from datetime import UTC, datetime, timedelta

import pytest

from garmin_mcp import coaching, grade, loads, running

SPEED_M_S = 1.8


def _save_run(conn, aid, step_s, slope, *, gap=False):
    start = datetime(2026, 10, 1, 7, tzinfo=UTC) + timedelta(days=aid)
    conn.execute(
        "INSERT INTO activities(activity_id,type,start_time_local,fit_parsed,updated_at) "
        "VALUES (?,'running',?,1,'x')",
        (aid, start.isoformat()),
    )
    records = []
    for seconds in range(0, 1801, step_s):
        if gap and 800 < seconds < 1000:
            continue
        after_gap = gap and seconds >= 1000
        distance = SPEED_M_S * (seconds - (200 if after_gap else 0))
        # A recording gap may be followed by an elevation datum change.
        altitude = 70 + slope * distance + (100 if after_gap else 0)
        cadence = 80 if seconds <= 900 else 83
        records.append((aid, (start + timedelta(seconds=seconds)).isoformat(),
                        SPEED_M_S, distance, altitude, cadence))
    conn.executemany(
        "INSERT INTO fit_records(activity_id,ts,speed,distance,altitude,cadence,heart_rate) "
        "VALUES (?,?,?,?,?,?,150)",
        records,
    )


@pytest.mark.parametrize("slope", [0.0, 0.05, -0.05])
@pytest.mark.parametrize("gap", [False, True])
def test_slow_run_grade_and_late_form_match_across_fit_recording_rates(conn, slope, gap):
    _save_run(conn, 1, 1, slope, gap=gap)
    _save_run(conn, 2, 5, slope, gap=gap)
    expected = SPEED_M_S * loads.minetti_cost(slope) / loads.minetti_cost(0)
    expected_duration = 1600 if gap else 1800
    for aid in (1, 2):
        metrics = coaching.run_metrics(conn, aid)
        assert metrics["graded_speed"] == pytest.approx(expected)
        assert metrics["efficiency_factor"] == round(expected * 60 / 150, 3)
        assert metrics["decoupling_pct"] == 0
        assert metrics["moving_s"] == expected_duration
        analysis = running.running_breakdown(conn, aid)
        assert analysis["late_form"]["cadence_spm"] == {
            "early": 160.0, "late": 166.0, "matched_s": expected_duration // 2,
        }


def test_missing_elevation_and_cumulative_distance_reset_break_grade_windows():
    samples = [
        (0, 0, 10), (5, 10, 11), (10, 20, 12),
        (15, 30, None), (20, 40, 30), (25, 45, 31),
        (30, 0, 100), (35, 10, 99), (40, 20, 98), (45, 20, 98),
    ]
    assert grade.interval_grades(samples) == [0.1, 0.1, None, None, None, None, -0.1, -0.1, None]


def test_grade_uses_distance_at_slope_changes_and_stops_on_missing_altitude(conn):
    _save_run(conn, 1, 1, 0.05)
    conn.execute(
        "UPDATE fit_records SET altitude=70 + 0.05 * (3240 - distance) WHERE distance > 1620",
    )
    metrics = coaching.run_metrics(conn, 1)
    assert metrics["decoupling_pct"] > 30
    assert running.running_breakdown(conn, 1)["late_form"] == {}
    conn.execute("UPDATE fit_records SET altitude=NULL")
    metrics = coaching.run_metrics(conn, 1)
    assert metrics["graded_speed"] == pytest.approx(SPEED_M_S)
    assert metrics["decoupling_pct"] == 0
    assert running.running_breakdown(conn, 1)["late_form"] == {}
