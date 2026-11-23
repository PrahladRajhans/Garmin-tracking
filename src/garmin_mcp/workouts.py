"""Phase 7: structured workouts to the watch.

Workouts are built from a small spec, validated against your thresholds, converted to Garmin
Connect's workout format using python-garminconnect's own models, then (optionally) uploaded,
scheduled and synced to the watch. Garmin's official Training API is business-only, so upload
uses the unofficial login (Mac only). The built JSON is always returned so nothing is hidden.

Spec example:
{"name": "5x800", "steps": [
  {"type": "warmup", "duration": "10:00"},
  {"type": "repeat", "times": 5, "steps": [
     {"type": "interval", "distance_m": 800, "pace": "5:00-5:10"},
     {"type": "recovery", "duration": "2:00"}]},
  {"type": "cooldown", "duration": "10:00"}]}
Targets per step: "pace": "m:ss-m:ss" (min/km), "hr": "lo-hi" (bpm), or "hr_zone": 1-5.
"""

from __future__ import annotations

import math
import sqlite3
from typing import Any

from garminconnect import workout as gw

STEP_ORDER_START = 1


def _secs(text: str | float) -> float:
    if isinstance(text, bool):
        raise TypeError("duration must be a positive time")
    if isinstance(text, (int, float)):
        total = float(text)
    else:
        parts = str(text).strip().split(":")
        if not 1 <= len(parts) <= 3 or not all(p.isdigit() for p in parts):
            raise ValueError("time must be seconds, m:ss or h:mm:ss")
        if any(int(p) >= 60 for p in parts[1:]):
            raise ValueError("seconds and intermediate minutes must be below 60")
        total = 0.0
        for part in parts:
            total = total * 60 + int(part)
    if not math.isfinite(total) or total <= 0:
        raise ValueError("time must be positive and finite")
    return total


def _pace_range(text: str) -> tuple[float, float]:
    """'5:00-5:10' -> (slow m/s, fast m/s)."""
    a, b = (p.strip() for p in text.split("-"))
    sa, sb = 1000 / _secs(a), 1000 / _secs(b)
    return min(sa, sb), max(sa, sb)


def _target(step: dict[str, Any]) -> Any:
    if "pace" in step:
        lo, hi = _pace_range(step["pace"])
        return gw.PaceTarget(lower_limit=lo, upper_limit=hi)
    if "hr" in step:
        lo, hi = (float(x) for x in str(step["hr"]).split("-"))
        return gw.CustomHeartRateTarget(lower_limit=lo, upper_limit=hi)
    if "hr_zone" in step:
        return gw.HeartRateZoneTarget(zone_number=int(step["hr_zone"]))
    return None


def validate(spec: dict[str, Any], hr_max: float | None) -> list[str]:
    """Safety and sanity checks; returns problems (empty = OK)."""
    if not isinstance(spec, dict):
        return ["workout must be an object"]
    problems = []
    count = 0

    def walk(steps: list[dict[str, Any]], depth: int = 0) -> None:
        nonlocal count
        if depth > 8 or not isinstance(steps, list):
            problems.append("steps must be a list with at most 8 nested repeat levels")
            return
        for s in steps:
            count += 1
            if count > 200:
                problems.append("workout exceeds the 200-step format limit")
                return
            if not isinstance(s, dict):
                problems.append("each step must be an object")
                continue
            t = s.get("type")
            if t not in ("warmup", "interval", "recovery", "cooldown", "repeat"):
                problems.append(f"unknown step type {t!r}")
                continue
            if t == "repeat":
                times = s.get("times", 0)
                if isinstance(times, bool) or not isinstance(times, int) or not 1 <= times <= 30:
                    problems.append("repeat 'times' must be 1-30")
                if not s.get("steps"):
                    problems.append("repeat needs steps")
                walk(s.get("steps", []), depth + 1)
                continue
            if "duration" not in s and "distance_m" not in s:
                problems.append(f"{t} step needs 'duration' or 'distance_m'")
            if "duration" in s and "distance_m" in s:
                problems.append("choose duration or distance_m, not both")
            try:
                if "duration" in s:
                    _secs(s["duration"])
                if "distance_m" in s:
                    distance = float(s["distance_m"])
                    if isinstance(s["distance_m"], bool) or not math.isfinite(distance) or distance <= 0:
                        problems.append("distance_m must be positive and finite")
                if sum(k in s for k in ("pace", "hr", "hr_zone")) > 1:
                    problems.append("choose one target: pace, hr or hr_zone")
                if "pace" in s:
                    slow, fast = _pace_range(s["pace"])
                    if not (1000 / 720 <= slow <= fast <= 1000 / 150):
                        problems.append("pace outside 2:30-12:00 min/km")
                if "hr" in s:
                    lo, hi = (float(x) for x in str(s["hr"]).split("-"))
                    if not (math.isfinite(lo) and math.isfinite(hi) and 0 < lo <= hi):
                        problems.append("hr must be an ordered, positive, finite range")
                    elif hr_max and hi > hr_max:
                        problems.append(f"HR target {hi:.0f} above your max HR {hr_max:.0f}")
                if "hr_zone" in s and (isinstance(s["hr_zone"], bool)
                        or not isinstance(s["hr_zone"], int) or not 1 <= s["hr_zone"] <= 5):
                    problems.append("hr_zone must be an integer 1-5")
            except (TypeError, ValueError, OverflowError):
                problems.append(f"{t} has an invalid duration, distance or target")

    walk(spec.get("steps", []))
    if not spec.get("steps"):
        problems.append("workout has no steps")
    if "name" in spec and not isinstance(spec["name"], str):
        problems.append("workout name must be text")
    return problems


