"""Clock times follow the watch on days recorded away from the configured timezone. Invented values."""

from zoneinfo import ZoneInfo

from garmin_mcp import db, engine, sleep_review, wellness_timeline
from garmin_mcp.normalize import rebuild

HOME = ZoneInfo("Asia/Kolkata")
DAY = "2026-06-10"


def _away_day(conn):
    """One day on a watch set to UTC+1: asleep 23:30 to 07:00, a run ending 18:00."""
    rebuild(conn)
    db.put_daily(conn, "ex_daily_summary", DAY, "export", {
        "calendarDate": DAY, "wellnessStartTimeGmt": "2026-06-09T23:00:00.0",
        "wellnessStartTimeLocal": "2026-06-10T00:00:00.0"})
    conn.execute("INSERT INTO sleep(day, sleep_start, sleep_end, sleep_s) VALUES (?,?,?,?)",
                 (DAY, "2026-06-09 22:30:00", "2026-06-10 06:00:00", 7.5 * 3600))
    db.upsert_activity(conn, {"activityId": 1, "activityType": {"typeKey": "running"}, "duration": 3600,
                              "startTimeLocal": f"{DAY} 17:00:00", "startTimeGMT": f"{DAY} 16:00:00"})
    conn.commit()


def test_stored_days_report_the_watch_offset(conn):
    _away_day(conn)
    zones = wellness_timeline.day_zones(conn, HOME)
    assert zones[DAY].utcoffset(None).total_seconds() == 3600


def test_bedtime_and_training_end_use_the_watch_clock(conn, monkeypatch):
    monkeypatch.setenv("GARMIN_TZ", "Asia/Kolkata")
    _away_day(conn)
    row = engine.features(conn, DAY, DAY)[DAY]
    assert row["bedtime_h"] == 23.5
    assert row["last_training_end_h"] == 18.0


def test_sleep_review_shows_the_watch_clock(conn):
    _away_day(conn)
    night = sleep_review.collect(conn, DAY, HOME, 8.0)["nights"][DAY]
    assert (night["bed"], night["wake"]) == (23 * 60 + 30, 7 * 60)
