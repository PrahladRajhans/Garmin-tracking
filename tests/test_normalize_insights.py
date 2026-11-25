import json
import sqlite3
from datetime import UTC, date, datetime, timedelta

import pytest

from garmin_mcp import db, insights
from garmin_mcp.normalize import rebuild

DAY = "2026-11-20"
EPOCH_MS = int(datetime(2026, 11, 20, tzinfo=UTC).timestamp() * 1000)


def _seed(conn):
    db.put_daily(conn, "pa_daily_summary", DAY, "personal_api", {"data": [{
        "calendarDate": DAY, "movement": {"steps": {"value": 8000}},
        "heartRate": {"restingValue": 46, "minValue": 40, "maxValue": 150},
        "stress": {"avgLevel": -1, "maxLevel": 70},
        "bodyBattery": {"minValue": 20, "maxValue": 90},
        "intensityMinutes": {"moderate": 30, "vigorous": 20}}]})
    db.put_daily(conn, "ex_daily_summary", DAY, "export", {
        "calendarDate": DAY, "totalSteps": 7000, "restingHeartRate": 99,
        "averageSpo2Value": 95, "allDayStress": {"aggregatorList": [{"averageStressLevel": 25}]},
        "bodyBattery": {"bodyBatteryStatList": [{"bodyBatteryStatType": "HIGHEST",
                                                 "statsValue": 88}]}})
    db.put_daily(conn, "ex_sleep", DAY, "export", {
        "calendarDate": DAY, "deepSleepSeconds": 3600, "lightSleepSeconds": 14400,
        "remSleepSeconds": 7200, "awakeSleepSeconds": 600,
        "sleepScores": {"overallScore": 82}, "sleepStartTimestampGMT": "2026-11-19T17:00:00.0"})
    db.put_daily(conn, "ex_training_readiness", DAY, "export", [
        {"calendarDate": DAY, "timestamp": "2026-11-20T02:00:00", "score": 80, "level": "HIGH"},
        {"calendarDate": DAY, "timestamp": "2026-11-20T12:00:00", "score": 60,
         "level": "MODERATE", "recoveryTime": 600}])
    db.put_daily(conn, "ex_race_predictions", DAY, "export", {
        "calendarDate": DAY, "timestamp": "x", "raceTime5K": 1481, "raceTime10K": 3239,
        "raceTimeHalf": 7436, "raceTimeMarathon": 16804})
    db.put_daily(conn, "ex_endurance_score", DAY, "export",
                 {"calendarDate": EPOCH_MS, "overallScore": 5400, "classification": 2})
    db.put_daily(conn, "ex_hill_score", DAY, "export",
                 {"calendarDate": 20261120, "overallScore": 22, "strengthScore": 0,
                  "enduranceScore": 1})
    db.put_range(conn, "pa_hrv_summaries", DAY, DAY, "personal_api", {"hrvSummaries": [{
        "calendarDate": DAY, "lastNightAvg": 53, "weeklyAvg": 51,
        "baseline": {"balancedLow": 49, "balancedUpper": 58}, "status": "BALANCED"}]})
    db.put_daily(conn, "pa_fitness_age", DAY, "personal_api", {
        "fitnessAge": 24.9, "chronologicalAge": 29, "achievableFitnessAge": 21.1,
        "components": {"rhr": {"value": 46}, "bmi": {"value": 23.6}}})
    db.upsert_activity(conn, {"activityId": 1, "activityType": {"typeKey": "running"},
                              "startTimeLocal": f"{DAY} 07:00:00", "duration": 1800.0,
                              "distance": 5000.0})
    conn.commit()


def test_rebuild_merges_sources_by_priority(conn):
    _seed(conn)
    counts = rebuild(conn)
    assert counts["daily"] == 1 and counts["sleep"] == 1 and counts["readiness"] == 1
    d = insights._row(conn, "daily", DAY)
    assert d["steps"] == 8000 and d["resting_hr"] == 46  # Personal API wins over export
    assert d["stress_avg"] == 25  # PA had -1 (no data) -> falls back to export
    assert d["spo2_avg"] == 95 and d["body_battery_max"] == 90
    assert d["sources"] == "personal_api,export"
    s = insights._row(conn, "sleep", DAY)
    assert s["sleep_s"] == 25200 and s["score"] == 82
    r = insights._row(conn, "readiness", DAY)
    assert r["score"] == 60 and r["morning_score"] == 80  # latest vs first of the day
    assert insights._row(conn, "scores", DAY)["endurance_score"] == 5400
    assert insights._row(conn, "scores", DAY)["hill_score"] == 22


