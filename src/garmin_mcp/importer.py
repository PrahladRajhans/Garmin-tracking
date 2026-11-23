"""Import a Garmin account data export (the GDPR "Export your data" ZIP or its unzipped folder).

The export holds the full history: daily summaries, sleep, health status (overnight HRV/RHR/
SpO2/respiration vs baseline), training readiness, training status, race predictions,
endurance/hill score, acute load, VO2max, acclimation, activities and their original FIT files.

Everything lands in the same database as the API sync, tagged ``source='export'`` and with
dataset names prefixed ``ex_``. Re-running is safe (idempotent). Activities already synced from
an API are never overwritten by the export's coarser summary.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sqlite3
import zipfile
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from garmin_mcp import db, fit
from garmin_mcp.config import db_path, fit_dir

SOURCE = "export"

# File-name prefix -> dataset name. Records are grouped by calendar day.
DAILY_FILES = {
    "UDSFile": "ex_daily_summary",
    "HydrationLogFile": "ex_hydration",
    "sleepData": "ex_sleep",
    "healthStatusData": "ex_health_status",
    "AbnormalHrEvents": "ex_abnormal_hr",
    "TrainingReadinessDTO": "ex_training_readiness",
    "TrainingHistory": "ex_training_status",
    "RunRacePredictions": "ex_race_predictions",
    "EnduranceScore": "ex_endurance_score",
    "HillScore": "ex_hill_score",
    "MetricsAcuteTrainingLoad": "ex_acute_load",
    "MetricsMaxMetData": "ex_vo2max",
    "MetricsHeatAltitudeAcclimation": "ex_acclimation",
}

# Whole-file snapshots (profile, zones, records...) stored once in raw_range.
SNAPSHOT_FILES = {
    "fitnessAgeData": "ex_fitness_age",
    "heartRateZones": "ex_hr_zones",
    "powerZones": "ex_power_zones",
    "userBioMetrics": "ex_biometrics",
    "bioMetrics_latest": "ex_biometrics_latest",
    "userBioMetricProfileData": "ex_biometric_profile",
    "wellnessActivities": "ex_wellness_activities",
    "personalRecord": "ex_personal_records",
    "workout": "ex_workouts",
    "gear": "ex_gear",
    "trainingPlan": "ex_training_plan",
    "weekly_training_report": "ex_weekly_report",
    "user_profile": "ex_user_profile",
    "user_settings": "ex_user_settings",
}


# --------------------------------------------------------------------------- file access
class ExportReader:
    """Uniform access to the export whether it is a folder or a (possibly nested) ZIP."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._zip = zipfile.ZipFile(path) if path.is_file() else None

    def names(self) -> list[str]:
        if self._zip:
            return self._zip.namelist()
        return [str(p.relative_to(self.path)) for p in self.path.rglob("*") if p.is_file()]

    def read(self, name: str) -> bytes:
        if self._zip:
            return self._zip.read(name)
        return (self.path / name).read_bytes()


def _calendar_day(value: Any) -> str | None:
    """Export dates come as 'YYYY-MM-DD', yyyymmdd ints, or epoch milliseconds."""
    if isinstance(value, str):
        return value[:10] if re.match(r"\d{4}-\d{2}-\d{2}", value) else None
    if isinstance(value, (int, float)):
        if value > 10**11:
            return datetime.fromtimestamp(value / 1000, tz=UTC).date().isoformat()
        text = str(int(value))
        if len(text) == 8:
            return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return None


def _record_day(rec: dict[str, Any]) -> str | None:
    for key in ("calendarDate", "calendar_date", "date"):
        if key in rec:
            return _calendar_day(rec[key])
    return None


def _match_prefix(filename: str, table: dict[str, str]) -> str | None:
    base = filename.rsplit("/", 1)[-1]
    for prefix, dataset in table.items():
        # Names look like "UDSFile_2024-...json", "2024-..._<userId>_sleepData.json",
        # "TrainingReadinessDTO_2026..._<userId>.json", "user@x_personalRecord.json".
        if re.search(rf"(^|_){re.escape(prefix)}(_|\.json$)", base):
            return dataset
    return None


# --------------------------------------------------------------------------- importers
def import_daily(conn: sqlite3.Connection, reader: ExportReader, names: list[str]) -> dict:
    by_day: dict[tuple[str, str], list[Any]] = defaultdict(list)
    files = 0
    for name in names:
        if not name.endswith(".json"):
            continue
        dataset = _match_prefix(name, DAILY_FILES)
        if not dataset:
            continue
        data = json.loads(reader.read(name))
        files += 1
        for rec in data if isinstance(data, list) else [data]:
            day = _record_day(rec) if isinstance(rec, dict) else None
            if day:
                by_day[(dataset, day)].append(rec)
    for (dataset, day), recs in by_day.items():
        db.put_daily(conn, dataset, day, SOURCE, recs[0] if len(recs) == 1 else recs)
    conn.commit()
    counts: dict[str, int] = defaultdict(int)
    for dataset, _ in by_day:
        counts[dataset] += 1
    return {"files": files, "days_per_dataset": dict(sorted(counts.items()))}


def import_snapshots(conn: sqlite3.Connection, reader: ExportReader, names: list[str]) -> list:
    stored = []
    for name in names:
        if not name.endswith(".json"):
            continue
        dataset = _match_prefix(name, SNAPSHOT_FILES)
        if dataset:
            db.put_range(conn, dataset, "all", "all", SOURCE, json.loads(reader.read(name)))
            stored.append(dataset)
    conn.commit()
    return sorted(set(stored))