def _build_steps(steps: list[dict[str, Any]], order: list[int]) -> tuple[list[Any], float]:
    out, est = [], 0.0
    for s in steps:
        order[0] += 1
        n = order[0]
        t = s["type"]
        if t == "repeat":
            inner, inner_est = _build_steps(s["steps"], order)
            out.append(gw.create_repeat_group(int(s["times"]), inner, n))
            est += inner_est * int(s["times"])
            continue
        target = _target(s)
        if "distance_m" in s:
            step = gw.create_targeted_distance_interval_step(float(s["distance_m"]), n, target)
            est += float(s["distance_m"]) / 2.8  # rough estimate at ~6:00/km
        else:
            dur = _secs(s["duration"])
            est += dur
            if t == "interval":
                step = gw.create_targeted_interval_step(dur, n, target)
            else:
                maker = {"warmup": gw.create_warmup_step, "recovery": gw.create_recovery_step,
                         "cooldown": gw.create_cooldown_step}[t]
                tt = gw._target_kwargs(target, None).get("target_type") if target else None
                step = maker(dur, n, tt)
                if target is not None:
                    kw = gw._target_kwargs(target, None)
                    step.targetValueOne = kw.get("target_value_one")
                    step.targetValueTwo = kw.get("target_value_two")
                    step.zoneNumber = kw.get("zone_number")
        if s.get("note"):
            step.description = s["note"]
        out.append(step)
    return out, est


def build(spec: dict[str, Any]) -> dict[str, Any]:
    order = [STEP_ORDER_START - 1]
    steps, est = _build_steps(spec["steps"], order)
    wk = gw.RunningWorkout(
        workoutName=spec.get("name", "Workout")[:40],
        estimatedDurationInSecs=int(est),
        description=spec.get("description"),
        workoutSegments=[gw.WorkoutSegment(
            segmentOrder=1,
            sportType={"sportTypeId": gw.SportType.RUNNING, "sportTypeKey": "running",
                       "displayOrder": 1},
            workoutSteps=steps)],
    )
    return wk.to_dict()


