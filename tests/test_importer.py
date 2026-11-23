import io
import json
import zipfile

from conftest import make_fit

from garmin_mcp import db
from garmin_mcp.importer import _calendar_day, run_import

# make_fit() sessions start 2026-11-01 07:00:00 UTC
START_MS = 1793516400000


def _write_export(root):
    dc = root / "DI_CONNECT"
    (dc / "DI-Connect-Aggregator").mkdir(parents=True)
    (dc / "DI-Connect-Wellness").mkdir()
    (dc / "DI-Connect-Metrics").mkdir()
    (dc / "DI-Connect-Fitness").mkdir()
    (dc / "DI-Connect-Uploaded-Files").mkdir()
    (dc / "DI-Connect-Aggregator/UDSFile_2026-10-01_2026-11-01.json").write_text(json.dumps(
        [{"calendarDate": "2026-11-01", "totalSteps": 9000, "restingHeartRate": 52}]))
    (dc / "DI-Connect-Wellness/2026-10-01_2026-11-01_1_sleepData.json").write_text(json.dumps(
        [{"calendarDate": "2026-11-01", "deepSleepSeconds": 3600}]))
    (dc / "DI-Connect-Metrics/TrainingReadinessDTO_20261001_20261101_1.json").write_text(
        json.dumps([{"calendarDate": "2026-11-01", "score": 70},
                    {"calendarDate": "2026-11-01", "score": 75}]))
    (dc / "DI-Connect-Metrics/EnduranceScore_20261001_20261101_1.json").write_text(
        json.dumps([{"calendarDate": 20261101, "overallScore": 6000}]))
    (dc / "DI-Connect-Wellness/1_heartRateZones.json").write_text(json.dumps([{"zone": 1}]))
    act = {"activityId": 99, "name": "Run", "activityType": "running",
           "startTimeGmt": START_MS, "startTimeLocal": START_MS + 19800000,
           "duration": 1634457.0, "distance": 461006.98, "elevationGain": 700.0,
           "avgHr": 160.0, "aerobicTrainingEffect": 3.2}
    (dc / "DI-Connect-Fitness/u_1_summarizedActivities.json").write_text(
        json.dumps([{"summarizedActivitiesExport": [act]}]))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("u_1.fit", make_fit(n=6))
    (dc / "DI-Connect-Uploaded-Files/UploadedFiles_0-_Part1.zip").write_bytes(buf.getvalue())


def test_calendar_day_formats():
    assert _calendar_day("2026-11-01") == "2026-11-01"
    assert _calendar_day(20261101) == "2026-11-01"
    assert _calendar_day(START_MS) == "2026-11-01"
    assert _calendar_day("junk") is None


def test_import_export_folder(conn, tmp_path):
    _write_export(tmp_path / "export")
    r = run_import(tmp_path / "export", conn=conn)
    assert r["daily"]["days_per_dataset"]["ex_daily_summary"] == 1
    assert r["daily"]["days_per_dataset"]["ex_endurance_score"] == 1
    assert "ex_hr_zones" in r["snapshots"]
    assert r["activities"] == {"added": 1, "already_present": 0}
    assert r["fit"]["attached"] == 1
    row = conn.execute("SELECT * FROM activities WHERE activity_id=99").fetchone()
    assert round(row["distance_m"], 1) == 4610.1 and round(row["duration_s"]) == 1634
    assert row["elevation_gain_m"] == 7.0 and row["fit_parsed"] == 1
    readiness = json.loads(conn.execute(
        "SELECT payload FROM raw_daily WHERE dataset='ex_training_readiness'").fetchone()[0])
    assert [x["score"] for x in readiness] == [70, 75]  # several per day kept as a list


def test_import_is_idempotent_and_never_overwrites_api_activity(conn, tmp_path):
    db.upsert_activity(conn, {"activityId": 99, "activityName": "From API", "distance": 1.0})
    _write_export(tmp_path / "export")
    run_import(tmp_path / "export", conn=conn)
    r2 = run_import(tmp_path / "export", conn=conn)
    assert r2["activities"] == {"added": 0, "already_present": 1}
    assert conn.execute("SELECT name FROM activities WHERE activity_id=99").fetchone()[0] == \
        "From API"