@pytest.mark.parametrize("blocked_table", ["daily", "sleep"])
def test_failed_rebuild_preserves_previous_normalized_tables(conn, blocked_table):
    _seed(conn)
    rebuild(conn)
    db.put_daily(conn, "pa_daily_summary", DAY, "personal_api", {
        "calendarDate": DAY, "movement": {"steps": {"value": 9000}},
    })
    conn.commit()

    def deny_insert(action, table, column, database, trigger):
        if action == sqlite3.SQLITE_INSERT and table == blocked_table:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    conn.set_authorizer(deny_insert)
    try:
        with pytest.raises(sqlite3.DatabaseError):
            rebuild(conn)
    finally:
        conn.set_authorizer(None)

    assert not conn.in_transaction
    assert insights._row(conn, "daily", DAY)["steps"] == 8000
    assert insights._row(conn, "sleep", DAY)["sleep_s"] == 25200
    counts = rebuild(conn)
    assert "loads_error" not in counts
    assert insights._row(conn, "daily", DAY)["steps"] == 9000


def test_snapshot_and_flags(conn):
    _seed(conn)
    rebuild(conn)
    snap = insights.health_snapshot(conn, DAY)
    assert snap["sleep"]["hours"] == 7.0
    assert snap["hrv"]["garmin_status"] == "BALANCED"
    assert snap["training"]["garmin_race_predictions"]["5k"] == "24:41"
    assert snap["fitness_age"]["garmin_fitness_age"] == 24.9
    assert snap["recent_activities"]["count"] == 1
    # 30 moderate + 2 x 20 vigorous = 70 < 150 -> flagged
    assert any("Intensity minutes last 7 days: 70" in f for f in snap["flags"])
    nxt = (date.fromisoformat(DAY) + timedelta(days=1)).isoformat()
    snap2 = insights.health_snapshot(conn, nxt)
    assert any("No sleep recorded" in f for f in snap2["flags"])
    assert snap2["sleep"]["night_ending"] == DAY


def test_trend_and_unknown_metric(conn):
    _seed(conn)
    rebuild(conn)
    t = insights.trend(conn, "daily.resting_hr", 7, DAY)
    assert t["points"] == 1 and t["avg"] == 46
    assert "valid_metrics" in insights.trend(conn, "nope.x")


def test_activity_detail(conn):
    _seed(conn)
    out = insights.activity_detail(conn, 1)
    assert out["distance_km"] == 5.0 and out["duration"] == "30:00"
    assert insights.activity_detail(conn, 999) is None
    assert json.dumps(out)


def test_activity_detail_reports_cycling_and_running_cadence_units(conn):
    from garmin_mcp import coaching

    conn.executemany("INSERT INTO activities(activity_id,type,updated_at) VALUES (?,?,'x')",
                     [(1, "running"), (2, "indoor_cycling")])
    conn.executemany("INSERT INTO fit_records(activity_id,ts,cadence) VALUES (?,'2026-11-20T07:00:00Z',90)",
                     [(1,), (2,)])
    conn.executemany("INSERT INTO fit_laps(activity_id,lap_index,avg_cadence) VALUES (?,0,90)", [(1,), (2,)])
    for aid, cadence, unit in ((1, 180, "steps/min"), (2, 90, "rev/min")):
        detail = insights.activity_detail(conn, aid)
        for values in (detail["running_form_from_fit"], detail["laps"][0]):
            assert (values["avg_cadence_spm"], values["cadence_unit"]) == (cadence, unit)
        sampled = coaching.activity_stream(conn, aid)
        assert (sampled["stream"][0]["cadence_spm"], sampled["cadence_unit"]) == (cadence, unit)


def test_fitness_age_as_of_uses_earlier_readings(conn):
    from garmin_mcp import coaching, dashboard

    rebuild(conn)
    db.put_daily(conn, "pa_fitness_age", "2026-11-01", "personal_api", {"fitnessAge": 27})
    db.put_daily(conn, "pa_fitness_age", "2026-11-03", "personal_api", {"fitnessAge": 25})
    conn.executemany("INSERT INTO training(day,vo2max_run) VALUES (?,?)",
                     [("2026-11-01", 48), ("2026-11-03", 51)])
    archived = coaching.fitness_age(conn, "2026-11-02")
    assert (archived["garmin_fitness_age"], archived["vo2max_run"]) == (27, 48)
    assert coaching.fitness_age(conn)["vo2max_run"] == 51
    conn.executemany("INSERT INTO activities(activity_id,start_time_local,updated_at) VALUES (?,?,'x')",
                     [(1, "2026-11-03T07:00:00"), (2, "2026-11-01T07:00:00")])
    conn.executemany("INSERT INTO fit_profile(activity_id,weight_kg) VALUES (?,?)", [(1, 76), (2, 78)])
    assert dashboard._weight(conn, "2026-11-02") == 78


