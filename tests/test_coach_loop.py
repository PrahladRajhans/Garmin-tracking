from datetime import date, timedelta

import pytest

from garmin_mcp import coach_loop, dashboard, db, route_review
from garmin_mcp.normalize import rebuild


def test_checkins_merge_and_knee_pause_applies_only_next_day(conn):
    coach_loop.save_checkin(conn, "2026-11-21", rested=4)
    coach_loop.save_checkin(conn, "2026-11-21", knee=4, energy=6)
    assert tuple(conn.execute("SELECT rested,energy,knee FROM coach_checkin").fetchone()) == (4, 6, 4)
    assert coach_loop.knee_pause(conn, "2026-11-22")
    assert not coach_loop.knee_pause(conn, "2026-11-23")
    with pytest.raises(ValueError):
        coach_loop.save_checkin(conn, "2026-11-21", rested=6)


def test_sessions_match_once_move_and_cap_adaptation(conn):
    rebuild(conn)
    conn.execute("INSERT INTO daily(day,steps) VALUES ('2026-11-23',8000)")
    first = coach_loop.save_session(conn, "2026-11-19", "run", 40)
    other = coach_loop.save_session(conn, "2026-11-19", "run", 25)
    db.upsert_activity(conn, {"activityId": 7, "activityType": {"typeKey": "running"},
                             "startTimeLocal": "2026-11-19 08:00:00", "duration": 1800})
    data = coach_loop.week(conn, "2026-11-23")
    assert [row["status"] for row in data["previous"]] == ["not recorded", "done"]
    assert "33 running minutes" in data["adaptive"]
    coach_loop.save_session(conn, "2026-11-24", "walk", 20, session_id=other["id"])
    assert coach_loop.week(conn, "2026-11-23")["sessions"][0]["kind"] == "walk"
    coach_loop.save_session(conn, "2026-11-19", "run", 40, "skipped", first["id"])
    assert "Repeat" in coach_loop.week(conn, "2026-11-23")["adaptive"]
    conn.execute("INSERT INTO meta VALUES ('sync_retry_required','1')")
    assert coach_loop.week(conn, "2026-11-23")["adaptive"] is None


def test_wake_followup_uses_a_fixed_comparison_and_links_existing_dates():
    end = date(2026, 11, 23)
    nights = {}
    for i in range(21, 0, -1):
        nights[(end - timedelta(days=i)).isoformat()] = {
            "wake": 540 if i <= 7 else 500 if i % 2 else 580,
            "hours": 7 if i <= 7 else 6.5,
        }
    result = coach_loop.wake_followup(nights, end.isoformat())
    assert result["hits"] == 7 and result["prior_hits"] == 0
    assert result["sleep_change"] == 30
    html = dashboard._wake_followup(result, {"detail_days": ["2026-11-16"]})
    assert "#day-2026-11-16" in html and "#day-2026-11-17" not in html


def test_route_replay_only_compares_aligned_recorded_traces():
    earlier = [(m, 19, 72 + m / 100_000, m * .3) for m in range(0, 3051, 10)]
    current = [(m, lat, lon, m * .31) for m, lat, lon, _ in earlier]
    rows = route_review.match(current, earlier)
    assert len(rows) == 3 and rows[0]["difference"] == 10
    assert not route_review.match(current, [(m, lat + .001, lon, t) for m, lat, lon, t in earlier])


def test_sunday_story_requires_coverage_and_includes_the_existing_plan():
    data = {"end": "2026-11-22", "weekly_review": {"week": {"sessions": 3}},
            "sleep_review": {"windows": {7: {"hours": 7, "nights": 5}}, "week_change_min": 20},
            "brief": {"week_ahead": {"plan": "Plan an easy run."}}}
    html = dashboard._sunday_story(data)
    assert "20 min more" in html and "Plan an easy run." in html
    data["end"] = "2026-11-23"
    assert not dashboard._sunday_story(data)
