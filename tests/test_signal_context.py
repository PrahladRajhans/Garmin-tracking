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


def test_history_preserves_missing_dates_and_uses_local_quarter_hour(conn):
    rebuild(conn)
    conn.execute("INSERT INTO daily(day,steps) VALUES ('2026-11-22',0), ('2025-11-01',50),"
                 "('2026-11-24',999)")
    early = int(datetime(2026, 11, 21, 19, tzinfo=UTC).timestamp()) * 1000
    outside = int(datetime(2026, 11, 22, 19, tzinfo=UTC).timestamp()) * 1000
    db.put_daily(conn, "pa_heart_rate", "2026-11-22", "personal_api",
                 {"heartRateValues": [[early, 60], [early + 1000, 80], [early, 100],
                                      [early + 2_700_000, 90], [outside, 99]]})
    history = dashboard_history.collect(conn, "2026-11-23", ZoneInfo("Asia/Kolkata"))
    assert history["week"] == ["2026-11-22"]
    assert history["days"]["2026-11-22"]["daily"]["steps"] == 0
    pulse = history["days"]["2026-11-22"]["intraday_hr"]
    assert pulse["samples"] == 3
    assert [(s["time"], s["median"], s["range"], s["count"]) for s in pulse["slots"]] == [
        ("00:30", 70, (60, 80), 2), ("01:15", 90, (90, 90), 1)]
    assert history["months"][0]["month"] == "2025-11"
    assert "2026-11-24" not in history["days"]


def test_resting_check_uses_dated_source_and_prior_days_only(conn):
    end = date(2026, 11, 23)
    for offset in range(1, 17):
        day = (end - timedelta(days=offset)).isoformat()
        db.put_daily(conn, "ex_daily_summary", day, "export",
                     {"calendarDate": day, "currentDayRestingHeartRate": 53, "totalSteps": 8000})
    day = end.isoformat()
    db.put_daily(conn, "ex_daily_summary", day, "export",
                 {"calendarDate": day, "restingHeartRate": 60})
    db.put_daily(conn, "pa_daily_summary", day, "personal_api",
                 {"calendarDate": day, "heartRate": {"restingValue": 44}})
    future = (end + timedelta(days=1)).isoformat()
    db.put_daily(conn, "ex_daily_summary", future, "export",
                 {"calendarDate": future, "restingHeartRate": 19, "totalSteps": 12})
    rebuild(conn)
    check = dashboard_history.collect(conn, day, UTC)["days"][day]["resting_pulse_check"]
    coverage = check.pop("coverage")
    assert coverage["Full archive"]["count"] == 16
    assert coverage["28 days"]["missing"] == 12
    assert coverage["90 days"]["last"] == "2026-11-22"
    assert check == {"value": 44, "median": 53, "range": (48, 58), "count": 16,
                     "direction": "lower", "verify": True, "sources": {"pa_daily_summary": 44}}
    assert conn.execute("SELECT resting_hr FROM daily WHERE day=?", (future,)).fetchone()[0] is None


def test_full_archive_baseline_includes_older_history_and_exact_sparse_gaps(conn):
    end = "2026-11-25"
    rebuild(conn)
    start = date(2023, 11, 25)
    conn.executemany("INSERT INTO daily(day,steps) VALUES (?,?)",
                     [((start + timedelta(days=index)).isoformat(), 4000 + index)
                      for index in range(1097)])
    conn.execute("UPDATE daily SET resting_hr=46 WHERE day IN ('2026-11-22','2026-11-24','2026-11-25')")
    conn.execute("UPDATE daily SET resting_hr='invalid' WHERE day='2025-01-01'")
    conn.execute("INSERT INTO sleep(day, sleep_s, score) VALUES ('2025-01-01','invalid','invalid')")
    coverage = dashboard_history.collect(conn, end, UTC)["baseline_coverage"]
    assert coverage["steps"]["28 days"]["count"] == 28
    assert coverage["steps"]["90 days"]["count"] == 90
    assert coverage["steps"]["Full archive"]["count"] == 1096
    assert coverage["steps"]["Full archive"]["first"] == "2023-11-25"
    assert coverage["steps"]["Full archive"]["last"] == "2026-11-24"
    pulse = coverage["resting_hr"]["28 days"]
    assert pulse["typical"] is None and pulse["count"] == 2
    assert pulse["sparse_gaps"] == [("2026-10-28", "2026-11-21"), ("2026-11-23", "2026-11-23")]
    assert coverage["resting_hr"]["Full archive"]["count"] == 2
    assert coverage["sleep_h"]["Full archive"]["count"] == 0
