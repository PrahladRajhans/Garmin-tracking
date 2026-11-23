"""Running workout breakdown: form ratings, pace-matched comparisons, trends and what to work on.

Sources and conventions (see METRICS.md "Running breakdown"):
- Garmin running-dynamics colour gauges (FR955 owner's manual, percentiles of Garmin's runner
  database). Values below are the published gauge bands; verify against the current manual.
- Cadence and stride length rise with speed, so a raw comparison is misleading. We fit your own
  cadence-speed and stride-speed lines across runs (least squares) and report each run versus
  what *you* usually do at that pace.
- Running effectiveness (Coggan/WKO): speed (m/s) / power (W/kg). Garmin wrist power is not
  Stryd power, so compare only with yourself.
"""

from __future__ import annotations

import json
import math
import sqlite3
import statistics
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from garmin_mcp import conditions, run_evidence

# (metric, higher_is_better, [(upper bound exclusive or None, colour, label)]) low -> high
GAUGES: dict[str, list[tuple[float | None, str, str]]] = {
    "cadence_spm": [(153, "red", "short of most runners"), (164, "orange", "below average"),
                    (174, "green", "average"), (184, "blue", "above average"),
                    (None, "purple", "top 5 %")],
    "ground_contact_ms": [(218, "purple", "top 5 %"), (249, "blue", "above average"),
                          (278, "green", "average"), (309, "orange", "below average"),
                          (None, "red", "short of most runners")],
    "vertical_oscillation_cm": [(6.4, "purple", "top 5 %"), (8.2, "blue", "above average"),
                                (9.8, "green", "average"), (11.6, "orange", "below average"),
                                (None, "red", "short of most runners")],
    "vertical_ratio_pct": [(6.1, "purple", "top 5 %"), (7.5, "blue", "above average"),
                           (8.7, "green", "average"), (10.2, "orange", "below average"),
                           (None, "red", "short of most runners")],
}
LABELS = {"cadence_spm": "Cadence", "ground_contact_ms": "Ground contact time",
          "vertical_oscillation_cm": "Bounce (vertical oscillation)",
          "vertical_ratio_pct": "Vertical ratio", "step_length_m": "Stride length"}


def rate(metric: str, value: float | None) -> dict[str, Any] | None:
    if value is None or metric not in GAUGES:
        return None
    for upper, colour, label in GAUGES[metric]:
        if upper is None or value < upper:
            return {"colour": colour, "label": label}
    return None


