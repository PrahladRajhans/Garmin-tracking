"""Describe comparable workouts and measured bedroom nights using local conditions."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from statistics import median

from garmin_mcp import conditions

MIN_INTERVAL_COVERAGE = 0.8
MIN_EARLIER_RUNS = 3
MIN_PER_NIGHT_GROUP = 6
METRICS = {
    "temperature_c": ("Temperature", "°C"),
    "humidity_pct": ("Relative humidity", "%"),
    "aqi": ("AQI", ""),
    "pm25_ug_m3": ("Fine particles (PM₂.₅)", "µg/m³"),
}


def _observed(windows: list[dict], span: tuple, field: str) -> dict | None:
    """Use one observation source and return its time-weighted median over the covered intervals."""
    first, last = span
    seconds = (last - first).total_seconds()
    if seconds <= 0:
        return None
    samples = defaultdict(list)
    for item in windows:
        if item["kind"] != "observation" or field not in item:
            continue
        left = max(first, conditions._utc(item["start_utc"]))
        right = min(last, conditions._utc(item["end_utc"]))
        if left < right:
            key = (item["source"], item.get("aqi_standard") if field == "aqi" else None)
            samples[key].append((item[field], (right - left).total_seconds()))
    for (source, standard), values in samples.items():
        covered = sum(weight for _, weight in values)
        if covered < seconds * MIN_INTERVAL_COVERAGE:
            continue
        elapsed = 0
        for value, weight in sorted(values):
            elapsed += weight
            if elapsed >= covered / 2:
                return {"value": value, "coverage_pct": round(100 * covered / seconds, 1),
                        "source": source, "standard": standard}
    return None


def _run_observations(conn: sqlite3.Connection, aid: int) -> dict[str, dict]:
    windows = conditions.for_activity(conn, aid)["windows"]
    if not windows:
        return {}
    bounds = conn.execute("SELECT min(ts), max(ts) FROM fit_records WHERE activity_id=?",
                          (aid,)).fetchone()
    if not bounds[0]:
        return {}
    span = tuple(conditions._stored_time(t) for t in bounds)
    return {key: measure for key in ("temperature_c", "humidity_pct", "aqi")
            if (measure := _observed(windows, span, key)) is not None}


def comparable_runs(conn: sqlite3.Connection, comparison: dict) -> list[dict]:
    if not comparison["available"]:
        return []
    target = comparison["this_run"]
    current = _run_observations(conn, target["activity_id"])
    if not current:
        return []
    earlier = [(run, _run_observations(conn, run["activity_id"])) for run in comparison["matches"]]
    out = []
    for key, value in current.items():
        samples = []
        for run, observations in earlier:
            previous = observations.get(key)
            if (previous is not None and previous["source"] == value["source"]
                    and previous["standard"] == value["standard"]):
                samples.append({**previous, "activity_id": run["activity_id"],
                                "start_local": run["start_local"], "hr_bpm": run["avg_hr_bpm"]})
        if len(samples) >= MIN_EARLIER_RUNS:
            label, unit = METRICS[key]
            out.append({"metric": key, "label": label, "unit": unit,
                        "recorded": {**value, "hr_bpm": target["avg_hr_bpm"]},
                        "earlier_value": median(p["value"] for p in samples),
                        "earlier_hr_bpm": median(p["hr_bpm"] for p in samples),
                        "earlier_runs": samples})
    return out


def bedroom(conn: sqlite3.Connection, end: str, days: int = 180) -> dict:
    first = (date.fromisoformat(end) - timedelta(days=days - 1)).isoformat()
    by_metric = defaultdict(list)
    imports = 0
    for day, payload in conn.execute(
            "SELECT day,payload FROM raw_daily WHERE dataset=? AND day BETWEEN ? AND ? ORDER BY day",
            (conditions.BEDROOM_DATASET, first, end)):
        imports += 1
        span = conditions.sleep_interval(conn, day)
        if not span:
            continue
        data = json.loads(payload)
        hours = conn.execute("SELECT sleep_s/3600.0 FROM sleep WHERE day=?", (day,)).fetchone()[0]
        for key in conditions.BEDROOM_FIELDS:
            if observation := _observed(data["windows"], span, key):
                by_metric[key, observation["source"]].append(
                    {"date": day, "sleep_h": hours, "morning_energy": data.get("morning_energy"),
                     "value": observation["value"], "coverage_pct": observation["coverage_pct"]})

    groups = []
    for (key, source), records in by_metric.items():
        if len(records) < 2 * MIN_PER_NIGHT_GROUP:
            continue
        if (date.fromisoformat(records[-1]["date"]) - date.fromisoformat(records[0]["date"])).days < 14:
            continue
        cut = median(p["value"] for p in records)
        lower = [p for p in records if p["value"] < cut]
        higher = [p for p in records if p["value"] > cut]
        if min(len(lower), len(higher)) < MIN_PER_NIGHT_GROUP:
            continue
        label, unit = METRICS[key]
        groups.append({"metric": key, "label": label, "unit": unit, "source": source,
                       "cut": cut, "lower": _night_summary(lower), "higher": _night_summary(higher)})
    return {"available": bool(groups), "imported_nights": imports, "groups": groups}


def _night_summary(rows: list[dict]) -> dict:
    scores = [row["morning_energy"] for row in rows if row["morning_energy"] is not None]
    return {"nights": rows, "sleep_h": median(row["sleep_h"] for row in rows),
            "conditions": median(row["value"] for row in rows), "energy_samples": len(scores),
            "morning_energy": median(scores) if len(scores) >= 4 else None}