def templates(conn: sqlite3.Connection) -> dict[str, Any]:
    """Suggested workouts using your thresholds (HR-based, because run paces are not yet
    calibrated by maximal efforts)."""
    from garmin_mcp import loads

    th = loads.thresholds(conn)
    lthr = th.get("lthr")
    if not lthr:
        return {"error": "no LTHR estimate yet"}
    from garmin_mcp import athlete

    limits = str(athlete.get(conn, "injuries_or_limits") or "")
    cautions = []
    if "knee" in limits.lower():
        cautions = [("Knee: prefer flat routes and soft surfaces; avoid steep downhills and jumps; "
                    "raise weekly volume gradually; stop if pain changes your stride."),
                    ("Strength work that supports knees: glute bridges, step-ups, split squats, "
                    "calf raises (pain-free range).")]
    easy_hi = round(0.85 * lthr)
    tempo = f"{round(0.95 * lthr)}-{round(lthr)}"
    return {
        "basis": {"lthr": lthr, "hr_max": th.get("hr_max"),
                  "note": "HR targets from your LTHR estimate; set lthr_override for accuracy"},
        "cautions": cautions,
        "easy_run": {"name": "Easy 40", "steps": [
            {"type": "warmup", "duration": "5:00"},
            {"type": "interval", "duration": "30:00", "hr": f"{round(0.75 * lthr)}-{easy_hi}",
             "note": "conversational"},
            {"type": "cooldown", "duration": "5:00"}]},
        "tempo": {"name": "Tempo 3x8", "steps": [
            {"type": "warmup", "duration": "12:00"},
            {"type": "repeat", "times": 3, "steps": [
                {"type": "interval", "duration": "8:00", "hr": tempo},
                {"type": "recovery", "duration": "2:00"}]},
            {"type": "cooldown", "duration": "10:00"}]},
        "vo2_intervals": {"name": "VO2 5x3", "steps": [
            {"type": "warmup", "duration": "15:00"},
            {"type": "repeat", "times": 5, "steps": [
                {"type": "interval", "duration": "3:00", "hr_zone": 5,
                 "note": "hard, ~3-5 km race effort"},
                {"type": "recovery", "duration": "3:00"}]},
            {"type": "cooldown", "duration": "10:00"}]},
        "calibration_test": {"name": "CS test", "description": "Calibrates critical speed and "
                             "LTHR: 5 min all-out, 15 min easy, 20 min hard but even.",
                             "steps": [
                                 {"type": "warmup", "duration": "15:00"},
                                 {"type": "interval", "duration": "5:00",
                                  "note": "all-out, even pace"},
                                 {"type": "recovery", "duration": "15:00"},
                                 {"type": "interval", "duration": "20:00",
                                  "note": "hardest even effort you can hold"},
                                 {"type": "cooldown", "duration": "10:00"}]},
    }


def create(conn: sqlite3.Connection, spec: dict[str, Any], upload: bool = False,
           schedule_date: str | None = None, client: Any = None) -> dict[str, Any]:
    from garmin_mcp import loads

    th = loads.thresholds(conn)
    problems = validate(spec, th.get("hr_max"))
    if problems:
        return {"ok": False, "problems": problems}
    payload = build(spec)
    out: dict[str, Any] = {"ok": True, "garmin_workout_json": payload,
                           "estimated_duration_s": payload["estimatedDurationInSecs"],
                           "uploaded": False}
    if not upload:
        out["next"] = "call again with upload=true to send it to Garmin Connect (needs the " \
                      "unofficial login on your Mac)"
        return out
    try:
        if client is None:
            from garmin_mcp.client import get_client

            client = get_client()
        res = client.upload_workout(payload)
        wid = res.get("workoutId") if isinstance(res, dict) else None
        out.update(uploaded=True, workout_id=wid)
        if wid and schedule_date:
            client.schedule_workout(wid, schedule_date)
            out["scheduled_for"] = schedule_date
        out["next"] = "sync the watch (Garmin Connect app) to receive the workout"
    except Exception as exc:  # noqa: BLE001 - report, don't crash the tool
        out["upload_error"] = f"{type(exc).__name__}: {exc}"[:300]
    return out


def list_on_garmin(client: Any = None, limit: int = 20) -> dict[str, Any]:
    try:
        if client is None:
            from garmin_mcp.client import get_client

            client = get_client()
        items = client.get_workouts(0, limit) or []
        return {"workouts": [{"id": w.get("workoutId"), "name": w.get("workoutName"),
                              "sport": (w.get("sportType") or {}).get("sportTypeKey"),
                              "updated": w.get("updatedDate")} for w in items]}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"[:300]}


def delete_on_garmin(workout_id: int, client: Any = None) -> dict[str, Any]:
    try:
        if client is None:
            from garmin_mcp.client import get_client

            client = get_client()
        client.delete_workout(workout_id)
        return {"deleted": workout_id}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"[:300]}
