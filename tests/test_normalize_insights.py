import json
from datetime import UTC, date, datetime, timedelta

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