def _fit(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    if len(xs) < 5 or statistics.pstdev(xs) == 0:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / \
        sum((x - mx) ** 2 for x in xs)
    return b, my - b * mx


def _history(conn: sqlite3.Connection, before: str | None, limit: int = 120,
             read_metrics: Callable[[sqlite3.Connection, int], dict | None] | None = None
             ) -> list[dict]:
    from garmin_mcp.coaching import run_metrics

    q = ("SELECT activity_id, start_time_local FROM activities WHERE type LIKE '%run%' AND "
         "fit_parsed=1 AND julianday(start_time_local) IS NOT NULL " + ("AND julianday(start_time_local) < julianday(?) " if before else "") +
         "ORDER BY julianday(start_time_local) DESC LIMIT ?")
    out = []
    for aid, ts in conn.execute(q, (before, limit) if before else (limit,)).fetchall():
        m = (read_metrics or run_metrics)(conn, aid)
        if m and m.get("avg_speed"):
            out.append({"activity_id": aid, "start": ts, **m})
    return out


def personal_lines(hist: list[dict]) -> dict[str, Any]:
    lines = {}
    for key in ("cadence_spm", "step_length_m", "ground_contact_ms", "vertical_ratio_pct"):
        pts = [(h["avg_speed"], h[key]) for h in hist if h.get(key)]
        f = _fit([p[0] for p in pts], [p[1] for p in pts])
        if f:
            lines[key] = {"slope_per_ms": round(f[0], 3), "intercept": round(f[1], 3),
                          "runs": len(pts), "min_speed_m_s": min(p[0] for p in pts),
                          "max_speed_m_s": max(p[0] for p in pts)}
    return lines


def running_breakdown(
    conn: sqlite3.Connection, aid: int, weight_kg: float | None = None,
    *, read_metrics: Callable[[sqlite3.Connection, int], dict | None] | None = None,
) -> dict[str, Any]:
    from garmin_mcp.coaching import _pace, run_metrics

    read_metrics = read_metrics or run_metrics
    m = read_metrics(conn, aid)
    if not m:
        return {"available": False, "reason": "no second-by-second data for this run"}
    start = conn.execute("SELECT start_time_local, type FROM activities WHERE activity_id=?",
                         (aid,)).fetchone()
    hist = _history(conn, start[0], read_metrics=read_metrics) if start and start[0] else []
    lines = personal_lines(hist)
    speed = m["avg_speed"]
    form = {}
    for key in ("cadence_spm", "step_length_m", "ground_contact_ms", "vertical_oscillation_cm",
                "vertical_ratio_pct"):
        v = m.get(key)
        if v is None:
            continue
        row: dict[str, Any] = {"label": LABELS[key], "value": v, "garmin_gauge": rate(key, v)}
        ln = lines.get(key)
        if ln and ln["min_speed_m_s"] <= speed <= ln["max_speed_m_s"]:
            exp = ln["intercept"] + ln["slope_per_ms"] * speed
            if math.isfinite(exp) and exp > 0:
                row["your_usual_at_this_pace"] = round(exp, 3)
                row["vs_usual_pct"] = round((v - exp) / exp * 100, 1)
        form[key] = row
    eff = None
    if m.get("power_w") and weight_kg:
        eff = round(speed / (m["power_w"] / weight_kg), 3)
    session = conn.execute("SELECT payload FROM fit_sessions WHERE activity_id=?", (aid,)).fetchone()
    sessions = json.loads(session[0]) if session and session[0] else []
    recorded = sessions[0] if len(sessions) == 1 else {}
    cue = knee_cadence_experiment(conn, start[1], m) if start else None
    return {"available": True, "activity_id": aid, "pace": _pace(speed),
            "avg_hr": m.get("avg_hr"), "power_w": m.get("power_w"),
            "running_effectiveness": eff, "form": form,
            "pacing": {"km_splits": m.get("km_splits"), "split_variation_pct":
                       m.get("split_cv_pct"), "negative_split": m.get("negative_split"),
                       "km_split_s": m["km_split_s"], "half_split_delta_s": m["half_split_delta_s"],
                       "recorded_moving_s": m["moving_s"], "recorded_elapsed_s": m["recorded_elapsed_s"],
                       "garmin_timer_s": recorded.get("total_timer_time"),
                       "garmin_elapsed_s": recorded.get("total_elapsed_time"),
                       "hr_drift_bpm": m.get("hr_drift_bpm"),
                       "decoupling_pct": m.get("decoupling_pct")},
            "work_on": suggestions(m, form, eff, cadence_experiment=cue),
            "cadence_experiment": cue,
            "comparable_effort": run_evidence.matched_effort(conn, aid, m, read_metrics),
            "conditions": conditions.for_activity(conn, aid),
            "comparison_runs": len(hist)}


def knee_cadence_experiment(conn: sqlite3.Connection, kind: str | None, metrics: dict
                            ) -> dict[str, Any] | None:
    """An optional change at the runner's own cadence for an easy, comfortable run."""
    from garmin_mcp import athlete, engine, health, loads

    measured = metrics.get("cadence_spm")
    if (kind not in loads.RUN_TYPES or not metrics.get("steady") or not measured
            or (metrics.get("cadence_coverage_pct") or 0) < 80):
        return None
    limits = str(athlete.get(conn, "injuries_or_limits") or "")
    if "knee" not in limits.lower():
        return None
    today = datetime.now(engine._tz(conn)).date().isoformat()
    if today in health.status_days(conn):
        return None
    target = round(measured * 1.05)
    return {"recorded_steps_per_min": measured, "trial_steps_per_min": target,
            "suggestion": f"If your knee feels comfortable on an easy run, try about {target} "
                          "steps/min for 1 minute at the same easy pace. Use shorter steps, "
                          "then return to your usual stride. Skip it if it feels worse.",
            "check": "Note knee comfort after the run and the next morning.",
            "basis": "Step-rate studies found lower per-step knee load at higher cadence "
                     "without increasing speed. The trial is optional and does not establish "
                     "a change in pain, injury risk or cumulative load.",
            "source": "https://pubmed.ncbi.nlm.nih.gov/20581720/"}


def suggestions(m: dict[str, Any], form: dict[str, Any], eff: float | None, *,
                cadence_experiment: dict[str, Any] | None = None) -> list[str]:
    out = [cadence_experiment["suggestion"]] if cadence_experiment else []
    cad = form.get("cadence_spm") or {}
    if not cadence_experiment and cad.get("vs_usual_pct", 0) < -3:
        out.append("Cadence was below your usual at this pace. Check terrain and how your "
                   "stride felt on another easy run at the same pace.")
    gct = form.get("ground_contact_ms")
    if gct and gct.get("vs_usual_pct", 0) > 4:
        out.append("Ground contact was longer than your usual at this pace. Compare on a "
                   "similar surface and check how your legs felt.")
    if m.get("decoupling_pct") is not None and m["decoupling_pct"] > 5:
        out.append(f"Speed per heartbeat fell {m['decoupling_pct']:.1f}% in the second half. Compare "
                   "another steady run and check heat, hills, fuelling and sensor fit.")
    if m.get("split_cv_pct") and m["split_cv_pct"] > 8:
        out.append("For your next steady run, start the first kilometre at an easy effort "
                   "and aim to hold it on level ground.")
    if not out:
        if any("vs_usual_pct" in value for value in form.values()):
            out.append("No large changes in the form measures we could compare at this pace.")
        else:
            out.append("Not enough comparable earlier runs to assess your usual form.")
    return out


def form_trends(
    conn: sqlite3.Connection, days_runs: int = 60,
    *, read_metrics: Callable[[sqlite3.Connection, int], dict | None] | None = None,
) -> dict[str, Any]:
    hist = list(reversed(_history(conn, None, days_runs, read_metrics)))
    lines = personal_lines(hist)
    series = [{"date": h["start"][:10], "pace_s_per_km": round(1000 / h["avg_speed"]),
               "cadence_spm": h.get("cadence_spm"), "step_length_m": h.get("step_length_m"),
               "ground_contact_ms": h.get("ground_contact_ms"),
               "vertical_ratio_pct": h.get("vertical_ratio_pct"),
               "efficiency_factor": h.get("efficiency_factor")} for h in hist]
    return {"runs": len(series), "series": series, "personal_lines": lines,
            "note": "Cadence and stride rise with speed; compare each run with the personal line "
                    "at the same pace, not with other runs."}


# --------------------------------------------------------------------------- test tracking
def test_runs(
    conn: sqlite3.Connection, tolerance: float = 0.10,
    *, read_metrics: Callable[[sqlite3.Connection, int], dict | None] | None = None,
) -> dict[str, Any]:
    """Standardised test tracking (roadmap 8.11) without asking you to run special tests.

    Use steady outdoor runs within +/-10 % of the median steady-run distance.
    Report the change in recorded grade-adjusted speed per heartbeat over time.
    """
    from garmin_mcp.coaching import _pace, run_metrics
    from garmin_mcp.engine import theil_sen
    from garmin_mcp.loads import RUN_TYPES

    rows = []
    for aid, ts, name, dist in conn.execute(
            f"SELECT activity_id, start_time_local, name, distance_m FROM activities "
            f"WHERE type IN ({','.join('?' * len(RUN_TYPES))}) AND fit_parsed=1 "
            "AND distance_m > 0 AND julianday(start_time_local) IS NOT NULL "
            "ORDER BY julianday(start_time_local)", RUN_TYPES):
        m = (read_metrics or run_metrics)(conn, aid)
        if m and m.get("efficiency_factor") and m.get("steady"):
            rows.append({"activity_id": aid, "date": ts[:10], "km": round((dist or 0) / 1000, 2),
                         "name": name, "ef": m["efficiency_factor"], "avg_hr": m["avg_hr"],
                         "pace": _pace(m["avg_speed"]), "decoupling_pct": m["decoupling_pct"]})
    if not rows:
        return {"available": False, "reason": "no steady runs with second-by-second data yet"}
    kms = sorted(r["km"] for r in rows)
    ref = statistics.median(kms)
    same = [r for r in rows if abs(r["km"] - ref) <= tolerance * ref]
    distinct_days = len({r["date"] for r in same})
    out: dict[str, Any] = {"available": distinct_days >= 3, "reference_km": round(ref, 1),
                           "runs": same,
                           "method": "steady runs within +/-10 % of your usual distance; "
                                     "efficiency factor = graded m/min per bpm"}
    if out["available"]:
        d0 = date.fromisoformat(same[0]["date"])
        slope = theil_sen([((date.fromisoformat(r["date"]) - d0).days, r["ef"]) for r in same])
        first, last = same[0]["ef"], same[-1]["ef"]
        out.update(ef_change_per_90d_pct=round(slope * 90 / statistics.fmean(
            r["ef"] for r in same) * 100, 1), first_ef=first, latest_ef=last,
            meaning="Positive means more grade-adjusted speed per heartbeat in this sample. "
                    "Check whether the trend repeats on similar runs. Heat, course and wrist "
                    "heart-rate accuracy can change this measure.")
    else:
        out["reason"] = "Needs comparable runs on at least three separate dates."
    return out
