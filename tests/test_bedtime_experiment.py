import pytest

from garmin_mcp import bedtime_experiment, dashboard
from garmin_mcp.normalize import rebuild


def test_saved_target_rejects_nonstandard_and_missing_clock_values(conn):
    for target in (None, "T1234", "24:00", "5:15"):
        with pytest.raises(ValueError):
            bedtime_experiment.accept(conn, "2026-11-17", target)
    assert conn.execute("SELECT COUNT(*) FROM bedtime_targets").fetchone()[0] == 0


def test_saved_week_keeps_target_and_steps_back_after_most_misses(conn):
    rebuild(conn)
    bedtime_experiment.accept(conn, "2026-11-17", "00:30")
    bedtime_experiment.accept(conn, "2026-11-18", "00:30")
    with pytest.raises(ValueError, match="already saved"):
        bedtime_experiment.accept(conn, "2026-11-18", "00:15")
    assert conn.execute("SELECT COUNT(*) FROM bedtime_targets").fetchone()[0] == 1
    nights = {f"2026-11-{day}": {"bed": 15 if day < 19 else 80, "hours": 7, "score": 70}
              for day in range(16, 23)}
    nights["2026-11-24"] = {"bed": 10, "hours": 7, "score": 80}
    review = {"nights": nights, "anchor": {"wake": "08:00", "bedtime": "00:10"}}
    result = bedtime_experiment.status(conn, "2026-11-23", review, 8)
    assert result["suggestion"] == "00:45"
    assert result["previous"]["on_time"] == 3 and result["previous"]["recorded"] == 7
    assert result["previous"]["comparisons"]["hours"]["later_n"] == 4
    assert "hrv_ms" not in result["previous"]["comparisons"]
    assert result["current"] is None


def test_missing_recordings_do_not_shift_saved_target(conn):
    rebuild(conn)
    bedtime_experiment.accept(conn, "2026-11-16", "23:50")
    review = {"nights": {}, "anchor": {"wake": "08:00"}}
    result = bedtime_experiment.status(conn, "2026-11-25", review, 8)
    assert result["suggestion"] == "23:50"


def test_saved_target_renders_with_and_without_recorded_nights(conn, monkeypatch):
    monkeypatch.setenv("GARMIN_TZ", "UTC")
    rebuild(conn)
    day = "2026-11-24"
    conn.execute("INSERT INTO daily(day,steps) VALUES (?,8000)", (day,))
    bedtime_experiment.accept(conn, day, "00:00")
    html = dashboard.render(dashboard.collect(conn, day))
    assert "This week’s target" in html and "0 of 0 timed nights" in html

    conn.execute("INSERT INTO sleep(day,sleep_s,sleep_start,sleep_end) VALUES (?,25200,?,?)",
                 (day, "2026-11-23 23:30:00", "2026-11-24 06:30:00"))
    html = dashboard.render(dashboard.collect(conn, day))
    assert "This week’s target" in html and "1 of 1 timed nights" in html
    assert "Recent nights" in html or "Past week" in html
    assert f'href="#day-{day}"' in html
