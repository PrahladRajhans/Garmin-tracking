from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from garmin_mcp import dashboard_history, db, signal_context
from garmin_mcp.normalize import rebuild


def test_weekly_signal_excludes_scored_week_and_requires_coverage(conn):
    rebuild(conn)
    end = date(2026, 11, 23)
    for offset in range(67):
        day = (end - timedelta(days=offset)).isoformat()
        if offset >= 3:  # Four usable days in the most recent week.
            rate = 70 if offset < 7 else 59 + 2 * (offset % 2)
            conn.execute("INSERT INTO daily(day,resting_hr) VALUES (?,?)", (day, rate))
        if offset < 3:
            conn.execute("INSERT INTO sleep(day,sleep_s,avg_spo2) VALUES (?,28800,96)", (day,))
    conn.execute("INSERT INTO daily(day,resting_hr) VALUES ('2026-11-24',100)")
    data = signal_context.collect(conn, end.isoformat())
    rhr = data["resting_hr"]
    assert rhr["recent"] == 70 and rhr["recent_count"] == 4 and rhr["state"] == "above"
    assert 9 < rhr["delta"] < 11
    assert rhr["baseline_count"] == 60 and rhr["baseline"][1] < 62
    assert rhr["latest_day"] == "2026-11-20"
    assert data["sleep_spo2"]["recent"] is None and data["sleep_spo2"]["delta"] is None


def test_history_preserves_missing_dates_and_uses_local_hour(conn):
    rebuild(conn)
    conn.execute("INSERT INTO daily(day,steps) VALUES ('2026-11-22',0), ('2025-11-01',50),"
                 "('2026-11-24',999)")
    early = int(datetime(2026, 11, 21, 19, tzinfo=UTC).timestamp()) * 1000
    outside = int(datetime(2026, 11, 22, 19, tzinfo=UTC).timestamp()) * 1000
    db.put_daily(conn, "pa_heart_rate", "2026-11-22", "personal_api",
                 {"heartRateValues": [[early, 60], [early + 1000, 80], [outside, 99]]})
    history = dashboard_history.collect(conn, "2026-11-23", ZoneInfo("Asia/Kolkata"))
    assert history["week"] == ["2026-11-22"]
    assert history["days"]["2026-11-22"]["daily"]["steps"] == 0
    assert history["days"]["2026-11-22"]["hourly_hr"] == [("00:00", 70)]
    assert history["months"][0]["month"] == "2025-11"
    assert "2026-11-24" not in history["days"]
