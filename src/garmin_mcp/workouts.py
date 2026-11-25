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
from datetime import date
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
    if not isinstance(text, str):
        raise TypeError("pace must be a range such as 5:00-5:10")
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
                if s.keys() & {"duration", "distance_m", "pace", "hr", "hr_zone"}:
                    problems.append("put duration, distance and targets on the steps inside a repeat")
                walk(s.get("steps", []), depth + 1)
                continue
            if s.keys() & {"times", "steps"}:
                problems.append("repeat counts and nested steps require a repeat group")
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
    makers = {"warmup": gw.create_warmup_step, "recovery": gw.create_recovery_step,
              "cooldown": gw.create_cooldown_step}
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
            distance = float(s["distance_m"])
            step = gw.create_targeted_distance_interval_step(distance, n, target)
            if t in makers:
                step.stepType = makers[t](0, n).stepType
            est += distance / 2.8  # rough estimate at ~6:00/km
        else:
            dur = _secs(s["duration"])
            est += dur
            if t == "interval":
                step = gw.create_targeted_interval_step(dur, n, target)
            else:
                tt = gw._target_kwargs(target, None).get("target_type") if target else None
                step = makers[t](dur, n, tt)
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
    if not math.isfinite(est):
        raise ValueError("combined workout duration must be finite")
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


def _preview(payload: dict[str, Any]) -> dict[str, Any]:
    """Read the serialized workout so preview and upload use the same step meaning."""
    from garmin_mcp.loads import _hms

    totals = {"encoded_steps": 0, "performed_steps": 0, "repeat_depth": 0,
              "fixed_time_s": 0.0, "fixed_distance_m": 0.0, "distance_without_pace_m": 0.0}
    fast_time = slow_time = 0.0
    has_zone = False

    def walk(steps, multiplier=1, depth=0):
        nonlocal fast_time, slow_time, has_zone
        rows = []
        for s in steps:
            totals["encoded_steps"] += 1
            typ = s["stepType"]["stepTypeKey"]
            row = {"order": s["stepOrder"], "type": typ}
            rows.append(row)
            if typ == "repeat":
                times = s["numberOfIterations"]
                totals["repeat_depth"] = max(totals["repeat_depth"], depth + 1)
                row.update(times=times, steps=walk(s["workoutSteps"], multiplier * times, depth + 1))
                continue
            totals["performed_steps"] += multiplier
            end = s["endCondition"]["conditionTypeKey"]
            value = s["endConditionValue"]
            key = "duration_s" if end == "time" else "distance_m"
            row[key] = value
            totals["fixed_time_s" if end == "time" else "fixed_distance_m"] += value * multiplier
            if s.get("description"):
                row["note"] = s["description"]
            target = (s.get("targetType") or {}).get("workoutTargetTypeKey")
            low, high = s.get("targetValueOne"), s.get("targetValueTwo")
            if target == "pace.zone":
                fast, slow = round(1000 / high), round(1000 / low)
                row["target"] = {"pace": f"{_hms(fast)}–{_hms(slow)} min/km",
                                 "faster_s_per_km": fast, "slower_s_per_km": slow}
                if end == "distance":
                    fast_time += value * multiplier / high
                    slow_time += value * multiplier / low
            else:
                if end == "distance":
                    totals["distance_without_pace_m"] += value * multiplier
                if target == "heart.rate.zone":
                    if "zoneNumber" in s:
                        has_zone = True
                        row["target"] = {"heart_rate_zone": s["zoneNumber"]}
                    else:
                        row["target"] = {"min_bpm": low, "max_bpm": high}
        return rows

    steps = walk(payload["workoutSegments"][0]["workoutSteps"])
    if not all(math.isfinite(value) for value in (*totals.values(), fast_time, slow_time)):
        raise ValueError("combined workout totals must be finite")
    compatibility = {
        "format": "validated Garmin Connect running workout",
        "watch_status": "unverified",
        "note": "This preview used the local compiler. Upload, sync and watch behavior need a device check.",
    }
    if totals["repeat_depth"] > 1:
        compatibility["nested_repeats"] = "Check how the paired watch renders nested repeat groups."
    if has_zone:
        compatibility["heart_rate_zones"] = "Zone targets use the watch’s running zone settings."
    estimate = None
    if not totals["distance_without_pace_m"]:
        bounds = [totals["fixed_time_s"] + time for time in (fast_time, slow_time)]
        if not all(math.isfinite(value) for value in bounds):
            raise ValueError("combined workout time bounds must be finite")
        estimate = [round(value, 1) for value in bounds]
    return {"steps": steps, "totals": totals, "time_at_target_range_s": estimate,
            "garmin_estimate_basis": "Fixed step time plus distance at 2.8 m/s.",
            "compatibility": compatibility}


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
    if schedule_date is not None:
        try:
            if date.fromisoformat(schedule_date).isoformat() != schedule_date:
                raise ValueError
        except (TypeError, ValueError):
            problems.append("schedule date must be YYYY-MM-DD")
    if problems:
        return {"ok": False, "problems": problems}
    try:
        payload = build(spec)
        preview = _preview(payload) if not upload else None
    except ValueError as exc:
        return {"ok": False, "problems": [str(exc)]}
    out: dict[str, Any] = {"ok": True, "garmin_workout_json": payload,
                           "estimated_duration_s": payload["estimatedDurationInSecs"],
                           "uploaded": False}
    if not upload:
        out["preview"] = preview
        if schedule_date is not None:
            out["preview"]["requested_schedule_date"] = schedule_date
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
