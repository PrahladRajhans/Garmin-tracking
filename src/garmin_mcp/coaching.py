"""Phase 5: workout coaching. Running first, then swim and strength trends.

Per-run analysis compares each run with YOUR history at a matched pace, because cadence, stride,
ground contact and vertical oscillation all change with speed (comparing raw averages across
easy and fast runs is misleading).

Rules (see METRICS.md §Phase 5):
- Steady run: >= 20 min moving, coefficient of variation of 1-min speeds < 15 %.
- Efficiency factor (EF) = graded speed (m/min, Minetti) / average HR (Allen & Coggan).
- Aerobic decoupling (Pa:HR) = (EF first half - EF second half) / EF first half * 100 (Friel).
  This comparison is descriptive and depends on course, conditions and sensor quality.
- Matched-pace norms: medians of your runs in the last 180 days within +/- 15 s/km of this run's
  pace (min 3 runs), compared per metric.
- Vertical ratio = vertical oscillation / step length * 100 (Garmin's definition).
- Effort: compare moving heart rate across similar steady outdoor runs.
"""

from __future__ import annotations

import itertools
import json
import math
import sqlite3
import statistics
from bisect import bisect_left
from datetime import UTC, date, datetime, timedelta
from typing import Any

from garmin_mcp import conditions, run_evidence
from garmin_mcp.loads import RUN_TYPES, _hms, minetti_cost

RUN_IN = ",".join("?" * len(RUN_TYPES))
MAX_SAMPLE_GAP_S = 10


def _ts(v: str) -> float:
    t = datetime.fromisoformat(v)
    return (t if t.tzinfo else t.replace(tzinfo=UTC)).timestamp()


def _pace(speed: float | None) -> str | None:
    if not speed:
        return None
    s = round(1000 / speed)
    return f"{s // 60}:{s % 60:02d}"


def _rows(conn: sqlite3.Connection, aid: int) -> list[dict[str, Any]]:
    cur = conn.execute(
        "SELECT ts, heart_rate, speed, altitude, distance, cadence, step_length, stance_time, "
        "vertical_oscillation, power, temperature FROM fit_records WHERE activity_id=? ORDER BY ts",
        (aid,))
    cols = [c[0] for c in cur.description]
    out = []
    for r in cur:
        d = dict(zip(cols, r))
        d["t"] = _ts(d["ts"])
        out.append(d)
    return out


def _moving(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r["speed"] and math.isfinite(r["speed"]) and r["speed"] > 1.0]


def _mean(vals: list[float]) -> float | None:
    vals = [v for v in vals if v is not None]
    return statistics.fmean(vals) if vals else None


def _moving_intervals(rows: list[dict[str, Any]]) -> list[tuple[float, float, float, float | None]]:
    intervals = []
    for a, b in itertools.pairwise(rows):
        dt = b["t"] - a["t"]
        if not 0 < dt <= MAX_SAMPLE_GAP_S or not all(
                isinstance(r["speed"], (int, float)) and math.isfinite(r["speed"])
                and r["speed"] > 1.0 for r in (a, b)):
            continue
        dd = b["distance"] - a["distance"] if None not in (a["distance"], b["distance"]) else 0
        da = b["altitude"] - a["altitude"] if None not in (a["altitude"], b["altitude"]) else 0
        grade = da / dd if dd > 2 and math.isfinite(da) else 0
        hr = b["heart_rate"]
        valid_hr = hr if isinstance(hr, (int, float)) and math.isfinite(hr) and hr > 0 else None
        speed = b["speed"]
        intervals.append((dt, speed, speed * minetti_cost(grade) / minetti_cost(0), valid_hr))
    return intervals


def _minute_speeds(intervals: list[tuple[float, float, float, float | None]]) -> list[float]:
    speeds = []
    seconds = metres = 0.0
    for dt, speed, _, _ in intervals:
        part = min(dt, 60 - seconds)
        seconds += part
        metres += speed * part
        if seconds >= 60:
            speeds.append(metres / 60)
            seconds = dt - part
            metres = speed * seconds
    return speeds