def _ms_to_str(value: Any) -> str | None:
    if not isinstance(value, (int, float)):
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")


def export_activity_to_summary(a: dict[str, Any]) -> dict[str, Any]:
    """Map an export activity (ms, cm, speed x10) onto the API field names and units."""

    def scaled(key: str, factor: float) -> float | None:
        v = a.get(key)
        return v / factor if isinstance(v, (int, float)) else None

    return {
        "activityId": a["activityId"],
        "activityName": a.get("name"),
        "activityType": {"typeKey": a.get("activityType")},
        # startTimeLocal in the export is local wall-clock time encoded as epoch ms.
        "startTimeLocal": _ms_to_str(a.get("startTimeLocal")),
        "startTimeGMT": _ms_to_str(a.get("startTimeGmt")),
        "duration": scaled("duration", 1000),
        "distance": scaled("distance", 100),
        "averageHR": a.get("avgHr"),
        "maxHR": a.get("maxHr"),
        "calories": a.get("calories"),
        "elevationGain": scaled("elevationGain", 100),
        "activityTrainingLoad": a.get("activityTrainingLoad"),
        "aerobicTrainingEffect": a.get("aerobicTrainingEffect"),
        "anaerobicTrainingEffect": a.get("anaerobicTrainingEffect"),
        "vO2MaxValue": a.get("vO2MaxValue"),
        "_export": a,
    }


def import_activities(conn: sqlite3.Connection, reader: ExportReader, names: list[str]) -> dict:
    added = kept = 0
    for name in names:
        if not name.endswith("summarizedActivities.json"):
            continue
        data = json.loads(reader.read(name))
        blocks = data if isinstance(data, list) else [data]
        for block in blocks:
            for act in block.get("summarizedActivitiesExport", []):
                exists = conn.execute(
                    "SELECT 1 FROM activities WHERE activity_id=?", (act["activityId"],)
                ).fetchone()
                if exists:
                    kept += 1  # API data is richer; never overwrite it
                    continue
                db.upsert_activity(conn, export_activity_to_summary(act))
                added += 1
    conn.commit()
    return {"added": added, "already_present": kept}


def _iter_fit_files(reader: ExportReader, names: list[str]) -> Iterator[tuple[str, bytes]]:
    for name in names:
        lower = name.lower()
        if lower.endswith(".fit"):
            yield name, reader.read(name)
        elif lower.endswith(".zip") and "uploaded" in lower:
            with zipfile.ZipFile(io.BytesIO(reader.read(name))) as inner:
                for inner_name in inner.namelist():
                    if inner_name.lower().endswith(".fit"):
                        yield inner_name, inner.read(inner_name)


def import_fit_files(conn: sqlite3.Connection, reader: ExportReader, names: list[str],
                     tolerance_s: int = 120) -> dict:
    """Attach activity FIT files to activities by matching session start time (UTC)."""
    starts: dict[int, int] = {}
    for row in conn.execute(
        "SELECT activity_id, start_time_gmt FROM activities WHERE fit_parsed=0 "
        "AND start_time_gmt IS NOT NULL"
    ):
        try:
            ts = datetime.strptime(row[1][:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        except ValueError:
            continue
        starts[int(ts.timestamp())] = row[0]

    stats = {"fit_files": 0, "activity_files": 0, "attached": 0, "unmatched": 0, "errors": 0}
    for _, data in _iter_fit_files(reader, names):
        stats["fit_files"] += 1
        try:
            messages = fit.decode(data)
        except Exception:  # noqa: BLE001 - skip unreadable files
            stats["errors"] += 1
            continue
        file_type = (messages.get("file_id_mesgs") or [{}])[0].get("type")
        sessions = messages.get("session_mesgs") or []
        if file_type != "activity" or not sessions:
            continue
        stats["activity_files"] += 1
        start = sessions[0].get("start_time")
        if not hasattr(start, "timestamp"):
            stats["unmatched"] += 1
            continue
        epoch = int(start.timestamp())
        match = next(
            (starts[t] for t in range(epoch - tolerance_s, epoch + tolerance_s + 1) if t in starts),
            None,
        )
        if match is None:
            stats["unmatched"] += 1
            continue
        path = fit_dir() / f"{match}.fit"
        path.write_bytes(data)
        conn.execute("UPDATE activities SET fit_path=? WHERE activity_id=?", (str(path), match))
        fit.store(conn, match, data)
        starts = {t: a for t, a in starts.items() if a != match}
        stats["attached"] += 1
        conn.commit()
    return stats


def run_import(path: str | Path, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    reader = ExportReader(Path(path).expanduser())
    names = reader.names()
    own = conn is None
    conn = conn or db.connect(db_path())
    try:
        result = {
            "daily": import_daily(conn, reader, names),
            "snapshots": import_snapshots(conn, reader, names),
            "activities": import_activities(conn, reader, names),
        }
        result["fit"] = import_fit_files(conn, reader, names)
        db.log(conn, "import", SOURCE, "export", str(path), "ok")
        conn.commit()
        return result
    finally:
        if own:
            conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a Garmin data export (ZIP or folder).")
    parser.add_argument("path", help="path to the export .zip or its unzipped folder")
    args = parser.parse_args()
    print(json.dumps(run_import(args.path), indent=2))


if __name__ == "__main__":
    main()