def test_setting_change_marks_dashboard_for_regeneration(conn, monkeypatch):
    from garmin_mcp import server

    monkeypatch.setattr(server, "_with_db", lambda fn: fn(conn))
    result = server.update_athlete_setting("timezone", "Asia/Kolkata")
    assert result["recalculated"]
    assert conn.execute("SELECT value FROM meta WHERE key='dashboard_rebuild_pending'").fetchone()[0] == "1"


def test_units_floors_metres_distance_and_timestamp_format(conn):
    from garmin_mcp.normalize import _ms_to_iso, daily_from_summary

    rows = dict(daily_from_summary({"data": [{"calendarDate": DAY, "movement": {
        "steps": {"value": 4192, "distanceInMeters": 3440.0},
        "floorsAscended": {"value": 12, "distanceInMeters": 36.58}}}]}))
    assert rows[DAY]["floors_up_m"] == 36.58  # not the floor count (12)
    assert rows[DAY]["steps"] == 4192 and rows[DAY]["distance_m"] == 3440.0
    assert _ms_to_iso("2026-10-25T00:08:45.0") == "2026-10-25 00:08:45"
    assert _ms_to_iso(EPOCH_MS) == "2026-11-20 00:00:00"


def test_verify_passes_on_consistent_sources(conn):
    from garmin_mcp import verify

    _seed(conn)
    conn.execute("DELETE FROM raw_daily WHERE dataset='ex_daily_summary'")
    db.put_daily(conn, "pa_sleep", DAY, "personal_api", {
        "calendarDate": DAY, "deepSleepSeconds": 3600, "lightSleepSeconds": 14400,
        "remSleepSeconds": 7200, "sleepStartTimestampGMT": EPOCH_MS - 7 * 3600 * 1000,
        "sleepScores": {"overall": {"value": 82}}})
    conn.commit()
    rebuild(conn)
    result = verify.run(conn)
    assert result["ok"], result["problems"]
    assert any(row["table"] == "sleep" and row["column"] == "sleep_s"
               and row["agree"] == "1/1" for row in result["agreement"])


def test_verify_checks_latest_finished_archive_day(conn):
    from garmin_mcp import engine, verify

    rebuild(conn)
    today = datetime.now(engine._tz(conn)).date()
    yesterday = (today - timedelta(days=1)).isoformat()
    conn.execute("INSERT INTO daily(day, steps) VALUES (?, 100001)", (yesterday,))
    result = verify.run(conn)
    assert "daily.steps: 1 values outside 0-100000 steps" in result["problems"]
    conn.execute("DELETE FROM daily")
    conn.execute("INSERT INTO daily(day, steps) VALUES (?, 100001)", (today.isoformat(),))
    assert verify.run(conn)["ok"]


def test_provenance_distinguishes_completed_sync_from_successful_request(conn):
    from garmin_mcp import db, server
    from garmin_mcp.normalize import rebuild

    rebuild(conn)
    db.log(conn, "partial", "personal_api", "sleep", "2026-11-23", "ok")
    conn.commit()
    assert server._provenance(conn)["last_successful_sync"] is None
    conn.execute("INSERT INTO meta VALUES ('last_full_sync','2026-11-22T12:00:00+00:00')")
    conn.commit()
    assert server._provenance(conn)["last_successful_sync"] == "2026-11-22T12:00:00+00:00"
    assert db.coverage(conn)["last_full_sync"] == "2026-11-22T12:00:00+00:00"


def test_training_status_numeric_code_uses_phrase():
    from garmin_mcp import dashboard
    from garmin_mcp.normalize import _status_word

    assert _status_word({"trainingStatus": "DETRAINING"}) == "DETRAINING"
    assert _status_word({"trainingStatus": 7,
                         "trainingStatusFeedbackPhrase": "PRODUCTIVE_7"}) == "PRODUCTIVE"
    assert _status_word({"trainingStatus": 4}) is None
    assert dashboard._status_label(4) == "–"
    assert dashboard._status_label("NO_STATUS") == "No Status"


def test_snapshot_hrv_combines_deduplicated_nights_from_both_sources(conn):
    rebuild(conn)
    conn.execute("INSERT INTO hrv(day,last_night_avg) VALUES "
                 "('2026-11-20',80), ('2026-11-21',0), ('2026-11-23',60)")
    conn.execute("INSERT INTO health_status(day,hrv) VALUES ('2026-10-23',20), "
                 "('2026-11-20',10), ('2026-11-21',40)")
    snapshot = insights.health_snapshot(conn, "2026-11-23")["hrv"]
    assert snapshot["last_night_ms"] == 60
    assert snapshot["avg_7d_ms"] == 60 and snapshot["days_in_7d"] == 3
    assert snapshot["avg_60d_ms"] == 50 and snapshot["days_in_60d"] == 4
