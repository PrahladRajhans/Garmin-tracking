import csv
import io
import stat
import sys
from datetime import date

import pytest

from garmin_mcp import archive_export, db, normalize, verify

START = date(2026, 11, 12)
END = date(2026, 11, 14)


@pytest.fixture
def path(tmp_path):
    path = tmp_path / "garmin.db"
    conn = db.connect(path)
    for activity, day, category in (
        (1, "2026-11-11", "running"),
        (2, "2026-11-12", "running"),
        (3, "2026-11-12", "=HYPERLINK(\"https://example.invalid\")"),
        (4, "2026-11-14", "cycling"),
        (5, "2026-11-15", "running"),
    ):
        db.upsert_activity(conn, {
            "activityId": activity,
            "activityName": "Private park",
            "activityType": {"typeKey": category},
            "startTimeLocal": day + " 06:00:00",
            "startLatitude": 12.3,
            "startLongitude": 77.4,
            "distance": 0,
            "duration": 61,
        })
    normalize.rebuild(conn)
    conn.execute("INSERT INTO daily(day,steps,resting_hr) VALUES ('2026-11-12',0,58)")
    conn.execute("INSERT INTO sleep(day,sleep_s) VALUES ('2026-11-13',24800)")
    conn.execute("INSERT INTO hrv(day,last_night_avg) VALUES ('2026-11-14',-1)")
    conn.execute("INSERT INTO health_status(day,hrv) VALUES ('2026-11-13',32),('2026-11-14',41),"
                 "('2026-11-15',42),('2026-11-16',0)")
    conn.commit()
    conn.close()
    return path


def _render(path, dataset):
    stream = io.StringIO()
    archive_export.write_csv(path, dataset, START, END, stream)
    return stream.getvalue()


def test_activity_export_preserves_identity_limits_and_numeric_zero(path):
    archive = path.read_bytes()
    content = _render(path, "activities")
    rows = list(csv.DictReader(io.StringIO(content)))
    assert [row["activity_id"] for row in rows] == ["2", "3", "4"]
    assert [row["activity_type"] for row in rows] == ["running", "", "cycling"]
    assert all(float(row["distance_m"]) == 0 for row in rows)
    assert rows[0]["avg_hr_bpm"] == ""
    assert set(rows[0]) == set(archive_export.ACTIVITY_COLUMNS)
    assert "Private park" not in content
    assert path.read_bytes() == archive


def test_wellness_sleep_only_and_hrv_only_dates_stay_in_export(path):
    stream = io.StringIO()
    archive_export.write_csv(path, "wellness", START, date(2026, 11, 16), stream)
    rows = list(csv.DictReader(io.StringIO(stream.getvalue())))
    assert [row["local_date"] for row in rows] == ["2026-11-12", "2026-11-13", "2026-11-14", "2026-11-15"]
    assert float(rows[0]["steps"]) == 0
    assert float(rows[1]["sleep_s"]) == 24800
    assert [float(row["night_hrv_ms"]) for row in rows[1:]] == [32, 41, 42]
    assert rows[1]["steps"] == rows[2]["sleep_s"] == ""


def test_cli_private_file_preserves_existing_file_and_archive(path, monkeypatch, capsys):
    monkeypatch.setenv("GARMIN_DB_PATH", str(path))
    output = path.with_name("export.csv")
    monkeypatch.setattr(sys, "argv", [
        "garmin-mcp-verify", "--export-csv", "activities", "--from-date", "2026-11-12",
        "--to-date", "2026-11-14", "--output", str(output),
    ])
    verify.main()
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    before = output.read_bytes()
    with pytest.raises(SystemExit) as error:
        verify.main()
    assert error.value.code == 2
    assert "already exists" in capsys.readouterr().err
    assert output.read_bytes() == before


def test_export_range_failure_leaves_no_output(path):
    destination = path.with_name("export.csv")
    with pytest.raises(ValueError, match="start date"):
        archive_export.export_file(path, "wellness", END, START, destination)
    assert not destination.exists()
    assert list(path.parent.iterdir()) == [path]