def _half_efficiency(intervals: list[tuple[float, float, float, float | None]],
                     start: float, end: float) -> tuple[float, float] | None:
    elapsed = valid = speed_sum = hr_sum = 0.0
    for dt, _, graded, hr in intervals:
        overlap = max(0.0, min(end, elapsed + dt) - max(start, elapsed))
        if hr is not None and overlap:
            valid += overlap
            speed_sum += overlap * graded
            hr_sum += overlap * hr
        elapsed += dt
        if elapsed >= end:
            break
    if valid < 0.9 * (end - start) or not hr_sum:
        return None
    return speed_sum * 60 / hr_sum, hr_sum / valid


def _elapsed_splits(rows: list[dict[str, Any]]) -> tuple[list[float], float | None]:
    """Interpolate elapsed crossings from recorded distance, with pauses included."""
    points = [(r["distance"], r["t"]) for r in rows
              if isinstance(r["distance"], (int, float)) and math.isfinite(r["distance"])
              and r["distance"] >= 0]
    distances = [d for d, _ in points]
    if len(points) < 2 or any(not 0 <= b - a < 1000 for a, b in itertools.pairwise(distances)):
        return [], None
    origin, t0 = points[0]
    total = distances[-1] - origin

    def crossing(target: float) -> float | None:
        i = bisect_left(distances, target)
        before, ta = points[i - 1]
        after, tb = points[i]
        if after == target and tb > ta:
            return tb
        if not 0 < tb - ta <= MAX_SAMPLE_GAP_S:
            return None
        return ta + (target - before) / (after - before) * (tb - ta)

    times = [t0]
    for km in range(1, int(total // 1000) + 1):
        t = crossing(origin + 1000 * km)
        if t is None or t <= times[-1]:
            return [], None
        times.append(t)
    midpoint = crossing(origin + total / 2) if total >= 4000 else None
    split_delta = (points[-1][1] - midpoint) - (midpoint - t0) if midpoint is not None else None
    return [b - a for a, b in itertools.pairwise(times)], split_delta


def run_metrics(conn: sqlite3.Connection, aid: int) -> dict[str, Any] | None:
    rows = _rows(conn, aid)
    mov = _moving(rows)
    intervals = _moving_intervals(rows)
    dur = sum(dt for dt, _, _, _ in intervals)
    if dur < 120:
        return None
    minute_speeds = _minute_speeds(intervals)
    cv = (statistics.stdev(minute_speeds) / statistics.fmean(minute_speeds) * 100
          if len(minute_speeds) > 2 else None)
    steady = dur >= 1200 and cv is not None and cv < 15
    gs = sum(dt * graded for dt, _, graded, _ in intervals) / dur
    avg_speed = sum(dt * speed for dt, speed, _, _ in intervals) / dur
    whole = _half_efficiency(intervals, 0, dur)
    ef, hr = whole if whole else (None, None)
    decoupling = drift = None
    if steady:
        first = _half_efficiency(intervals, 0, dur / 2)
        second = _half_efficiency(intervals, dur / 2, dur)
        if first and second:
            ef1, h1 = first
            ef2, h2 = second
            decoupling = (ef1 - ef2) / ef1 * 100
            drift = h2 - h1
    cadence_samples = [cadence for r in mov if isinstance(cadence := r["cadence"], (int, float))
                       and math.isfinite(cadence) and cadence > 0]
    cad = _mean(cadence_samples)
    step = _mean([r["step_length"] for r in mov if r["step_length"]])
    vo = _mean([r["vertical_oscillation"] for r in mov if r["vertical_oscillation"]])
    splits, split_delta = _elapsed_splits(rows)
    split_cv = (statistics.stdev(splits) / statistics.fmean(splits) * 100
                if len(splits) >= 3 else None)
    return {
        "moving_s": round(dur), "recorded_elapsed_s": round(rows[-1]["t"] - rows[0]["t"]),
        "steady": steady, "speed_cv_pct": _r(cv),
        "avg_speed": avg_speed, "graded_speed": gs, "avg_hr": _r(hr),
        "efficiency_factor": _r(ef, 3), "decoupling_pct": _r(decoupling),
        "hr_drift_bpm": _r(drift),
        "cadence_spm": _r(cad * 2) if cad else None,
        "cadence_coverage_pct": _r(100 * len(cadence_samples) / len(mov)),
        "step_length_m": _r(step / 1000, 3) if step else None,
        "ground_contact_ms": _r(_mean([r["stance_time"] for r in mov if r["stance_time"]])),
        "vertical_oscillation_cm": _r(vo / 10, 2) if vo else None,
        "vertical_ratio_pct": _r(vo / step * 100, 2) if vo and step else None,
        "power_w": _r(_mean([r["power"] for r in mov if r["power"]])),
        "temperature_c": _r(_mean([r["temperature"] for r in mov if r["temperature"] is not None])),
        "km_splits": [_hms(s) for s in splits],
        "km_split_s": [_r(s) for s in splits], "half_split_delta_s": _r(split_delta),
        "split_cv_pct": _r(split_cv),
        "negative_split": split_delta < -1 if split_delta is not None else None,
    }


def _r(v: float | None, nd: int = 1) -> float | None:
    return round(v, nd) if isinstance(v, (int, float)) else None


def _history(conn: sqlite3.Connection, end: str, days: int = 180,
             exclude: int | None = None) -> list[tuple[int, str, dict[str, Any]]]:
    lo = (date.fromisoformat(end) - timedelta(days=days)).isoformat()
    out = []
    for aid, start in conn.execute(
            f"SELECT activity_id, start_time_local FROM activities WHERE type IN ({RUN_IN}) AND "
            "fit_parsed=1 AND substr(start_time_local,1,10) BETWEEN ? AND ? "
            "AND (? IS NULL OR julianday(start_time_local) < "
            "(SELECT julianday(start_time_local) FROM activities WHERE activity_id=?)) "
            "ORDER BY julianday(start_time_local)", (*RUN_TYPES, lo, end, exclude, exclude)):
        m = run_metrics(conn, aid)
        if m:
            out.append((aid, start[:10], m))
    return out


FORM_KEYS = ("avg_hr", "cadence_spm", "step_length_m", "ground_contact_ms",
             "vertical_oscillation_cm", "vertical_ratio_pct", "power_w", "efficiency_factor")


def matched_pace_norms(hist: list[tuple[int, str, dict[str, Any]]], speed: float,
                       window_s_per_km: float = 15) -> dict[str, Any] | None:
    pace = 1000 / speed
    near = [m for _, _, m in hist if m["avg_speed"] and abs(1000 / m["avg_speed"] - pace)
            <= window_s_per_km]
    if len(near) < 3:
        return None
    return {"runs": len(near), **{k: _r(statistics.median(v), 3) for k in FORM_KEYS
                                  if len(v := [m[k] for m in near if m.get(k) is not None]) >= 3}}


def run_analysis(conn: sqlite3.Connection, aid: int) -> dict[str, Any]:
    from garmin_mcp.running import knee_cadence_experiment

    a = conn.execute("SELECT name, type, start_time_local, distance_m, aerobic_te, anaerobic_te, "
                     "summary FROM activities WHERE activity_id=?", (aid,)).fetchone()
    if not a:
        return {"error": f"activity {aid} not found"}
    m = run_metrics(conn, aid)
    if not m:
        return {"error": "not enough moving data in the FIT file for running analysis"}
    try:
        day = date.fromisoformat((a[2] or "")[:10]).isoformat()
    except ValueError:
        day = None
    hist = _history(conn, day, 180, exclude=aid) if day else []
    norms, window = None, 15
    for window in (15, 30):  # widen if too few runs at a closely matched pace
        norms = matched_pace_norms(hist, m["avg_speed"], window)
        if norms:
            break
    comparison = None
    if norms:
        comparison = {k: {"this_run": m.get(k), "your_norm_at_this_pace": norms.get(k),
                          "diff": _r(m[k] - norms[k], 3)
                          if m.get(k) is not None and norms.get(k) is not None else None}
                      for k in FORM_KEYS}
    similar = [(x[1], x[2]) for x in hist if a[3] and x[2]["avg_speed"] and
               abs((x[2]["moving_s"] * x[2]["avg_speed"]) - a[3]) <= 0.25 * a[3]]
    cached = {other_id: measurements for other_id, _, measurements in hist}

    def measurements(c: sqlite3.Connection, activity_id: int) -> dict | None:
        return cached[activity_id] if activity_id in cached else run_metrics(c, activity_id)

    effort = run_evidence.matched_effort(conn, aid, m, measurements)
    load = conn.execute("SELECT trimp, z1_s, z2_s, z3_s FROM activity_load WHERE activity_id=?",
                        (aid,)).fetchone() if _has(conn, "activity_load") else None
    summary = json.loads(a[6] or "{}")
    facts = _facts(m, comparison, effort, summary)
    cue = knee_cadence_experiment(conn, a[1], m)
    if cue:
        facts.insert(0, cue["suggestion"])
    return {
        "id": aid, "name": a[0], "date": day, "distance_km": _r((a[3] or 0) / 1000, 2),
        "pace": _pace(m["avg_speed"]), "graded_pace": _pace(m["graded_speed"]),
        "metrics": m,
        "compared_with_your_norm_at_matched_pace": comparison,
        "norm_basis": f"{norms['runs']} runs within +/-{window} s/km in 180 days" if norms else
        "fewer than 3 runs at a similar pace in 180 days",
        "similar_runs": [{"date": d, "pace": _pace(x["avg_speed"]), "avg_hr": x["avg_hr"],
                          "efficiency_factor": x["efficiency_factor"]} for d, x in similar[-5:]],
        "garmin": {"aerobic_te": a[4], "anaerobic_te": a[5],
                   "label": summary.get("trainingEffectLabel")},
        "load": {"trimp": load[0], "seiler_zone_s": list(load[1:])} if load else None,
        "heat_model": {"available": False, "reason": "Watch temperature does not establish "
                       "outdoor heat exposure. Use separately sourced conditions."},
        "comparable_effort": effort,
        "conditions": conditions.for_activity(conn, aid),
        "facts_for_recap": facts,
        "cadence_experiment": cue,
        "narrate_as": "Activity recap: pacing, heart rate on similar runs, form at this pace, "
                      "and one thing to check next time.",
    }


def _has(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone() is not None


def _facts(m: dict[str, Any], comp: dict[str, Any] | None, effort: dict,
           summary: dict[str, Any]) -> list[str]:
    f = [run_evidence.headline(effort)]
    if check := run_evidence.next_check(effort):
        f.append(check)
    if m["steady"] and m["decoupling_pct"] is not None:
        d = m["decoupling_pct"]
        f.append(f"Pace-to-heart-rate efficiency changed by {-d:+.1f}% in the second half. "
                 "Compare similar steady runs and consider heat, terrain, pacing and sensor noise.")
    elif not m["steady"]:
        f.append("Too little steady recorded moving time for an efficiency comparison.")
    delta = m["half_split_delta_s"]
    if delta is not None:
        f.append("Second half faster by recorded distance." if delta < -1 else
                 "Second half slower by recorded distance." if delta > 1 else
                 "Both distance halves took about the same elapsed time.")
    if comp:
        for k, label, unit in (("cadence_spm", "Cadence", "spm"),
                               ("ground_contact_ms", "Ground contact", "ms"),
                               ("vertical_ratio_pct", "Vertical ratio", "%")):
            d = comp[k]["diff"]
            if d is not None and abs(d) >= {"cadence_spm": 3, "ground_contact_ms": 10,
                                            "vertical_ratio_pct": 0.4}[k]:
                f.append(f"{label} {d:+.1f} {unit} vs your norm at this pace.")
    if summary.get("trainingEffectLabel"):
        f.append(f"Garmin training effect label: {summary['trainingEffectLabel']}.")
    return f


def running_form_trends(conn: sqlite3.Connection, end: str, days: int = 365) -> dict[str, Any]:
    """Monthly medians at your most common pace band, so changes reflect form, not speed."""
    hist = _history(conn, end, days)
    if not hist:
        return {"runs": 0}
    paces = [1000 / m["avg_speed"] for _, _, m in hist if m["avg_speed"]]
    band = statistics.median(paces)
    in_band = [(d, m) for _, d, m in hist if m["avg_speed"] and abs(1000 / m["avg_speed"] - band)
               <= 30]
    months: dict[str, list[dict[str, Any]]] = {}
    for d, m in in_band:
        months.setdefault(d[:7], []).append(m)
    rows = [{"month": k, "runs": len(v), **{x: _r(statistics.median(vals), 3) for x in FORM_KEYS
                                             if (vals := [m[x] for m in v if m.get(x) is not None])}}
            for k, v in sorted(months.items())]
    steady = [(d, m["efficiency_factor"], m["decoupling_pct"]) for _, d, m in hist
              if m["steady"] and m["efficiency_factor"]]
    return {"pace_band": f"{_pace(1000 / band)} +/- 0:30 per km", "runs_in_band": len(in_band),
            "monthly": rows,
            "steady_runs_efficiency": [{"date": d, "ef": e, "decoupling_pct": dc}
                                       for d, e, dc in steady[-20:]],
            "meaning": "Within a fixed pace band: rising EF = fitter aerobically; higher cadence "
                       "with shorter ground contact and lower vertical ratio = usually more "
                       "economical form."}


def activity_stream(conn: sqlite3.Connection, aid: int, every_s: int = 10) -> dict[str, Any]:
    rows = _rows(conn, aid)
    if not rows:
        return {"error": "no FIT records"}
    out, last = [], None
    t0 = rows[0]["t"]
    for r in rows:
        if last is None or r["t"] - last >= every_s:
            out.append({"t_s": round(r["t"] - t0), "hr": r["heart_rate"],
                        "pace": _pace(r["speed"]) if r["speed"] and r["speed"] > 0.5 else None,
                        "cadence_spm": r["cadence"] * 2 if r["cadence"] else None,
                        "step_length_m": _r(r["step_length"] / 1000, 3) if r["step_length"] else None,
                        "speed_m_s": r["speed"],
                        "altitude_m": _r(r["altitude"]), "power_w": r["power"],
                        "distance_km": _r((r["distance"] or 0) / 1000, 3)})
            last = r["t"]
    return {"activity_id": aid, "every_s": every_s, "points": len(out), "stream": out,
            "start_utc": datetime.fromtimestamp(t0, UTC).isoformat()}


# --------------------------------------------------------------------------- other sports
def swim_trends(conn: sqlite3.Connection, end: str, days: int = 365) -> dict[str, Any]:
    from garmin_mcp.insights import swim_summary

    lo = (date.fromisoformat(end) - timedelta(days=days)).isoformat()
    out = []
    for aid, start in conn.execute(
            "SELECT activity_id, start_time_local FROM activities WHERE type='lap_swimming' AND "
            "substr(start_time_local,1,10) BETWEEN ? AND ? ORDER BY start_time_local", (lo, end)):
        s = swim_summary(conn, aid)
        if s:
            out.append({"date": start[:10], "distance_m": s["distance_m"],
                        "pace_per_100m": s["pace_per_100m"], "pool_m": s["pool_length_m"],
                        "by_stroke": {k: {"swolf": v["swolf"], "pace": v["pace_per_100m"]}
                                      for k, v in s["by_stroke"].items()}})
    return {"swims": len(out), "sessions": out,
            "meaning": "Compare SWOLF and pace within the same stroke and pool length."}


def strength_trends(conn: sqlite3.Connection, end: str, days: int = 365) -> dict[str, Any]:
    lo = (date.fromisoformat(end) - timedelta(days=days)).isoformat()
    rows = conn.execute(
        "SELECT substr(a.start_time_local,1,7), COUNT(DISTINCT a.activity_id), COUNT(s.seq), "
        "SUM(s.repetitions) FROM activities a LEFT JOIN fit_sets s ON s.activity_id = "
        "a.activity_id AND s.set_type='active' WHERE a.type='strength_training' AND "
        "substr(a.start_time_local,1,10) BETWEEN ? AND ? GROUP BY 1 ORDER BY 1", (lo, end))
    return {"monthly": [{"month": m, "sessions": n, "sets": s, "reps": r} for m, n, s, r in rows],
            "note": "Weights are not recorded in your sessions, so volume (kg) is unavailable."}


# --------------------------------------------------------------------------- fitness age
def fitness_age(conn: sqlite3.Connection) -> dict[str, Any]:
    """Garmin's fitness age with the levers Garmin itself reports (target and potential age)."""
    row = conn.execute("SELECT day, payload FROM raw_daily WHERE dataset IN "
                       "('pa_fitness_age','fitness_age') AND payload != 'null' "
                       "ORDER BY day DESC LIMIT 1").fetchone()
    if not row:
        return {"available": False}
    p = json.loads(row[1])
    levers = []
    for key, label, unit in (("vigorousDaysAvg", "vigorous days per week", "days"),
                             ("vigorousMinutesAvg", "vigorous minutes per week", "min"),
                             ("rhr", "resting heart rate", "bpm"),
                             ("bmi", "BMI", "")):
        c = (p.get("components") or {}).get(key) or {}
        if c:
            levers.append({"lever": label, "current": _r(c.get("value"), 1),
                           "target": c.get("targetValue"),
                           "fitness_age_if_reached": _r(c.get("potentialAge"), 1),
                           "priority": c.get("priority"), "unit": unit})
    vo2 = conn.execute("SELECT vo2max_run FROM training WHERE vo2max_run IS NOT NULL "
                       "ORDER BY day DESC LIMIT 1").fetchone()
    return {"as_of": row[0], "garmin_fitness_age": _r(p.get("fitnessAge"), 1),
            "chronological_age": p.get("chronologicalAge"),
            "achievable_age": _r(p.get("achievableFitnessAge"), 1),
            "levers": sorted(levers, key=lambda x: x["priority"] or 99),
            "vo2max_run": vo2[0] if vo2 else None,
            "method": "Garmin: based on VO2max norms adjusted by RHR, BMI and vigorous activity; "
                      "levers and potential ages are Garmin's own figures.",
            "next_steps": [f"{x['lever']}: {x['current']} -> {x['target']} {x['unit']} "
                           f"(fitness age ~{x['fitness_age_if_reached']})"
                           for x in levers if x["target"] is not None]}


def session_unit_check(conn: sqlite3.Connection, limit: int = 30) -> dict[str, Any]:
    """Our stream-derived form metrics vs Garmin's own FIT session averages (unit check)."""
    diffs: dict[str, list[float]] = {"vertical_ratio_pct": [], "ground_contact_ms": [],
                                     "step_length_m": [], "cadence_spm": []}
    for aid, payload in conn.execute(
            f"SELECT s.activity_id, s.payload FROM fit_sessions s JOIN activities a "
            f"USING(activity_id) WHERE a.type IN ({RUN_IN}) ORDER BY a.start_time_local DESC "
            f"LIMIT ?", (*RUN_TYPES, limit)):
        g = (json.loads(payload) or [{}])[0]
        m = run_metrics(conn, aid)
        if not m:
            continue
        pairs = {"vertical_ratio_pct": (m["vertical_ratio_pct"], g.get("avg_vertical_ratio")),
                 "ground_contact_ms": (m["ground_contact_ms"], g.get("avg_stance_time")),
                 "step_length_m": (m["step_length_m"],
                                   (g.get("avg_step_length") or 0) / 1000 or None),
                 "cadence_spm": (m["cadence_spm"], (g.get("avg_running_cadence") or 0) * 2
                                 or None)}
        for k, (ours, theirs) in pairs.items():
            if ours and theirs:
                diffs[k].append(abs(ours - theirs) / theirs * 100)
    return {k: {"runs": len(v), "median_abs_diff_pct": round(statistics.median(v), 2)}
            for k, v in diffs.items() if v}


# --------------------------------------------------------------------------- glossary
GLOSSARY: dict[str, dict[str, str]] = {
    "cadence": {"meaning": "Steps per minute (both feet).",
                "typical": "150-180 spm recreational; rises with speed.",
                "improve": "Small increases (5-10 %) at the same pace reduce overstriding and "
                           "impact loading (Heiderscheit 2011). Compare at matched pace only.",
                "unit": "spm"},
    "step_length": {"meaning": "Distance per step. Speed = cadence x step length.",
                    "typical": "0.8-1.3 m; grows with speed.",
                    "improve": "Comes from strength and power (hill sprints, plyometrics), not "
                               "reaching forward.", "unit": "m"},
    "ground_contact_time": {"meaning": "Time each foot is on the ground per step.",
                            "typical": "200-300 ms; shorter when faster.",
                            "improve": "Strength, plyometrics, strides; compare at matched pace.",
                            "unit": "ms"},
    "vertical_oscillation": {"meaning": "Up-down bounce of the torso per step.",
                             "typical": "6-11 cm.",
                             "improve": "Less bounce for the same speed is more economical; "
                                        "cues: run tall, quicker steps.", "unit": "cm"},
    "vertical_ratio": {"meaning": "Vertical oscillation / step length x 100: bounce per unit of "
                                  "forward motion (lower = more efficient).",
                       "typical": "6-10 %.", "improve": "Raise cadence slightly, reduce bounce.",
                       "unit": "%"},
    "running_power": {"meaning": "Garmin wrist estimate of mechanical power, includes wind.",
                      "typical": "Personal; ~3.5-5 W/kg at threshold for recreational runners.",
                      "improve": "Use for trends on the same watch; not comparable with Stryd.",
                      "unit": "W"},
    "efficiency_factor": {"meaning": "Graded speed (m/min) per heartbeat. Higher = more speed "
                                     "for the same cardiac effort.",
                          "typical": "Personal; compare steady runs at similar pace.",
                          "improve": "Rises with aerobic base (easy volume, long runs).",
                          "unit": "m/min per bpm"},
    "aerobic_decoupling": {"meaning": "Percentage drop in grade-adjusted speed per heartbeat "
                                      "from first to second moving-time half of a steady run.",
                           "typical": "Compare your own runs of similar duration and conditions.",
                           "improve": "Consider pace, course, heat, fuelling and sensor quality.",
                           "unit": "%"},
    "trimp": {"meaning": "Banister training impulse: time weighted by HR intensity "
                         "(exponential), our training-load unit.",
              "typical": "Easy 30 min ~ 30-50; hard 60 min ~ 120+.",
              "improve": "A dose, not a goal: build gradually.", "unit": "TRIMP"},
    "ctl_atl_tsb": {"meaning": "CTL = 42-day load (fitness), ATL = 7-day load (fatigue), "
                               "TSB = CTL - ATL (form).",
                    "typical": "TSB -10 to -30 in heavy training; +5 to +15 fresh for racing "
                               "(heuristics).", "improve": "Raise CTL slowly (ramp ~3-5/week "
                                                         "heuristic).", "unit": "TRIMP/day"},
    "hrv": {"meaning": "Overnight heart-rate variability (RMSSD): autonomic recovery signal.",
            "typical": "Personal; judge against your own normal band.",
            "improve": "Sleep, lower alcohol and stress, sensible load progression.",
            "unit": "ms"},
    "effective_vo2max": {"meaning": "Fitness estimated from pace relative to %HRmax on "
                                    "submaximal runs (Swain 1994 + Daniels).",
                         "typical": "Usually a few points below Garmin's VO2max.",
                         "improve": "Intervals at 3-5 min, threshold work, consistent volume.",
                         "unit": "ml/kg/min"},
    "swolf": {"meaning": "Seconds + strokes per pool length (lower = more efficient).",
              "typical": "Personal; compare same stroke and pool length.",
              "improve": "Technique drills; longer glide.", "unit": "points"},
    "training_effect": {"meaning": "Garmin aerobic/anaerobic training effect (0-5) from "
                                   "EPOC (Firstbeat).", "typical": "2-3 maintains, 3-4 improves, "
                        "4-5 highly improving.", "improve": "Mix of easy and harder sessions.",
                        "unit": "0-5"},
}
