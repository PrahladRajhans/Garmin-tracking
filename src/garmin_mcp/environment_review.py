"""Describe comparable workouts and measured bedroom nights using local conditions."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta
from functools import lru_cache
from statistics import median

from garmin_mcp import conditions, recovery, run_evidence
from garmin_mcp.loads import RUN_TYPES

MIN_INTERVAL_COVERAGE = 0.8
MIN_EARLIER_RUNS = 3
MIN_PER_NIGHT_GROUP = 6
METRICS = {
    "temperature_c": ("Temperature", "°C"),
    "humidity_pct": ("Relative humidity", "%"),
    "aqi": ("AQI", ""),
    "pm25_ug_m3": ("Fine particles (PM₂.₅)", "µg/m³"),
}
RUN_EXPOSURES = {"temperature_c": 3, "humidity_pct": 15, "aqi": 20}
OUTCOMES = {"moving_hr": ("Moving heart rate", "bpm"), "sleep_h": ("Following sleep", "h"),
            "hrv": ("Following nightly HRV", "ms"), "rhr": ("Following day resting HR", "bpm")}
MIN_PAIRS = 6
MAX_RUNS = 60


def _covered(windows: list[dict], span: tuple, field: str, kind: str) -> dict | None:
    """Return the coverage and time-weighted median for one source and reading type."""
    first, last = span
    seconds = (last - first).total_seconds()
    if seconds <= 0:
        return None
    samples = defaultdict(list)
    for item in windows:
        if item["kind"] != kind or field not in item:
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
                        "source": source, "standard": standard, "kind": kind}
    return None


def _run_conditions(conn: sqlite3.Connection, aid: int) -> tuple[tuple | None, dict]:
    windows = conditions.for_activity(conn, aid)["windows"]
    if not windows:
        return None, {}
    bounds = conn.execute("SELECT min(ts), max(ts) FROM fit_records WHERE activity_id=?",
                          (aid,)).fetchone()
    if not bounds[0]:
        return None, {}
    span = tuple(conditions._stored_time(t) for t in bounds)
    values = {}
    for key in RUN_EXPOSURES:
        value = _covered(windows, span, key, "observation") or _covered(windows, span, key, "model")
        if value is not None:
            values[key] = value
    return span, values


def _provenance(reading: dict) -> tuple:
    return reading["kind"], reading["source"], reading["standard"]


def comparable_runs(conn: sqlite3.Connection, comparison: dict) -> list[dict]:
    if not comparison["available"]:
        return []
    target = comparison["this_run"]
    _, current = _run_conditions(conn, target["activity_id"])
    if not current:
        return []
    earlier = [(run, _run_conditions(conn, run["activity_id"])[1])
               for run in comparison["matches"]]
    out = []
    for key, value in current.items():
        samples = []
        for run, observations in earlier:
            previous = observations.get(key)
            if previous is not None and _provenance(previous) == _provenance(value):
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
            if observation := _covered(data["windows"], span, key, "observation"):
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


def _outdoor_record(conn, aid, local_start, end, signals) -> dict | None:
    span, readings = _run_conditions(conn, aid)
    if not readings:
        return None
    point = conn.execute(
        "SELECT lat,lon FROM fit_records WHERE activity_id=? AND lat BETWEEN -90 AND 90 "
        "AND lon BETWEEN -180 AND 180 ORDER BY ts LIMIT 1", (aid,)).fetchone()
    if not point:
        return None
    local = datetime.fromisoformat(local_start)
    wake = (local.date() + timedelta(days=1)).isoformat()
    following = {}
    night = conditions.sleep_interval(conn, wake) if wake <= end else None
    if night and span[1] <= night[0] <= span[1] + timedelta(hours=24):
        following = {key: signals[key][wake] for key in ("sleep_h", "hrv", "rhr")
                     if wake in signals[key] and signals[key][wake] > 0}
    return {"id": aid, "day": local.date().isoformat(), "start_min": local.hour * 60 + local.minute,
            "cell": tuple(round(n, 2) for n in point), "readings": readings,
            "wake": wake if following else None, "outcomes": following}


def outdoor_patterns(conn: sqlite3.Connection, end: str, read_metrics=None) -> dict:
    """Describe within-person matched pairs, with a separate sample count for each outcome."""
    from garmin_mcp.coaching import run_metrics
    from garmin_mcp.health import status_days

    first = (date.fromisoformat(end) - timedelta(days=run_evidence.LOOKBACK_DAYS - 1)).isoformat()
    placeholders = ",".join("?" for _ in RUN_TYPES)
    rows = conn.execute(
        f"SELECT a.activity_id,a.start_time_local FROM activity_details AS d "
        f"JOIN activities AS a USING (activity_id) "
        f"WHERE d.kind=? AND a.fit_parsed=1 AND a.type IN ({placeholders}) "
        f"AND substr(a.start_time_local,1,10) BETWEEN ? AND ? "
        f"AND julianday(a.start_time_local) IS NOT NULL "
        f"AND (SELECT count(*) FROM activities b WHERE substr(b.start_time_local,1,10)"
        f"=substr(a.start_time_local,1,10))=1 ORDER BY a.start_time_local DESC LIMIT ?",
        (conditions.DETAIL_KIND, *RUN_TYPES, first, end, MAX_RUNS)).fetchall()
    result = {"sampled_runs": len(rows), "minimum_pairs": MIN_PAIRS, "patterns": []}
    if len(rows) < 2 * MIN_PAIRS:
        return result
    read_metrics = read_metrics or lru_cache(maxsize=160)(run_metrics)
    signals = recovery.load_series(conn, end, run_evidence.LOOKBACK_DAYS)
    skipped = set(status_days(conn))
    for series in signals.values():
        for day in skipped:
            series.pop(day, None)
    runs = {}
    for aid, start in rows:
        if start[:10] not in skipped and (record := _outdoor_record(conn, aid, start, end, signals)):
            runs[aid] = record

    # Match without consulting the health outcomes. Count each run day once per exposure.
    picked = defaultdict(list)
    used = defaultdict(set)
    for aid, this_run in runs.items():
        metrics = read_metrics(conn, aid)
        if not run_evidence._usable(metrics):
            continue
        effort = run_evidence.matched_effort(conn, aid, metrics, read_metrics)
        for metric, current in this_run["readings"].items():
            basis = (metric, *_provenance(current))
            if this_run["day"] in used[basis]:
                continue
            for match in effort["matches"]:
                earlier = runs.get(match["activity_id"])
                if not earlier or earlier["day"] in used[basis] or match["days_before"] > 42:
                    continue
                minutes = abs(earlier["start_min"] - this_run["start_min"])
                if earlier["cell"] != this_run["cell"] or min(minutes, 1440 - minutes) > 180:
                    continue
                previous = earlier["readings"].get(metric)
                if (previous is None or _provenance(previous) != _provenance(current)
                        or abs(current["value"] - previous["value"]) < RUN_EXPOSURES[metric]):
                    continue
                comparison = [_pair_member(this_run, current, metrics["avg_hr"]),
                              _pair_member(earlier, previous, match["avg_hr_bpm"])]
                lower, higher = sorted(comparison, key=lambda member: member["exposure"])
                picked[basis].append({"lower": lower, "higher": higher})
                used[basis].update((this_run["day"], earlier["day"]))
                break

    for (metric, kind, source, standard), pairs in picked.items():
        outcomes = []
        for key, (label, unit) in OUTCOMES.items():
            valid = [pair for pair in pairs if all(key in x["outcomes"] for x in pair.values())]
            if len(valid) < MIN_PAIRS:
                continue
            days = [x["day"] for pair in valid for x in pair.values()]
            if (date.fromisoformat(max(days)) - date.fromisoformat(min(days))).days < 14:
                continue
            changes = [p["higher"]["outcomes"][key] - p["lower"]["outcomes"][key] for p in valid]
            outcomes.append({"key": key, "label": label, "unit": unit, "pairs": len(valid),
                             "median_delta": round(median(changes), 1)})
        if outcomes:
            label, unit = METRICS[metric]
            result["patterns"].append({"metric": metric, "label": label, "unit": unit,
                                       "kind": kind, "source": source, "standard": standard,
                                       "outcomes": outcomes, "pairs": pairs})
    return result


def _pair_member(run, reading, moving_hr):
    return {"activity_id": run["id"], "day": run["day"], "wake_day": run["wake"],
            "exposure": reading["value"], "coverage_pct": reading["coverage_pct"],
            "outcomes": {"moving_hr": moving_hr, **run["outcomes"]}}
