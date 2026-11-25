import io
import json
import zipfile
from pathlib import Path

import pytest
from conftest import make_fit

from garmin_mcp import db
from garmin_mcp.importer import (
    ExportReader,
    _calendar_day,
    _record_day,
    import_fit_files,
    run_import,
)

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
    assert _calendar_day("2026-02-30") is None
    assert _calendar_day(20269999) is None
    assert _calendar_day(float("inf")) is None
    assert _record_day({"calendarDate": "invalid", "calendar_date": 20261101}) == "2026-11-01"


def test_import_fit_prefers_closest_and_preserves_new_revisions(conn, tmp_path):
    reader = ExportReader(tmp_path)
    name = "run.fit"
    (tmp_path / name).write_bytes(make_fit(n=6))
    conn.executemany("INSERT INTO activities(activity_id,start_time_gmt,updated_at) VALUES (?,?,'x')",
                     [(1, "2026-11-01 06:58:30"), (2, "2026-11-01T12:30:00+05:30")])
    assert import_fit_files(conn, reader, [name])["attached"] == 1
    path = conn.execute("SELECT fit_path FROM activities WHERE activity_id=2").fetchone()[0]
    assert path and conn.execute("SELECT fit_parsed FROM activities WHERE activity_id=1").fetchone()[0] == 0

    (tmp_path / name).write_bytes(make_fit(n=7))
    stats = import_fit_files(conn, reader, [name])
    assert stats["already_parsed"] == 1 and not stats["attached"]
    assert conn.execute("SELECT fit_path FROM activities WHERE activity_id=2").fetchone()[0] == path
    assert len(list(Path(path).parent.glob("2-*.fit"))) == 1


def test_import_fit_keeps_equal_start_matches_unassigned(conn, tmp_path):
    (tmp_path / "run.fit").write_bytes(make_fit(n=6))
    conn.executemany("INSERT INTO activities(activity_id,start_time_gmt,updated_at) VALUES (?,?,'x')",
                     [(1, "2026-11-01 07:00:00"), (2, "2026-11-01T07:00:00Z")])
    stats = import_fit_files(conn, ExportReader(tmp_path), ["run.fit"])
    assert stats["ambiguous"] == stats["unmatched"] == 1 and not stats["attached"]
    assert not conn.execute("SELECT 1 FROM activities WHERE fit_path IS NOT NULL").fetchone()


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



def test_replaying_snapshot_bundle_adds_no_superseded_versions(conn, tmp_path):
    current = tmp_path / "1_heartRateZones_b.json"
    (tmp_path / "1_heartRateZones_a.json").write_text('[{"zone":1}]')
    current.write_text('[{"zone":2}]')

    for _ in range(2):
        assert run_import(tmp_path, conn=conn)["snapshots"] == ["ex_hr_zones"]
    active = "SELECT payload FROM raw_range WHERE dataset='ex_hr_zones'"
    history = "SELECT payload FROM raw_payload_history WHERE dataset='ex_hr_zones' ORDER BY id"
    assert json.loads(conn.execute(active).fetchone()[0]) == [{"zone": 2}]
    assert [json.loads(row[0]) for row in conn.execute(history)] == [[{"zone": 1}]]

    current.write_text('[{"zone":3}]')
    run_import(tmp_path, conn=conn)
    assert json.loads(conn.execute(active).fetchone()[0]) == [{"zone": 3}]
    assert {row[0] for row in conn.execute(history)} == {'[{"zone":1}]', '[{"zone":2}]'}


def test_coverage_isolates_each_import_even_when_times_match(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(db, "now_iso", lambda: "2026-11-25T08:00:00+00:00")
    damaged = tmp_path / "damaged.fit"
    damaged.write_bytes(b"not a FIT file")
    assert run_import(tmp_path, conn=conn)["fit"]["errors"] == 1
    failed = db.coverage(conn)["last_sync"]
    damaged.unlink()
    assert run_import(tmp_path, conn=conn)["fit"]["errors"] == 0
    succeeded = db.coverage(conn)["last_sync"]

    assert failed["calls"] == succeeded["calls"] == 1
    assert failed["errors"] == 1 and succeeded["errors"] == 0
    assert failed["run_id"] != succeeded["run_id"]


def test_import_rejects_nonexistent_export_before_creating_database(tmp_path, monkeypatch):
    database = tmp_path / "no-archive.db"
    monkeypatch.setenv("GARMIN_DB_PATH", str(database))
    with pytest.raises(FileNotFoundError, match="existing Garmin export"):
        run_import(tmp_path / "missing-export")
    assert not database.exists()


def test_bad_fit_crc_and_nested_zip_do_not_prevent_accepting_valid_fit(conn, tmp_path):
    original = make_fit(n=6)
    (tmp_path / "corrupt.fit").write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
    (tmp_path / "UploadedFiles_bad.zip").write_bytes(b"invalid ZIP")
    (tmp_path / "valid.fit").write_bytes(original)
    conn.execute("INSERT INTO activities(activity_id,start_time_gmt,updated_at) "
                 "VALUES (2,'2026-11-01 07:00:00','x')")
    conn.commit()
    with ExportReader(tmp_path) as reader:
        stats = import_fit_files(conn, reader, ["corrupt.fit", "UploadedFiles_bad.zip", "valid.fit"])
    assert stats["errors"] == 2 and stats["attached"] == 1 and stats["fit_files"] == 2
    path = Path(conn.execute("SELECT fit_path FROM activities WHERE activity_id=2").fetchone()[0])
    assert path.read_bytes() == original
    assert not list(path.parent.glob("2-*.fit"))


def test_failed_fit_reference_keeps_previous_pointer_and_rows(conn, tmp_path):
    (tmp_path / "retry.fit").write_bytes(make_fit(n=7))
    conn.execute("INSERT INTO activities(activity_id,start_time_gmt,updated_at,fit_path) "
                 "VALUES (1,'2026-11-01 07:00:00','x','old.fit')")
    conn.execute("INSERT INTO fit_records(activity_id,ts,heart_rate) VALUES (1,'old',62)")
    conn.execute("CREATE TRIGGER fail_reference BEFORE UPDATE OF fit_path ON activities "
                 "BEGIN SELECT RAISE(ABORT,'blocked'); END;")
    conn.commit()
    stats = import_fit_files(conn, ExportReader(tmp_path), ["retry.fit"])
    conn.commit()
    assert stats["errors"] == 1 and stats["attached"] == 0
    assert tuple(conn.execute("SELECT fit_path,fit_parsed FROM activities").fetchone()) == ("old.fit", 0)
    assert [tuple(row) for row in conn.execute("SELECT ts,heart_rate FROM fit_records")] == [("old", 62)]
