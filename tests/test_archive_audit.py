import json
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from garmin_mcp import archive_audit, athlete, dashboard, dashboard_history, db, wellness_timeline
from garmin_mcp.normalize import rebuild


def _stamp(local):
    return int(local.timestamp()) * 1000


def test_timelines_drop_sentinels_and_local_date_mismatches(conn):
    rebuild(conn)
    day = "2026-11-25"
    zone = ZoneInfo("Asia/Kolkata")
    local = datetime.fromisoformat(day).replace(tzinfo=zone)
    start = _stamp(local)
    db.put_daily(conn, "stress", day, "garminconnect", {
        "stressValuesArray": [[start, 0], [start, 80], [start + 300_000, 50], [start + 900_000, -2],
                              [start + 2_700_000, 40], [start - 1_000, 70], [start + 30, 101], [None]],
        "bodyBatteryValuesArray": [[start, "level", 73], [start + 300_000, "level", 72],
                                   [start + 2_700_000, "level", 68], [start + 3_000_000, "level", 0]],
    })
    result = dashboard_history.collect(conn, day, zone)["days"][day]["intraday_wellness"]
    stress, battery = result["stress"], result["battery"]
    assert [(s["time"], s["value"], s["span"], s["count"]) for s in stress["slots"]] == [
        ("00:00", 25, (0, 50), 2), ("00:45", 40, (40, 40), 1)]
    assert battery["first"] == ("00:00", 73) and battery["last"] == ("00:45", 68)
    assert battery["slots"][0]["value"] == 72
    athlete.set_value(conn, "timezone", "Asia/Kolkata")
    conn.execute("INSERT INTO daily(day,steps) VALUES (?,1000)", (day,))
    page = dashboard.render(dashboard.collect(conn, day))
    html = dashboard._intraday_wellness_card(result, day, zone)
    assert "Stress and Body Battery" in page
    assert "Garmin Body Battery" in html and "Highest measured 15-minute median · 25/100" in html
    assert html.count(">24:00</text>") == 2
    paths = re.findall(r'<path d="([^"]+)" class="ln s1 context"', html)
    assert len(paths) == 2
    assert all(path.count("M") == 2 and "L" not in path for path in paths)


def test_repeated_local_hour_does_not_merge_windows(conn):
    ny = ZoneInfo("America/New_York")
    first = datetime(2026, 11, 1, 1, 5, tzinfo=ny)
    second = first.replace(fold=1)
    db.put_daily(conn, "stress", "2026-11-01", "garminconnect",
                 {"stressValuesArray": [[_stamp(first), 25], [_stamp(second), 50]]})
    [(_, wellness)] = wellness_timeline.collect(conn, "2026-11-01", "2026-11-01", ny)
    assert [slot["time"] for slot in wellness["stress"]["slots"]] == ["01:00 -0400", "01:00 -0500"]
    html = dashboard._intraday_wellness_card(wellness, "2026-11-01", ny)
    assert "<h4>Garmin Body Battery</h4>" in html and "Timeline unavailable for this date." in html


def test_audit_keeps_coverage_and_file_availability_distinct(conn, tmp_path, monkeypatch):
    monkeypatch.delenv("GARMIN_TZ", raising=False)
    athlete.set_value(conn, "timezone", "Asia/Kolkata")
    database = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    present = tmp_path / "protected-waypoints.fit"
    present.write_bytes(b"file")
    empty = tmp_path / "empty.fit"
    empty.touch()
    missing = tmp_path / "missing.fit"
    conn.executemany("INSERT INTO activities(activity_id,fit_path,fit_parsed,updated_at) "
                     "VALUES (?,?,?,CURRENT_TIMESTAMP)",
                     [(1, str(present), 0), (2, str(missing), 1), (3, str(empty), 0), (4, None, 1)])
    first = datetime(2026, 11, 23, 20, tzinfo=UTC)
    for offset in (0, 1, 2):
        stamp = first + timedelta(days=offset)
        day = stamp.astimezone(ZoneInfo("Asia/Kolkata")).date().isoformat()
        db.put_daily(conn, "stress", day, "garminconnect",
                     {"stressValuesArray": [[_stamp(stamp), 42 if offset != 1 else -1]]})
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    source_bytes = database.read_bytes()
    report = archive_audit.audit(database)
    assert database.read_bytes() == source_bytes
    assert not report["ok"] and report["sqlite_quick_check"] == "passed"
    assert report["fit_references"] == {"activities": 4, "decoded": 2, "no_file_reference": 1,
                                       "present": 1, "missing": 1, "unavailable_or_empty": 1}
    assert report["wellness_timelines"]["stored_connect_stress_days"] == 3
    assert report["wellness_timelines"]["stress"] == {
        "usable_days": 2, "first_day": "2026-11-24", "last_day": "2026-11-26", "gaps_between_usable_days": 1,
    }
    assert report["wellness_timelines"]["battery"]["usable_days"] == 0
    assert str(tmp_path) not in json.dumps(report) and "protected-waypoints" not in json.dumps(report)


