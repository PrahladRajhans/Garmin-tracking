"""Bounded calendar detail from the same stored Garmin summaries as the dashboard."""

from __future__ import annotations

import json
import math
import sqlite3
import statistics
from datetime import date, datetime, timedelta, tzinfo
from typing import Any

from garmin_mcp import health, insights, recovery


def _heart_rate_by_hour(conn: sqlite3.Connection, start: str, end: str,
                        zone: tzinfo) -> dict[str, list[tuple[str, float]]]:
    output = {}
    rows = conn.execute(
        "SELECT day, payload FROM raw_daily WHERE day BETWEEN ? AND ? "
        "AND dataset IN ('pa_heart_rate','heart_rate') "
        "ORDER BY day, CASE dataset WHEN 'pa_heart_rate' THEN 0 ELSE 1 END", (start, end))
    for day, raw in rows:
        if day in output or not raw:
            continue
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        buckets: dict[str, list[float]] = {}
        samples = payload.get("heartRateValues", []) if isinstance(payload, dict) else []
        if not isinstance(samples, list):
            continue
        for entry in samples:
            if not isinstance(entry, list) or len(entry) < 2:
                continue
            stamp, bpm = entry[:2]
            if not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0
                       for v in (stamp, bpm)):
                continue
            try:
                local = datetime.fromtimestamp(stamp / 1000, zone)
            except (ValueError, OSError, OverflowError):
                continue
            if local.date().isoformat() == day:
                hour = local.strftime("%H:00")
                buckets.setdefault(hour, []).append(bpm)
        if buckets:
            output[day] = [(hour, statistics.fmean(values)) for hour, values in sorted(buckets.items())]
    return output


def collect(conn: sqlite3.Connection, end: str, zone: tzinfo) -> dict[str, Any]:
    last = date.fromisoformat(end)
    first_month = last.replace(day=1)
    previous_month = (first_month - timedelta(days=1)).isoformat()[:7]
    months = health.monthly_history(conn, previous_month, count=12)
    start = months[0]["month"] + "-01"
    days: dict[str, dict] = {}
    for row in conn.execute("SELECT * FROM daily WHERE day BETWEEN ? AND ?", (start, end)):
        days.setdefault(row["day"], {})["daily"] = dict(row)
    for row in conn.execute("SELECT * FROM sleep WHERE day BETWEEN ? AND ?", (start, end)):
        days.setdefault(row["day"], {})["sleep"] = dict(row)
    for day, value in recovery.nightly_hrv(conn, start, end).items():
        days.setdefault(day, {})["hrv"] = value
    span = (last - date.fromisoformat(start)).days + 1
    for activity in insights.recent_activities(conn, days=span, end=end)["activities"]:
        days.setdefault(activity["start"][:10], {}).setdefault("activities", []).append(activity)
    detail_start = (last - timedelta(days=29)).isoformat()
    week_start = (last - timedelta(days=6)).isoformat()
    for day, pulse in _heart_rate_by_hour(conn, week_start, end, zone).items():
        days.setdefault(day, {})["hourly_hr"] = pulse
    detail_days = sorted(day for day in days if day >= detail_start)
    by_month: dict[str, list[str]] = {}
    for day in sorted(days, reverse=True):
        by_month.setdefault(day[:7], []).append(day)
    return {"days": days, "months": months, "by_month": by_month,
            "week": [day for day in sorted(days, reverse=True) if week_start <= day],
            "current_month": first_month.isoformat()[:7], "week_start": week_start,
            "detail_days": detail_days, "detail_start": detail_start}
