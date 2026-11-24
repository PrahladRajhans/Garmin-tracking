"""Goal reality check (ROADMAP 6.2).

Compares a saved goal race with current predictions. The verdict bands are heuristics and are
labelled as such; the required VDOT is computed exactly (Daniels & Gilbert) so the gap is
expressed in fitness units, not only time.
"""

from __future__ import annotations

import math
import sqlite3
from datetime import date
from typing import Any

from garmin_mcp import athlete, loads

# Weekly running volume often recommended for completing/racing a distance (coaching rules of
# thumb, not research thresholds).
VOLUME_HINT_KM = {5: (15, 25), 10: (20, 35), 21.1: (30, 45), 42.2: (45, 70)}


def _parse_time(text: str) -> float | None:
    try:
        parts = [int(p) for p in text.split(":")]
    except (ValueError, AttributeError):
        return None
    if len(parts) not in (2, 3) or parts[0] < 0 or any(not 0 <= value < 60 for value in parts[1:]):
        return None
    secs = 0
    for p in parts:
        secs = secs * 60 + p
    return float(secs)


def goal_check(conn: sqlite3.Connection, today: str | None = None) -> dict[str, Any]:
    goal = athlete.get(conn, "goal_race")
    if not isinstance(goal, dict) or not goal.get("distance_km") or not goal.get("target"):
        return {"needs_input": True,
                "question": athlete.PLACEHOLDERS["goal_race"][0],
                "example": {"distance_km": 10, "date": "2027-03-01", "target": "50:00"}}
    try:
        dist_m = float(goal["distance_km"]) * 1000
    except (TypeError, ValueError, OverflowError):
        return {"error": "distance_km must be a positive, finite number"}
    if isinstance(goal["distance_km"], bool) or not math.isfinite(dist_m) or dist_m <= 0:
        return {"error": "distance_km must be a positive, finite number"}
    target_s = _parse_time(str(goal["target"]))
    if not target_s:
        return {"error": "target must look like 'mm:ss' or 'h:mm:ss'"}
    today = today or conn.execute("SELECT MAX(day) FROM daily").fetchone()[0] or \
        date.today().isoformat()
    weeks = None
    if goal.get("date"):
        try:
            race_day = date.fromisoformat(goal["date"])
        except (TypeError, ValueError):
            return {"error": "race date must be YYYY-MM-DD"}
        weeks = round((race_day - date.fromisoformat(today)).days / 7, 1)

    th = loads.thresholds(conn, today)
    eff = loads.effective_vo2max(conn, today, th["hr_max"], 180) if th["hr_max"] else {}
    preds: dict[str, Any] = {}
    if eff.get("value"):
        preds["effective_vo2max"] = loads.time_for_vdot(dist_m, eff["value"])
    rp = loads.race_predictions(conn, today, 180)
    if rp.get("based_on"):
        b = rp["based_on"]
        preds["best_effort_riegel"] = loads.riegel(b["duration_s"], b["distance_m"], dist_m)
    std = {5000: 0, 10000: 1, 21097.5: 2, 42195: 3}
    key = min(std, key=lambda d: abs(d - dist_m))
    if abs(key - dist_m) < 300:
        g = conn.execute("SELECT t5k_s, t10k_s, half_s, marathon_s FROM race_predictions "
                         "WHERE day<=? ORDER BY day DESC LIMIT 1", (today,)).fetchone()
        if g and g[std[key]]:
            preds["garmin"] = float(g[std[key]])

    required_vdot = loads.vdot(dist_m, target_s)
    import statistics

    # Median of methods, never the most optimistic one (avoids a skewed verdict).
    central = statistics.median(preds.values()) if preds else None
    gap = (central - target_s) / target_s * 100 if central else None
    spread = ((max(preds.values()) - min(preds.values())) / central * 100
              if len(preds) > 1 and central else None)
    if gap is None:
        verdict = "not enough run data to predict"
    elif gap <= 0:
        verdict = "on track: the middle prediction already meets the target"
    elif gap <= 3:
        verdict = "within reach with focused training (heuristic: <= 3% slower)"
    elif gap <= 8:
        verdict = "ambitious: needs a clear fitness gain (heuristic: 3-8% slower)"
    else:
        verdict = "very ambitious for the time available (heuristic: > 8% slower)"

    km8 = rp.get("weekly_run_km_8wk")
    hint_key = min(VOLUME_HINT_KM, key=lambda d: abs(d - dist_m / 1000))
    cautions = []
    if spread is not None and spread > 10:
        cautions.append(f"Methods disagree by {spread:.0f}%: predictions are uncertain; a "
                        "time-trial or race would settle it.")
    if km8 is not None and km8 < VOLUME_HINT_KM[hint_key][0]:
        cautions.append(f"Current volume {km8} km/week is below the usual "
                        f"{VOLUME_HINT_KM[hint_key][0]}-{VOLUME_HINT_KM[hint_key][1]} km/week "
                        "for this distance: endurance, not speed, is the limiter.")
        if gap is not None and gap <= 3:
            verdict += " - but only if volume is built up"
    return {
        "cautions": cautions,
        "prediction_spread_pct": round(spread, 1) if spread is not None else None,
        "goal": goal, "weeks_to_race": weeks,
        "required_pace_min_km": loads._pace(target_s / dist_m * 1000),
        "required_vdot": round(required_vdot, 1) if required_vdot else None,
        "current_effective_vo2max": eff.get("value"),
        "predictions": {k: loads._hms(v) for k, v in preds.items()},
        "gap_vs_median_prediction_pct": round(gap, 1) if gap is not None else None,
        "verdict": verdict,
        "volume": {"current_km_per_week_8wk": km8,
                   "typical_range_km_per_week": VOLUME_HINT_KM[hint_key],
                   "note": "coaching rule of thumb, not a research threshold"},
    }
