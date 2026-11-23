"""Personal chart context and comparisons of non-overlapping weeks."""

from __future__ import annotations

import math
import sqlite3
import statistics
from datetime import date, timedelta
from typing import Any

from garmin_mcp import health, recovery

BASELINE_DAYS = 60
WEEK_MINIMUM = 4
SIGNALS = {
    "resting_hr": ("Resting heart rate", "bpm", 21),
    "sleep_spo2": ("Overnight Pulse Ox", "%", 14),
    "sleep_resp": ("Overnight breathing rate", "breaths/min", 14),
    "sleep_h": ("Sleep duration", "h", 14),
}


def _valid(key: str, value: float | None) -> bool:
    return (isinstance(value, (int, float)) and math.isfinite(value)
            and 0 < value <= (100 if key == "sleep_spo2" else math.inf))


def _compare(values: dict[str, float], day: str, minimum: int,
             excluded: set[str], ceiling: float) -> dict[str, Any]:
    dates = recovery._days_back(day, BASELINE_DAYS + 7)
    current = [values[d] for d in dates[-7:] if d in values]
    previous = [values[d] for d in dates[-14:-7] if d in values]
    baseline = [values[d] for d in dates[:-7] if d in values and d not in excluded]
    recent = statistics.fmean(current) if len(current) >= WEEK_MINIMUM else None
    prior = statistics.fmean(previous) if len(previous) >= WEEK_MINIMUM else None
    band = None
    if len(baseline) >= minimum:
        mean, sd = statistics.fmean(baseline), statistics.stdev(baseline)
        if sd > 0:
            band = (max(0, mean - sd), min(ceiling, mean + sd))
    state = ("above" if recent > band[1] else "below" if recent < band[0] else "within"
             ) if band and recent is not None else None
    return {"recent": recent, "previous": prior,
            "delta": recent - prior if recent is not None and prior is not None else None,
            "recent_count": len(current), "previous_count": len(previous),
            "baseline_count": len(baseline), "baseline": band, "state": state}


def collect(conn: sqlite3.Connection, end: str, days: int = 60,
            *, with_history: bool = True) -> dict[str, Any]:
    first = (date.fromisoformat(end) - timedelta(days=days + BASELINE_DAYS + 6)).isoformat()
    series: dict[str, dict] = {key: {} for key in SIGNALS}
    for day, value in conn.execute(
            "SELECT day, resting_hr FROM daily WHERE day BETWEEN ? AND ?", (first, end)):
        if _valid("resting_hr", value):
            series["resting_hr"][day] = value
    for day, oxygen, breathing, hours in conn.execute(
            "SELECT day, avg_spo2, avg_respiration, sleep_s/3600.0 FROM sleep "
            "WHERE day BETWEEN ? AND ? AND sleep_s>=3*3600", (first, end)):
        for key, value in (("sleep_spo2", oxygen), ("sleep_resp", breathing), ("sleep_h", hours)):
            if _valid(key, value):
                series[key][day] = value
    excluded = set(health.status_days(conn))
    visible = recovery._days_back(end, days)
    out = {}
    for key, values in series.items():
        label, unit, minimum = SIGNALS[key]
        ceiling = 100 if key == "sleep_spo2" else math.inf
        latest = max(values, default=None)
        summary = _compare(values, end, minimum, excluded, ceiling)
        summary.update(label=label, unit=unit, latest_day=latest,
                       latest=values[latest] if latest else None)
        if with_history:
            summary["days"] = []
            for day in visible:
                point = summary if day == end else _compare(values, day, minimum, excluded, ceiling)
                summary["days"].append({"day": day, "value": values.get(day),
                                        "average": point["recent"], "range": point["baseline"]})
        out[key] = summary
    return out


def describe(key: str, state: str | None) -> str:
    """Context for a reading without a diagnostic threshold or a predicted outcome."""
    if key == "resting_hr":
        return {
            "above": "Check recent training and sleep. Stress and illness can also raise resting pulse.",
            "below": "A lower pulse can accompany fitness or rest. Consider how you feel as well.",
        }.get(state, "Compare resting pulse with your own history and how you feel.")
    if key == "sleep_spo2":
        return {
            "below": "Recheck watch fit and look for a repeat. Altitude and the sensor can affect readings.",
            "above": "Watch fit and altitude can affect this. Compare repeated readings in similar conditions.",
        }.get(state, "Wrist Pulse Ox is an estimate. Watch fit and altitude can affect readings.")
    if key == "sleep_resp":
        return "Compare nights with similar sleep conditions. Congestion, altitude and the sensor can shift readings."
    if state == "below":
        return "Check whether later bedtimes or earlier wake times shortened your sleep."
    return "Compare with Garmin sleep need or your planning target, as well as your usual hours."
