"""Read saved activity weather and optionally join locally supplied observation windows."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from garmin_mcp import db

AQI_STANDARDS = {"IN-CPCB": "India CPCB", "US-EPA": "US EPA"}
FIELDS = {
    "temperature_c": (-100, 70),
    "humidity_pct": (0, 100),
    "wind_m_s": (0, 150),
    "precipitation_mm": (0, math.inf),
    "aqi": (0, 500),
}
DETAIL_KIND = "local_conditions_v1"
OPEN_METEO_SOURCE = "Open-Meteo model, location rounded to ~1 km"
ALIGNED_RAIN = "preceding_hour"
BEDROOM_DATASET = "local_bedroom_v1"
BEDROOM_FIELDS = {"temperature_c": FIELDS["temperature_c"], "humidity_pct": FIELDS["humidity_pct"],
                  "pm25_ug_m3": (0, math.inf)}
MAX_ROWS = 512


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("use a timestamp with an explicit UTC offset, such as 2026-11-20T01:30:00Z")
    return parsed.astimezone(UTC)


def _value(value: Any, limits: tuple[float, float]) -> float | None:
    if (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and limits[0] <= value <= limits[1]):
        return float(value)
    return None


def _text(value: Any) -> str:
    return " ".join(value.split())[:100] if isinstance(value, str) else ""


def _payload(conn: sqlite3.Connection, aid: int, kind: str) -> Any:
    row = conn.execute("SELECT payload FROM activity_details WHERE activity_id=? AND kind=?",
                       (aid, kind)).fetchone()
    return json.loads(row[0]) if row and row[0] else None


def for_activity(conn: sqlite3.Connection, aid: int) -> dict:
    weather = _payload(conn, aid, "weather")
    snapshot = {}
    if isinstance(weather, dict):
        raw_temp = _value(weather.get("temp"), (-148, 158))
        if raw_temp is not None:
            snapshot["temperature_c"] = round((raw_temp - 32) * 5 / 9, 1)
        humidity = _value(weather.get("relativeHumidity"), FIELDS["humidity_pct"])
        if humidity is not None:
            snapshot["humidity_pct"] = humidity
        description = weather.get("weatherTypeDTO")
        if isinstance(description, dict):
            label = _text(description.get("desc") or description.get("weatherTypeDesc"))
            if label:
                snapshot["description"] = label
        if snapshot:
            snapshot.update(source="Garmin saved weather", reference_time=_text(weather.get("issueDate")))
    windows = _payload(conn, aid, DETAIL_KIND) or []
    for window in windows:
        if (window.get("source") == OPEN_METEO_SOURCE and window.get("kind") == "model"
                and window.get("precipitation_alignment") != ALIGNED_RAIN):
            # Older fetches assigned rain to the hour after the API's accumulation.
            window.pop("precipitation_mm", None)
    return {"garmin_snapshot": snapshot or None,
            "windows": [window for window in windows if FIELDS.keys() & window.keys()]}


def import_windows(conn: sqlite3.Connection, aid: int, path: Path) -> int:
    bounds = conn.execute("SELECT min(ts), max(ts) FROM fit_records WHERE activity_id=?",
                          (aid,)).fetchone()
    from garmin_mcp.loads import RUN_TYPES

    activity = conn.execute("SELECT type FROM activities WHERE activity_id=?", (aid,)).fetchone()
    if not activity or activity[0] not in RUN_TYPES or not bounds[0]:
        raise ValueError("choose an outdoor run with a local FIT timeline")
    windows = _read_windows(path, _stored_time(bounds[0]), _stored_time(bounds[1]),
                            FIELDS, ("observation", "model"))
    db.put_activity_detail(conn, aid, DETAIL_KIND, windows)
    return len(windows)


def _stored_time(timestamp: str) -> datetime:
    parsed = datetime.fromisoformat(timestamp)
    return parsed.replace(tzinfo=parsed.tzinfo or UTC).astimezone(UTC)


def sleep_interval(conn: sqlite3.Connection, day: str) -> tuple[datetime, datetime] | None:
    row = conn.execute("SELECT sleep_start, sleep_end FROM sleep WHERE day=? AND sleep_s>=10800",
                       (day,)).fetchone()
    if not row or not all(row):
        return None
    try:
        first, last = (_stored_time(ts) for ts in row)
    except ValueError:
        return None
    return (first, last) if first < last else None


def import_bedroom(conn: sqlite3.Connection, day: str, path: Path, energy: int | None = None) -> int:
    span = sleep_interval(conn, day)
    if not span:
        raise ValueError("choose a recorded wake date with both sleep start and end")
    if energy is not None and not 1 <= energy <= 5:
        raise ValueError("morning energy must be between 1 and 5")
    windows = _read_windows(path, *span, BEDROOM_FIELDS, ("observation",))
    db.put_daily(conn, BEDROOM_DATASET, day, "local_bedroom",
                 {"windows": windows, "morning_energy": energy})
    return len(windows)


def _read_windows(path: Path, first: datetime, last: datetime, fields: dict,
                  kinds: tuple[str, ...]) -> list[dict]:
    windows = []
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required = {"start_utc", "end_utc", "source", "kind"}
        allowed = required | fields.keys()
        if "aqi" in fields:
            allowed |= {"aqi_standard"}
        headers = reader.fieldnames or []
        if not required <= set(headers) <= allowed or len(headers) != len(set(headers)):
            raise ValueError("use the documented columns, including start_utc,end_utc,source,kind")
        for row in reader:
            line = reader.line_num
            try:
                if None in row or None in row.values():
                    raise ValueError("wrong number of fields")
                start, end = _utc(row["start_utc"]), _utc(row["end_utc"])
                if not start < end:
                    raise ValueError("the end must follow the start")
                source, kind = _text(row["source"]), row["kind"].strip()
                if not source or kind not in kinds:
                    raise ValueError(f"provide a source and an allowed kind ({', '.join(kinds)})")
                window = {"start_utc": start.isoformat(), "end_utc": end.isoformat(),
                          "source": source, "kind": kind}
                for name, limits in fields.items():
                    if raw := row.get(name, "").strip():
                        value = _value(float(raw), limits)
                        if value is None or (name == "aqi" and not value.is_integer()):
                            raise ValueError(f"invalid {name}")
                        window[name] = value
                standard = row.get("aqi_standard", "").strip()
                if "aqi" in window:
                    if standard not in AQI_STANDARDS:
                        raise ValueError("with AQI, specify IN-CPCB or US-EPA")
                    window["aqi_standard"] = standard
                elif standard:
                    raise ValueError("an AQI standard requires an AQI value")
                if not fields.keys() & window.keys():
                    raise ValueError("provide at least one reading")
                if end > first and start <= last:
                    windows.append(window)
                if line > MAX_ROWS + 1:
                    raise ValueError(f"keep the file within {MAX_ROWS} data rows")
            except ValueError as error:
                raise ValueError(f"CSV line {line}: {error}") from error
    if not windows:
        raise ValueError("no observation window overlaps the recorded interval")
    windows.sort(key=lambda window: _utc(window["start_utc"]))
    if any(_utc(a["end_utc"]) > _utc(b["start_utc"]) for a, b in pairwise(windows)):
        raise ValueError("overlapping windows need to be resolved in the source file")
    return windows


def for_samples(start_utc: str | None, samples: list[dict], context: dict) -> dict[int, dict]:
    """Join half-open windows to actual FIT times. Uncovered samples have no context."""
    windows = context["windows"]
    if not windows or not start_utc:
        return {}
    start = _utc(start_utc).timestamp()
    spans = [(_utc(w["start_utc"]).timestamp(), _utc(w["end_utc"]).timestamp(), w) for w in windows]
    out = {}
    index = 0
    for sample in samples:
        second = sample["t_s"]
        instant = start + second
        while index < len(spans) and spans[index][1] <= instant:
            index += 1
        if index == len(spans):
            break
        if spans[index][0] <= instant:
            out[second] = spans[index][2]
    return out


def main() -> None:
    from garmin_mcp.config import db_path

    parser = argparse.ArgumentParser(description="Manage optional workout or measured bedroom conditions.")
    parser.add_argument("activity_id", type=int, nargs="?")
    parser.add_argument("--night", type=date.fromisoformat, help="Recorded local wake date")
    parser.add_argument("--morning-energy", type=int, choices=range(1, 6))
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--csv", type=Path)
    options.add_argument("--clear", action="store_true")
    args = parser.parse_args()
    if (args.activity_id is None) == (args.night is None):
        parser.error("provide either an activity ID or --night YYYY-MM-DD")
    if args.morning_energy is not None and (args.night is None or args.clear):
        parser.error("--morning-energy can only accompany a bedroom import")
    load_dotenv()
    try:
        with closing(db.connect(db_path())) as conn, conn:
            if args.night is not None:
                day = args.night.isoformat()
                if args.clear:
                    conn.execute("DELETE FROM raw_daily WHERE dataset=? AND day=?",
                                 (BEDROOM_DATASET, day))
                    print("Removed local bedroom conditions and morning check-in.")
                else:
                    count = import_bedroom(conn, day, args.csv, args.morning_energy)
                    print(f"Saved {count} measured bedroom interval(s).")
            elif args.clear:
                cursor = conn.execute("DELETE FROM activity_details WHERE activity_id=? AND kind=?",
                                      (args.activity_id, DETAIL_KIND))
                print(f"Removed {cursor.rowcount} local conditions record(s).")
            else:
                count = import_windows(conn, args.activity_id, args.csv)
                print(f"Saved {count} observation window(s).")
            conn.execute("INSERT OR REPLACE INTO meta VALUES ('dashboard_rebuild_pending','1')")
    except (OSError, ValueError, csv.Error, sqlite3.Error) as error:
        parser.exit(2, f"{error}\n")
