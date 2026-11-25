import json
import stat
import sys
from datetime import UTC, datetime, timedelta

import pytest
from garmin_fit_sdk import Encoder, Profile

from garmin_mcp import db, monitoring_preview, normalize, verify

STAMP = datetime(2026, 11, 25, 18, 31, tzinfo=UTC)


def _ms(stamp):
    return int(stamp.timestamp() * 1000)


def _short(stamp):
    return int(stamp.timestamp() - monitoring_preview.FIT_EPOCH) % 65536


def _fixture(path, rows=(), kind="monitoring_b"):
    encoder = Encoder()
    for name, cols in (("FILE_ID", {"type": kind, "time_created": STAMP}), *rows):
        encoder.write_mesg({"mesg_num": Profile["mesg_num"][name], **cols})
    path.write_bytes(encoder.close())
    return path


def test_monitoring_preview_counts_read_only_overlap_and_conflicts(tmp_path, monkeypatch, capsys):
    database = tmp_path / "archive.db"
    monkeypatch.setenv("GARMIN_DB_PATH", str(database))
    monkeypatch.setenv("GARMIN_TZ", "Asia/Kolkata")
    conn = db.connect(database)
    normalize.rebuild(conn)
    day = "2026-11-26"
    conn.execute("INSERT INTO daily(day,resting_hr) VALUES (?,54)", (day,))
    following = STAMP + timedelta(minutes=1)
    last = STAMP + timedelta(minutes=2)
    db.put_daily(conn, "heart_rate", day, "garminconnect", {
        "heartRateValues": [[_ms(STAMP), 60], [_ms(following), 61]],
    })
    db.put_daily(conn, "pa_heart_rate", day, "personal_api", {
        "heartRateValues": [[_ms(STAMP), 62]],
    })
    db.put_daily(conn, "stress", day, "garminconnect", {
        "stressValuesArray": [[_ms(STAMP), 20], [_ms(following), 31]],
        "bodyBatteryValuesArray": [[_ms(STAMP), "level", 70], [_ms(last), "level", 68],
                                   [_ms(last), "level", 73]],
    })
    conn.commit()
    conn.close()

    monitoring = (
        ("MONITORING_INFO", {"timestamp": STAMP, "resting_metabolic_rate": 1700}),
        ("MONITORING", {"timestamp_16": _short(STAMP), "heart_rate": 60}),
        ("MONITORING", {"timestamp": STAMP, "heart_rate": 60}),
        ("MONITORING", {"timestamp_16": _short(following), "heart_rate": 61}),
        ("MONITORING", {"timestamp": last, "heart_rate": 63}),
        ("MONITORING", {"timestamp_16": _short(last + timedelta(minutes=3)), "heart_rate": 64}),
        ("STRESS_LEVEL", {"stress_level_time": STAMP, "stress_level_value": 20}),
        ("STRESS_LEVEL", {"stress_level_time": following, "stress_level_value": 30}),
        ("STRESS_LEVEL", {"stress_level_time": last, "stress_level_value": 48}),
        ("STRESS_LEVEL", {"stress_level_time": last, "stress_level_value": 49}),
        ("HSA_BODY_BATTERY_DATA", {"timestamp": STAMP, "level": 70}),
        ("HSA_BODY_BATTERY_DATA", {"timestamp": last, "level": 68}),
        ("MONITORING_HR_DATA", {"timestamp": STAMP, "resting_heart_rate": 80,
                                "current_day_resting_heart_rate": 52}),
        ("MONITORING_HR_DATA", {"timestamp": following, "resting_heart_rate": 81}),
    )
    path = _fixture(tmp_path / "monitoring.fit", monitoring)
    source_bytes, fit_bytes = database.read_bytes(), path.read_bytes()
    monkeypatch.setattr(sys, "argv", ["garmin-mcp-verify", "--preview-wellness-fit", str(path)])
    verify.main()
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["candidate_local_days"] == 1
    assert result["unanchored_pulse_messages"] == 2
    assert result["uncompared_message_types"] == {"monitoring_info_mesgs": 1}
    assert result["signals"]["pulse"] == {
        "fit_keys": 3, "candidate_gaps": 1, "overlaps": 1, "agreements": 1, "disagreements": 0,
        "archive_conflicts": 1, "fit_conflicts": 0,
    }
    assert result["signals"]["stress"] == {
        "fit_keys": 3, "candidate_gaps": 0, "overlaps": 2, "agreements": 1, "disagreements": 1,
        "archive_conflicts": 0, "fit_conflicts": 1,
    }
    assert result["signals"]["body_battery"]["overlaps"] == 1
    assert result["signals"]["body_battery"]["archive_conflicts"] == 1
    assert result["signals"]["resting_pulse"]["disagreements"] == 1
    assert result["signals"]["resting_pulse"]["fit_keys"] == 1  # no rolling value
    assert "2026-" not in output and str(tmp_path) not in output
    monkeypatch.setattr(sys, "argv", [
        "garmin-mcp-verify", "--preview-wellness-fit", str(path), "--include-dates",
    ])
    verify.main()
    detailed = json.loads(capsys.readouterr().out)
    by_day = detailed["signals"]["stress"]["by_local_date"]
    assert by_day == {day: result["signals"]["stress"]}
    assert detailed["signals"]["resting_pulse"]["by_local_date"][day]["disagreements"] == 1
    assert database.read_bytes() == source_bytes
    assert path.read_bytes() == fit_bytes


