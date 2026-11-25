"""Bounded calendar detail from the same stored Garmin summaries as the dashboard."""

from __future__ import annotations

import json
import math
import sqlite3
import statistics
from datetime import date, datetime, timedelta, tzinfo
from typing import Any

from garmin_mcp import baseline, health, insights, normalize, recovery, wellness_timeline

_DAILY_NUMBERS = frozenset(normalize.TABLES["daily"])
_SLEEP_NUMBERS = frozenset(normalize.TABLES["sleep"]) - {"sleep_start", "sleep_end"}


def _intraday_pulse(conn: sqlite3.Connection, start: str, end: str, zone: tzinfo) -> dict[str, dict]:
    output = {}
    ranks = {}
    rows = conn.execute(
        "SELECT day, dataset, payload FROM raw_daily WHERE day BETWEEN ? AND ? "
        "AND dataset IN ('pa_heart_rate','heart_rate')", (start, end))
    for day, dataset, raw in rows:
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        local_zone = wellness_timeline.device_zone(payload, zone)
        unique: dict[float, float] = {}
        samples = payload.get("heartRateValues", []) if isinstance(payload, dict) else []
        if not isinstance(samples, list):
            continue
        for entry in samples:
            if not isinstance(entry, list) or len(entry) < 2:
                continue
            stamp, bpm = entry[:2]
            if not all(type(v) in (int, float) and math.isfinite(v) and v > 0
                       for v in (stamp, bpm)):
                continue
            try:
                local = datetime.fromtimestamp(stamp / 1000, local_zone)
            except (ValueError, OSError, OverflowError):
                continue
            if bpm <= 300 and local.date().isoformat() == day:
                unique.setdefault(stamp, bpm)
        buckets: dict[float, list[float]] = {}
        for stamp, bpm in sorted(unique.items()):
            local = datetime.fromtimestamp(stamp / 1000, local_zone)
            start_slot = local.replace(minute=local.minute // 15 * 15, second=0, microsecond=0)
            buckets.setdefault(start_slot.timestamp(), []).append(bpm)
        if buckets:
            # Rank by recorded time coverage, then freshness. Sample frequency
            # inside each 15-minute window does not give a source more weight.
            rank = (len(buckets), max(unique), dataset == "pa_heart_rate")
            if day in ranks and ranks[day] >= rank:
                continue
            slots = []
            for stamp, values in buckets.items():
                local = datetime.fromtimestamp(stamp, local_zone)
                label = local.strftime("%H:%M")
                if local.replace(fold=0).utcoffset() != local.replace(fold=1).utcoffset():
                    label += local.strftime(" %z")
                slots.append({"time": label, "minute": stamp / 60, "median": statistics.median(values),
                              "range": (min(values), max(values)), "count": len(values)})
            output[day] = {"slots": slots, "samples": len(unique), "dataset": dataset}
            ranks[day] = rank

    return output


def _prior_values(days, day, field, section="daily"):
    start = date.fromisoformat(day)
    return [value for offset in range(1, 29)
            if (value := days.get((start - timedelta(days=offset)).isoformat(), {})
                .get(section, {}).get(field)) is not None and baseline._within(value, -math.inf, math.inf)]


def _personal_reference(value, baseline, minimum_radius):
    if len(baseline) < 14:
        return {"median": None, "count": len(baseline), "range": None, "direction": None}
    center = statistics.median(baseline)
    spread = 1.4826 * statistics.median(abs(v - center) for v in baseline)
    radius = max(minimum_radius, 3 * spread)
    direction = "lower" if value < center - radius else "higher" if value > center + radius else "near"
    return {"median": center, "count": len(baseline), "range": (center - radius, center + radius),
            "direction": direction}


def _day_highlights(days, day, row):
    candidates = []
    for section, field, label, unit, factor, minimum_radius, low, high in (
        ("sleep", "sleep_s", "Sleep duration", " h", 3600, .5, 10800, 86400),
        ("daily", "steps", "Steps", " steps", 1, 1500, 0, math.inf),
        ("daily", "stress_avg", "Garmin daytime stress", "/100", 1, 8, 0, 100),
    ):
        value = row.get(section, {}).get(field)
        if not baseline._within(value, low, high):
            continue
        value /= factor
        prior = [v / factor for v in _prior_values(days, day, field, section) if low <= v <= high]
        ref = _personal_reference(value, prior, minimum_radius)
        if ref["direction"] in {"lower", "higher"}:
            center = ref["median"]
            radius = (ref["range"][1] - ref["range"][0]) / 2
            candidates.append((abs(value - center) / radius,
                               {"label": label, "unit": unit, "value": value, **ref}))
    return [match for _, match in sorted(candidates, key=lambda item: item[0], reverse=True)]


def resting_pulse_checks(conn, days, start, end, archive_start, archive_pulse):
    sources = baseline.resting_pulse_sources(conn, start, end)
    checks = {}
    for day, row in days.items():
        if not start <= day <= end:
            continue
        value = row.get("daily", {}).get("resting_hr")
        if not baseline._within(value, 1, 300):
            continue
        earlier = date.fromisoformat(day) - timedelta(days=28)
        recent = [v for d, v in archive_pulse.items() if earlier.isoformat() <= d < day]
        ref = _personal_reference(value, recent, 5)
        checks[day] = {"value": value, **ref,
                       "verify": value < 50 or ref["direction"] in {"lower", "higher"},
                       "sources": {dataset: tuple(sorted(values))
                                   for dataset, values in sources.get(day, {}).items()},
                       "coverage": baseline.windows(archive_pulse, day, archive_start)}
    return checks


def _history_values(row, numeric_fields):
    return {key: value if key not in numeric_fields or baseline._within(value, -math.inf, math.inf)
            else None for key, value in dict(row).items()}


def collect(conn: sqlite3.Connection, end: str, zone: tzinfo) -> dict[str, Any]:
    last = date.fromisoformat(end)
    first_month = last.replace(day=1)
    previous_month = (first_month - timedelta(days=1)).isoformat()[:7]
    months = health.monthly_history(conn, previous_month, count=12)
    start = months[0]["month"] + "-01"
    days: dict[str, dict] = {}
    for row in conn.execute("SELECT * FROM daily WHERE day BETWEEN ? AND ?", (start, end)):
        days.setdefault(row["day"], {})["daily"] = _history_values(row, _DAILY_NUMBERS)
    for row in conn.execute("SELECT * FROM sleep WHERE day BETWEEN ? AND ?", (start, end)):
        days.setdefault(row["day"], {})["sleep"] = _history_values(row, _SLEEP_NUMBERS)
    for day, value in recovery.nightly_hrv(conn, start, end).items():
        days.setdefault(day, {})["hrv"] = value
    span = (last - date.fromisoformat(start)).days + 1
    for activity in insights.recent_activities(conn, days=span, end=end)["activities"]:
        days.setdefault(activity["start"][:10], {}).setdefault("activities", []).append(activity)
    detail_start = (last - timedelta(days=29)).isoformat()
    week_start = (last - timedelta(days=6)).isoformat()
    for day, pulse in _intraday_pulse(conn, week_start, end, zone).items():
        days.setdefault(day, {})["intraday_hr"] = pulse
    for day, wellness in wellness_timeline.collect(conn, week_start, end, zone):
        days.setdefault(day, {})["intraday_wellness"] = wellness
    archive_start, series = baseline.collect(conn, end)
    pulse_checks = resting_pulse_checks(conn, days, detail_start, end, archive_start, series["resting_hr"])
    coverage = {key: baseline.windows(values, end, archive_start) for key, values in series.items()}
    for day, check in pulse_checks.items():
        days[day]["resting_pulse_check"] = check
    for day, row in days.items():
        if day < detail_start or day == end:
            continue
        row["highlights"] = _day_highlights(days, day, row)
        steps = [v for v in _prior_values(days, day, "steps") if v >= 0]
        if len(steps) >= 14:
            row["steps_typical"] = round(statistics.median(steps))
    detail_days = sorted(day for day in days if day >= detail_start)
    by_month: dict[str, list[str]] = {}
    for day in sorted(days, reverse=True):
        by_month.setdefault(day[:7], []).append(day)
    return {"days": days, "months": months, "by_month": by_month, "baseline_coverage": coverage,
            "week": [day for day in sorted(days, reverse=True) if week_start <= day],
            "current_month": first_month.isoformat()[:7], "week_start": week_start,
            "detail_days": detail_days, "detail_start": detail_start}
