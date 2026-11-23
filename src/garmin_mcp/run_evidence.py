"""Auditable like-for-like effort comparisons between recorded outdoor runs."""

from __future__ import annotations

import math
import sqlite3
import statistics
from collections.abc import Callable
from typing import Any

from garmin_mcp.loads import RUN_TYPES

LOOKBACK_DAYS = 180
MAX_MATCHES = 8
MIN_MATCHES = 3
PACE_WINDOW_S = 15
DURATION_WINDOW = 0.20
CLIMB_WINDOW_M_KM = 5


def _climb(distance: float | None, ascent: float | None) -> float | None:
    if (distance and ascent is not None and math.isfinite(distance) and math.isfinite(ascent)
            and distance > 0 and ascent >= 0):
        return 1000 * ascent / distance
    return None


def _usable(metrics: dict | None) -> bool:
    return bool(metrics and metrics["steady"] and metrics["avg_hr"] is not None
                and metrics["moving_s"] >= 0.8 * metrics["recorded_elapsed_s"])


def matched_effort(conn: sqlite3.Connection, aid: int, metrics: dict,
                   read_metrics: Callable[[sqlite3.Connection, int], dict | None]
                   ) -> dict[str, Any]:
    """Compare moving HR at similar pace, duration and recorded climb per kilometre."""
    result: dict[str, Any] = {"available": False, "matches": [], "minimum_matches": MIN_MATCHES,
                              "lookback_days": LOOKBACK_DAYS, "maximum_matches": MAX_MATCHES,
                              "pace_window_s_per_km": PACE_WINDOW_S,
                              "duration_window_pct": round(DURATION_WINDOW * 100),
                              "climb_window_m_per_km": CLIMB_WINDOW_M_KM}
    target = conn.execute("SELECT type, distance_m, elevation_gain_m FROM activities "
                          "WHERE activity_id=?", (aid,)).fetchone()
    if not target or target[0] not in RUN_TYPES:
        return {**result, "reason": "This comparison is for outdoor runs."}
    if not _usable(metrics):
        return {**result, "reason": "This run needs at least 20 steady moving minutes, "
                "good heart-rate coverage and limited stops or recording gaps."}
    climb = _climb(target[1], target[2])
    if climb is None:
        return {**result, "reason": "Garmin distance and ascent are needed to match climbing."}
    pace, duration = 1000 / metrics["avg_speed"], metrics["moving_s"]
    # Prefer absolute time when both workouts have it. Older exports may have only local time.
    earlier = """CASE WHEN julianday(a.start_time_gmt) IS NOT NULL
                        AND julianday(b.start_time_gmt) IS NOT NULL
                   THEN julianday(b.start_time_gmt) - julianday(a.start_time_gmt)
                   ELSE julianday(b.start_time_local) - julianday(a.start_time_local) END"""
    rows = conn.execute(
        f"SELECT a.activity_id, a.start_time_local, a.distance_m, a.elevation_gain_m, ({earlier}) "
        f"FROM activities a JOIN activities b ON b.activity_id=? "
        f"WHERE a.type=b.type AND a.fit_parsed=1 AND a.activity_id<>b.activity_id "
        f"AND julianday(a.start_time_local) IS NOT NULL "
        f"AND ({earlier})>0 AND ({earlier})<=? ORDER BY ({earlier}), a.activity_id DESC",
        (aid, LOOKBACK_DAYS))
    result["this_run"] = {"activity_id": aid, "pace_s_per_km": round(pace, 1),
                          "moving_s": duration, "climb_m_per_km": round(climb, 1),
                          "avg_hr_bpm": metrics["avg_hr"]}
    matches = result["matches"]
    for other_id, start, distance, ascent, days_before in rows:
        other_climb = _climb(distance, ascent)
        if other_climb is None or abs(other_climb - climb) > CLIMB_WINDOW_M_KM:
            continue
        other = read_metrics(conn, other_id)
        if not _usable(other):
            continue
        other_pace = 1000 / other["avg_speed"]
        if (abs(other["moving_s"] - duration) > DURATION_WINDOW * duration
                or abs(other_pace - pace) > PACE_WINDOW_S):
            continue
        matches.append({"activity_id": other_id, "start_local": start,
                        "pace_s_per_km": round(other_pace, 1), "moving_s": other["moving_s"],
                        "days_before": days_before,
                        "climb_m_per_km": round(other_climb, 1), "avg_hr_bpm": other["avg_hr"]})
        if len(matches) == MAX_MATCHES:
            break
    if len(matches) < MIN_MATCHES:
        return {**result, "reason": f"{len(matches)} earlier runs matched. "
                f"At least {MIN_MATCHES} are needed for a personal reference."}
    hrs = [match["avg_hr_bpm"] for match in matches]
    median = statistics.median(hrs)
    return {**result, "available": True, "median_hr_bpm": round(median, 1),
            "observed_hr_range_bpm": [min(hrs), max(hrs)],
            "difference_hr_bpm": round(metrics["avg_hr"] - median, 1)}


def headline(comparison: dict) -> str:
    if not comparison["available"]:
        return comparison["reason"]
    delta = comparison["difference_hr_bpm"]
    count = len(comparison["matches"])
    if delta == 0:
        return f"Heart rate matched your median across {count} similar runs."
    direction = "higher" if delta > 0 else "lower"
    return (f"Heart rate was {abs(delta):g} bpm {direction} than your median "
            f"across {count} similar runs.")


def next_check(comparison: dict) -> str:
    if not comparison["available"]:
        return ""
    low, high = comparison["observed_hr_range_bpm"]
    hr = comparison["this_run"]["avg_hr_bpm"]
    if low <= hr <= high:
        return f"Within the observed {low:g}–{high:g} bpm span for those runs."
    return ("Outside the observed span. Compare another similar effort and check conditions "
            "and watch fit before changing your training.")