def test_wrap_uses_previous_full_timestamp_and_next_full_bound():
    first = datetime.fromtimestamp(monitoring_preview.FIT_EPOCH + 17000 * 65536 - 60, UTC)
    valid = first + timedelta(minutes=2)
    later = valid + timedelta(minutes=1)
    points, missing = monitoring_preview._fit_signals({"monitoring_mesgs": [
        {"timestamp": first, "heart_rate": 56},
        {"timestamp_16": _short(valid), "heart_rate": 58},
        {"timestamp_16": _short(later + timedelta(minutes=1)), "heart_rate": 61},
        {"timestamp": later, "heart_rate": 60},
        {"timestamp": later + timedelta(minutes=30)},
    ]}, UTC)
    assert tuple(points["pulse"]) == (first.timestamp(), later.timestamp(), valid.timestamp())
    assert missing == 1


def test_preview_rejects_activity_and_corrupted_fit(tmp_path):
    activity = _fixture(tmp_path / "activity.fit", kind="activity")
    database = tmp_path / "untouched.db"
    with pytest.raises(ValueError, match="monitoring FIT"):
        monitoring_preview.preview(database, activity)
    damaged = _fixture(tmp_path / "damaged.fit")
    damaged.write_bytes(damaged.read_bytes()[:-2] + b"\x00\x00")
    with pytest.raises(ValueError, match="integrity"):
        monitoring_preview.preview(database, damaged)
    assert not database.exists()



def test_retain_is_explicit_private_idempotent_and_requires_valid_input(tmp_path, monkeypatch, capsys):
    database = tmp_path / "archive.db"
    db.connect(database).close()
    archive = database.read_bytes()
    source = _fixture(tmp_path / "well.fit")
    directory = tmp_path / "monitoring-fit"
    monkeypatch.setenv("GARMIN_DB_PATH", str(database))
    monkeypatch.setenv("GARMIN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["garmin-mcp-verify", "--preview-wellness-fit", str(source)])
    verify.main()
    assert "retained" not in json.loads(capsys.readouterr().out)
    assert not directory.exists()

    monkeypatch.setattr(sys, "argv", [
        "garmin-mcp-verify", "--preview-wellness-fit", str(source), "--retain",
    ])
    verify.main()
    assert json.loads(capsys.readouterr().out)["retained"] == "created"
    retained, = directory.iterdir()
    assert retained.read_bytes() == source.read_bytes()
    assert stat.S_IMODE(retained.stat().st_mode) == 0o600
    verify.main()
    assert json.loads(capsys.readouterr().out)["retained"] == "already_present"
    assert list(directory.iterdir()) == [retained]
    assert database.read_bytes() == archive

    activity = _fixture(tmp_path / "activity.fit", kind="activity")
    rejected = tmp_path / "unapproved"
    with pytest.raises(ValueError, match="monitoring FIT"):
        monitoring_preview.preview(database, activity, retain_directory=rejected)
    assert not rejected.exists()


def test_end_of_day_resting_estimate_belongs_to_the_day_it_closes(tmp_path, monkeypatch):
    """The watch writes it at its own midnight, which may differ from the configured zone."""
    database = tmp_path / "archive.db"
    monkeypatch.setenv("GARMIN_TZ", "Asia/Kolkata")
    conn = db.connect(database)
    normalize.rebuild(conn)
    conn.execute("INSERT INTO daily(day,resting_hr) VALUES ('2026-06-10',52)")
    conn.commit()
    conn.close()
    start = datetime(2026, 6, 9, 23, 0, tzinfo=UTC)  # midnight on a watch set to UTC+1
    local = int(start.timestamp() - monitoring_preview.FIT_EPOCH) + 3600
    path = _fixture(tmp_path / "monitoring.fit", (
        ("MONITORING_INFO", {"timestamp": start, "local_timestamp": local}),
        ("MONITORING_HR_DATA", {"timestamp": start + timedelta(days=1), "current_day_resting_heart_rate": 52}),
    ))
    result = monitoring_preview.preview(database, path, include_dates=True)
    assert result["signals"]["resting_pulse"]["agreements"] == 1
    assert list(result["signals"]["resting_pulse"]["by_local_date"]) == ["2026-06-10"]
