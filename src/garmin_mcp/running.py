"""Running workout breakdown: form ratings, pace-matched comparisons, trends and what to work on.

Sources and conventions (see METRICS.md "Running breakdown"):
- Garmin running-dynamics colour gauges (FR955 owner's manual, percentiles of Garmin's runner
  database). Values below are the published gauge bands; verify against the current manual.
- Cadence and stride length rise with speed, so a raw comparison is misleading. We fit your own
  cadence-speed and stride-speed lines across runs (least squares) and report each run versus
  what *you* usually do at that pace.
- Running effectiveness (Coggan/WKO): speed (m/s) / power (W/kg). Garmin wrist power is not
  Stryd power, so compare only with yourself.
- Knee loading: raising cadence 5-10 % at the same speed reduces knee and hip load
  (Heiderscheit et al. 2011, Med Sci Sports Exerc 43:296). Suggested gently because of a weak
  right knee; never more than +5 % per block.
"""

from __future__ import annotations

import sqlite3
import statistics
from typing import Any

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


def _history(conn: sqlite3.Connection, before: str | None, limit: int = 120) -> list[dict]:
    from garmin_mcp.coaching import run_metrics

    q = ("SELECT activity_id, start_time_local FROM activities WHERE type LIKE '%run%' AND "
         "fit_parsed=1 " + ("AND start_time_local < ? " if before else "") +
         "ORDER BY start_time_local DESC LIMIT ?")
    out = []
    for aid, ts in conn.execute(q, (before, limit) if before else (limit,)).fetchall():
        m = run_metrics(conn, aid)
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
                          "runs": len(pts)}
    return lines


def running_breakdown(conn: sqlite3.Connection, aid: int, weight_kg: float | None = None
                      ) -> dict[str, Any]:
    from garmin_mcp.coaching import _pace, run_metrics

    m = run_metrics(conn, aid)
    if not m:
        return {"available": False, "reason": "no second-by-second data for this run"}
    start = conn.execute("SELECT start_time_local FROM activities WHERE activity_id=?",
                         (aid,)).fetchone()
    hist = _history(conn, start[0] if start else None)
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
        if ln:
            exp = ln["intercept"] + ln["slope_per_ms"] * speed
            row["your_usual_at_this_pace"] = round(exp, 3)
            row["vs_usual_pct"] = round((v - exp) / exp * 100, 1)
        form[key] = row
    eff = None
    if m.get("power_w") and weight_kg:
        eff = round(speed / (m["power_w"] / weight_kg), 3)
    return {"available": True, "activity_id": aid, "pace": _pace(speed),
            "avg_hr": m.get("avg_hr"), "power_w": m.get("power_w"),
            "running_effectiveness": eff, "form": form,
            "pacing": {"km_splits": m.get("km_splits"), "split_variation_pct":
                       m.get("split_cv_pct"), "negative_split": m.get("negative_split"),
                       "hr_drift_bpm": m.get("hr_drift_bpm"),
                       "decoupling_pct": m.get("decoupling_pct")},
            "work_on": suggestions(m, form, eff),
            "comparison_runs": len(hist)}


def suggestions(m: dict[str, Any], form: dict[str, Any], eff: float | None) -> list[str]:
    out = []
    cad = form.get("cadence_spm")
    if cad and cad["value"] < 170:
        target = round(cad["value"] * 1.05)
        out.append(f"Cadence {cad['value']:.0f} spm: try about {target} spm on easy runs (+5 %), "
                   "same pace, shorter quicker steps. Higher cadence lowers knee load, which "
                   "suits your right knee. Use the watch metronome for 5-min blocks.")
    vr = form.get("vertical_ratio_pct")
    if vr and vr["garmin_gauge"] and vr["garmin_gauge"]["colour"] in ("orange", "red"):
        out.append("Vertical ratio is high (bouncing more than moving forward): think 'run "
                   "quiet', add strides and calf/hip strength twice a week.")
    gct = form.get("ground_contact_ms")
    if gct and gct.get("vs_usual_pct", 0) > 4:
        out.append("Ground contact was longer than your usual at this pace: often fatigue or "
                   "tired legs; check sleep and recovery before the next hard run.")
    if m.get("decoupling_pct") is not None and m["decoupling_pct"] > 5:
        out.append(f"Heart rate drifted {m['decoupling_pct']:.1f} % against pace: aerobic base "
                   "is the limiter at this pace. More easy-zone volume will help.")
    if m.get("split_cv_pct") and m["split_cv_pct"] > 8:
        out.append("Pacing was uneven across kilometres: start slower and hold a steady effort.")
    if not out:
        out.append("Form and pacing look in line with your usual. Keep building easy volume.")
    return out


def form_trends(conn: sqlite3.Connection, days_runs: int = 60) -> dict[str, Any]:
    hist = list(reversed(_history(conn, None, days_runs)))
    lines = personal_lines(hist)
    series = [{"date": h["start"][:10], "pace_s_per_km": round(1000 / h["avg_speed"]),
               "cadence_spm": h.get("cadence_spm"), "step_length_m": h.get("step_length_m"),
               "ground_contact_ms": h.get("ground_contact_ms"),
               "vertical_ratio_pct": h.get("vertical_ratio_pct"),
               "efficiency_factor": h.get("efficiency_factor")} for h in hist]
    return {"runs": len(series), "series": series, "personal_lines": lines,
            "note": "Cadence and stride rise with speed; compare each run with the personal line "
                    "at the same pace, not with other runs."}