def test_audit_reports_unrelated_database_without_migrating(tmp_path):
    path = tmp_path / "other.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE other (key TEXT)")
    assert archive_audit.audit(path) == {"ok": False, "reason": "This database has no Garmin Tracking archive schema."}


def test_battery_accepts_known_compact_and_described_archive_shapes():
    day = "2026-11-25"
    instant = datetime.fromisoformat(day).replace(tzinfo=UTC)
    stamp = _stamp(instant)
    compact = wellness_timeline.samples({"bodyBatteryValuesArray": [[stamp, 72]]}, day, UTC)
    assert compact == {"battery": [(instant, 72)]}

    described = {
        "bodyBatteryValueDescriptorDTOList": [
            {"bodyBatteryValueDescriptorKey": "BODY_BATTERY_LEVEL", "bodyBatteryValueDescriptorIndex": 0},
            {"bodyBatteryValueDescriptorKey": "TIMESTAMP", "bodyBatteryValueDescriptorIndex": 2},
        ],
        "bodyBatteryValuesArray": [[64, 10, stamp], [75, 14, stamp + 60_000]],
    }
    assert wellness_timeline.samples(described, day, UTC) == {
        "battery": [(instant, 64), (instant + timedelta(minutes=1), 75)],
    }


def test_unknown_battery_descriptors_do_not_mask_stress_or_guess_a_column():
    day = "2026-11-25"
    instant = datetime.fromisoformat(day).replace(tzinfo=UTC)
    stamp = _stamp(instant)
    payload = {
        "stressValuesArray": [[stamp, 32]],
        "bodyBatteryValuesArray": [[stamp, 55, 64]],
        "bodyBatteryValueDescriptorDTOList": [{"key": "timestamp", "index": 0},
                                               {"key": "unknown_score", "index": 1}],
    }
    assert wellness_timeline.samples(payload, day, UTC) == {"stress": [(instant, 32)]}
    payload["bodyBatteryValueDescriptorDTOList"].extend(
        [{"key": "level", "index": 1}, {"key": "level", "index": 2}],
    )
    assert wellness_timeline.samples(payload, day, UTC) == {"stress": [(instant, 32)]}


def test_timelines_use_the_watch_clock_for_days_recorded_away_from_home():
    """A day recorded at UTC+1 keeps its late-evening samples when home is Asia/Kolkata."""
    late = datetime(2026, 6, 10, 22, 0, tzinfo=UTC)  # 23:00 on the watch, 03:30 next day in Kolkata
    payload = {"startTimestampGMT": "2026-06-09T23:00:00.0", "startTimestampLocal": "2026-06-10T00:00:00.0",
               "stressValuesArray": [[int(late.timestamp() * 1000), 25]]}
    [(stamp, value)] = wellness_timeline.samples(payload, "2026-06-10", ZoneInfo("Asia/Kolkata"))["stress"]
    assert (stamp.strftime("%H:%M"), value) == ("23:00", 25)


def test_intraday_pulse_uses_the_watch_clock(conn):
    late = datetime(2026, 6, 10, 22, 0, tzinfo=UTC)
    db.put_daily(conn, "pa_heart_rate", "2026-06-10", "personal_api", {
        "startTimestampGMT": "2026-06-09T23:00:00.0", "startTimestampLocal": "2026-06-10T00:00:00.0",
        "heartRateValues": [[int(late.timestamp() * 1000), 61]]})
    found = dashboard_history._intraday_pulse(conn, "2026-06-10", "2026-06-10", ZoneInfo("Asia/Kolkata"))
    assert [slot["time"] for slot in found["2026-06-10"]["slots"]] == ["23:00"]
