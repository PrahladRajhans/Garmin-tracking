"""Read saved activity weather and optionally join locally supplied observation windows."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from datetime import UTC, datetime
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
    return {"garmin_snapshot": snapshot or None,
            "windows": _payload(conn, aid, DETAIL_KIND) or []}


def import_windows(conn: sqlite3.Connection, aid: int, path: Path) -> int:
    bounds = conn.execute("SELECT min(ts), max(ts) FROM fit_records WHERE activity_id=?",
                          (aid,)).fetchone()
    from garmin_mcp.loads import RUN_TYPES

    activity = conn.execute("SELECT type FROM activities WHERE activity_id=?", (aid,)).fetchone()
    if not activity or activity[0] not in RUN_TYPES or not bounds[0]:
        raise ValueError("choose an outdoor run with a local FIT timeline")
    first, last = (datetime.fromisoformat(ts) for ts in bounds)
    first = first.replace(tzinfo=first.tzinfo or UTC).astimezone(UTC)
    last = last.replace(tzinfo=last.tzinfo or UTC).astimezone(UTC)
    windows = []
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required = {"start_utc", "end_utc", "source", "kind"}
        allowed = required | FIELDS.keys() | {"aqi_standard"}
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
                if not source or kind not in ("observation", "model"):
                    raise ValueError("provide a source and kind (observation or model)")
                window = {"start_utc": start.isoformat(), "end_utc": end.isoformat(),
                          "source": source, "kind": kind}
                for name, limits in FIELDS.items():
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
                if not FIELDS.keys() & window.keys():
                    raise ValueError("provide at least one reading")
                if end > first and start <= last:
                    windows.append(window)
                if line > MAX_ROWS + 1:
                    raise ValueError(f"keep the file within {MAX_ROWS} data rows")
            except ValueError as error:
                raise ValueError(f"CSV line {line}: {error}") from error
    if not windows:
        raise ValueError("no observation window intersects this activity")
    windows.sort(key=lambda window: _utc(window["start_utc"]))
    if any(_utc(a["end_utc"]) > _utc(b["start_utc"]) for a, b in pairwise(windows)):
        raise ValueError("overlapping windows need to be resolved in the source file")
    db.put_activity_detail(conn, aid, DETAIL_KIND, windows)
    return len(windows)


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

    parser = argparse.ArgumentParser(description="Manage optional local workout weather and AQI.")
    parser.add_argument("activity_id", type=int)
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--csv", type=Path)
    options.add_argument("--clear", action="store_true")
    args = parser.parse_args()
    load_dotenv()
    conn = db.connect(db_path())
    try:
        with conn:
            if args.clear:
                cursor = conn.execute("DELETE FROM activity_details WHERE activity_id=? AND kind=?",
                                      (args.activity_id, DETAIL_KIND))
                print(f"Removed {cursor.rowcount} local conditions record(s).")
            else:
                count = import_windows(conn, args.activity_id, args.csv)
                print(f"Saved {count} observation window(s). Rebuild the dashboard to view them.")
    except (OSError, ValueError, csv.Error) as error:
        parser.exit(2, f"{error}\n")
    finally:
        conn.close()
