"""Phase 3: recovery & readiness, computed transparently from your own baselines.

Methods (see METRICS.md §Recovery and VERIFICATION_LOG.md):
- HRV: nightly overnight HRV (Garmin's overnight RMSSD average). ln-transform, 7-day rolling
  mean, compared with a normal band = baseline mean ± 0.5 SD (smallest worthwhile change).
  Rolling 7-day ln RMSSD + SWC: AIS HRV best-practice guide; Plews et al. 2012-2014.
  Baseline window of 60 days is OUR design choice (no primary source fixes it; one study used a
  42-day EWMA). Needs >= 21 nights, matching Garmin's ~3 weeks before HRV status appears.
- RHR / respiration: today's value vs 60-day mean and SD (z-score).
- Sleep: last night vs 28-day personal norm; 7-day debt vs need (Garmin sleep need when
  available, else an 8 h planning fallback); bedtime consistency = SD of sleep start.
- Readiness (ours): mean of signed z-scores of the available components, each shown. This is a
  transparent heuristic; no validated composite exists. Garmin's readiness is shown beside it.
- Illness/strain flag: >= 2 of {HRV z < -1, RHR z > +1, respiration z > +1} on each of the last
  2 days (pattern reported before illness; heuristic, not a diagnosis).
"""

from __future__ import annotations

import math
import sqlite3
import statistics
from datetime import date, timedelta
from typing import Any

BASELINE_DAYS = 60
MIN_BASELINE_NIGHTS = 21
SWC_FACTOR = 0.5
SLEEP_NORM_DAYS = 28
DEFAULT_SLEEP_NEED_H = 8.0  # shared planning fallback, not a measured individual requirement
MIN_SLEEP_BASELINE_NIGHTS = 14
MIN_VALID_NIGHT_H = 3.0  # shorter records are treated as incomplete (watch off, nap only)


def _days_back(day: str, n: int) -> list[str]:
    d = date.fromisoformat(day)
    return [(d - timedelta(days=i)).isoformat() for i in range(n - 1, -1, -1)]


def _series(conn: sqlite3.Connection, sql: str, start: str, end: str) -> dict[str, float]:
    return {d: v for d, v in conn.execute(sql, (start, end)) if isinstance(v, (int, float))}


def load_series(conn: sqlite3.Connection, end: str, days: int) -> dict[str, dict[str, float]]:
    start = (date.fromisoformat(end) - timedelta(days=days - 1)).isoformat()
    hrv = _series(conn, "SELECT day, last_night_avg FROM hrv WHERE day BETWEEN ? AND ?",
                  start, end)
    hs_hrv = _series(conn, "SELECT day, hrv FROM health_status WHERE day BETWEEN ? AND ?",
                     start, end)
    resp = _series(conn, "SELECT day, avg_respiration FROM sleep WHERE day BETWEEN ? AND ?",
                   start, end)
    hs_resp = _series(conn, "SELECT day, respiration FROM health_status "
                      "WHERE day BETWEEN ? AND ?", start, end)
    out = {
        "hrv": {**hs_hrv, **hrv},  # Garmin HRV status value wins; health status fills history
        "rhr": _series(conn, "SELECT day, resting_hr FROM daily WHERE day BETWEEN ? AND ?",
                       start, end),
        "resp": {**hs_resp, **resp},
        "sleep_h": {d: v / 3600 for d, v in _series(
            conn, "SELECT day, sleep_s FROM sleep WHERE day BETWEEN ? AND ?", start, end).items()
            if v / 3600 >= MIN_VALID_NIGHT_H},
        "sleep_incomplete_h": {d: v / 3600 for d, v in _series(
            conn, "SELECT day, sleep_s FROM sleep WHERE day BETWEEN ? AND ?", start, end).items()
            if v / 3600 < MIN_VALID_NIGHT_H},
        "sleep_need_h": {d: v / 60 for d, v in _series(
            conn, "SELECT day, sleep_need_min FROM sleep WHERE day BETWEEN ? AND ?",
            start, end).items() if v > 0},
    }
    # Days tagged sick / injured / break are left out of baselines (Bevel's activity status),
    # except the day being scored, so being ill doesn't redefine "normal".
    from garmin_mcp.health import status_days

    skip = {d for d in status_days(conn) if d != end}
    if skip:
        out = {k: {d: v for d, v in ser.items() if d not in skip} for k, ser in out.items()}
    return out


def _stats(values: list[float]) -> tuple[float, float] | None:
    if len(values) < 2:
        return None
    return statistics.fmean(values), statistics.stdev(values)


def _z(value: float | None, ref: tuple[float, float] | None) -> float | None:
    if value is None or ref is None or ref[1] == 0:
        return None
    return round((value - ref[0]) / ref[1], 2)


def hrv_status(series: dict[str, float], day: str) -> dict[str, Any]:
    ln = {d: math.log(v) for d, v in series.items() if v > 0}
    week = [ln[d] for d in _days_back(day, 7) if d in ln]
    base = [ln[d] for d in _days_back(day, BASELINE_DAYS) if d in ln]
    out: dict[str, Any] = {"nights_in_baseline": len(base), "nights_in_7d": len(week),
                           "last_night_ms": series.get(day)}
    if len(base) < MIN_BASELINE_NIGHTS or len(week) < 4:
        out["state"] = "calibrating"
        out["meaning"] = (f"Needs {MIN_BASELINE_NIGHTS} nights in the last {BASELINE_DAYS} days "
                          "and 4 of the last 7 nights.")
        return out
    mean, sd = statistics.fmean(base), statistics.stdev(base)
    lo, hi = mean - SWC_FACTOR * sd, mean + SWC_FACTOR * sd
    m7 = statistics.fmean(week)
    cv7 = statistics.stdev(week) / m7 * 100 if len(week) > 1 else None
    state = "within normal" if lo <= m7 <= hi else ("below normal" if m7 < lo else "above normal")
    out.update({
        "ln_rmssd_7d": round(m7, 3),
        "normal_band_ln": [round(lo, 3), round(hi, 3)],
        "rolling_7d_ms": round(math.exp(m7), 1),
        "normal_band_ms": [round(math.exp(lo), 1), round(math.exp(hi), 1)],
        "cv_7d_pct": round(cv7, 1) if cv7 is not None else None,
        "state": state,
        "z": _z(m7, (mean, sd)),
        "meaning": {
            "within normal": "Autonomic recovery is in your usual range.",
            "below normal": "7-day HRV below your normal range: accumulated fatigue, illness, "
                            "poor sleep, alcohol or life stress are common causes.",
            "above normal": "7-day HRV above your normal range: usually good recovery; if it "
                            "comes with fatigue it can also reflect very high load.",
        }[state],
    })
    return out


def sleep_status(series: dict[str, dict[str, float]], day: str) -> dict[str, Any]:
    sleep = series["sleep_h"]
    prior = [sleep[d] for d in _days_back(day, SLEEP_NORM_DAYS + 1)[:-1] if d in sleep]
    norm = _stats(prior) if len(prior) >= MIN_SLEEP_BASELINE_NIGHTS else None
    week = _days_back(day, 7)
    debt = 0.0
    nights = 0
    inputs = []
    for d in week:
        if d in sleep:
            need = series["sleep_need_h"].get(d, DEFAULT_SLEEP_NEED_H)
            debt += max(0.0, need - sleep[d])
            nights += 1
            inputs.append({"day": d, "sleep_h": round(sleep[d], 2), "need_h": need,
                           "shortfall_h": round(max(0.0, need - sleep[d]), 2),
                           "source": "Garmin sleep need" if d in series["sleep_need_h"]
                           else "8 h planning fallback"})
    incomplete = [d for d in week if d in series["sleep_incomplete_h"]]
    return {
        "last_night_h": round(sleep[day], 2) if day in sleep else None,
        "incomplete_records_7d": incomplete,
        "norm_28d_h": round(norm[0], 2) if norm else None,
        "z": _z(sleep.get(day), norm),
        "debt_7d_h": round(debt, 1) if nights else None, "valid_nights_7d": nights,
        "debt_inputs": inputs, "baseline_nights": len(prior),
        "debt_note": f"sum of shortfalls on valid nights (>= {MIN_VALID_NIGHT_H:.0f} h); missing "
                     "or incomplete nights are not counted",
        "need_source": "Garmin sleep need where available; otherwise 8 h planning fallback",
    }


def bedtime_consistency(conn: sqlite3.Connection, day: str, nights: int = 14) -> float | None:
    """SD of sleep-start time in minutes over the last `nights` (circular around noon)."""
    start = (date.fromisoformat(day) - timedelta(days=nights - 1)).isoformat()
    mins = []
    for (ts,) in conn.execute("SELECT sleep_start FROM sleep WHERE day BETWEEN ? AND ? AND "
                              "sleep_start IS NOT NULL AND sleep_s > 3*3600", (start, day)):
        h, m = int(ts[11:13]), int(ts[14:16])
        mins.append((h * 60 + m - 12 * 60) % 1440)  # minutes after 12:00 UTC: no midnight wrap
    return round(statistics.stdev(mins), 0) if len(mins) >= 5 else None


def _metric_z(series: dict[str, float], day: str) -> float | None:
    prior = [series[d] for d in _days_back(day, BASELINE_DAYS + 1)[:-1] if d in series]
    ref = _stats(prior)
    if ref is None or len(prior) < MIN_BASELINE_NIGHTS:
        return None
    return _z(series.get(day), ref)


def illness_flag(series: dict[str, dict[str, float]], day: str) -> dict[str, Any]:
    days = _days_back(day, 2)
    per_day = []
    for d in days:
        hz = _metric_z({k: math.log(v) for k, v in series["hrv"].items() if v > 0}, d)
        rz = _metric_z(series["rhr"], d)
        pz = _metric_z(series["resp"], d)
        signals = [n for n, hit in (("HRV low", hz is not None and hz < -1),
                                    ("resting HR high", rz is not None and rz > 1),
                                    ("respiration high", pz is not None and pz > 1)) if hit]
        per_day.append({"day": d, "hrv_z": hz, "rhr_z": rz, "respiration_z": pz,
                        "signals": signals})
    raised = all(len(x["signals"]) >= 2 for x in per_day)
    return {"raised": raised, "days": per_day,
            "rule": ">=2 of HRV z<-1, resting HR z>+1, respiration z>+1 on both of the last 2 "
                    "days (heuristic, not a diagnosis)"}


def readiness(conn: sqlite3.Connection, day: str) -> dict[str, Any]:
    series = load_series(conn, day, BASELINE_DAYS + 7)
    hrv = hrv_status(series["hrv"], day)
    slp = sleep_status(series, day)
    rhr_z = _metric_z(series["rhr"], day)
    resp_z = _metric_z(series["resp"], day)
    components = [
        {"name": "HRV (7-day vs normal)", "z": hrv.get("z"), "sign": +1},
        {"name": "Resting HR (today vs 60-day)", "z": rhr_z, "sign": -1},
        {"name": "Sleep (last night vs 28-day)", "z": slp["z"], "sign": +1},
        {"name": "Respiration (last night vs 60-day)", "z": resp_z, "sign": -1},
    ]
    used = [c for c in components if c["z"] is not None]
    for c in components:
        c["contribution"] = round(c["sign"] * max(-3, min(3, c["z"])), 2) \
            if c["z"] is not None else None
    score = round(statistics.fmean(c["contribution"] for c in used), 2) if used else None
    if score is None:
        state = "calibrating"
    elif score >= 0.5:
        state = "fresher than usual"
    elif score >= -0.5:
        state = "normal"
    elif score >= -1.0:
        state = "below usual"
    else:
        state = "well below usual"
    garmin = conn.execute("SELECT score, level, feedback, recovery_time_min FROM readiness "
                          "WHERE day=?", (day,)).fetchone()
    drivers = sorted((c for c in components if c["contribution"] is not None),
                     key=lambda c: c["contribution"])
    return {
        "day": day,
        "ours": {"composite_z": score, "state": state, "components": components,
                 "holding_back": [c["name"] for c in drivers if c["contribution"] < -0.5],
                 "helping": [c["name"] for c in drivers[::-1] if c["contribution"] > 0.5],
                 "method": "mean of signed, clipped z-scores vs your own baselines "
                           "(transparent heuristic; see METRICS.md)"},
        "garmin": {"score": garmin[0], "level": garmin[1], "feedback": garmin[2],
                   "recovery_time_h": round(garmin[3] / 60, 1) if garmin[3] else None}
        if garmin else None,
        "hrv": hrv, "sleep": {**slp, "bedtime_sd_min_14d": bedtime_consistency(conn, day)},
        "illness_flag": illness_flag(series, day),
        "activity_status": __import__("garmin_mcp.health", fromlist=["x"]).status_days(
            conn).get(day),
    }


def recovery_trend(conn: sqlite3.Connection, end: str, days: int = 28) -> dict[str, Any]:
    rows = []
    for d in _days_back(end, days):
        r = readiness(conn, d)
        rows.append({"day": d, "composite_z": r["ours"]["composite_z"],
                     "state": r["ours"]["state"],
                     "hrv_7d_ms": r["hrv"].get("rolling_7d_ms"),
                     "hrv_band_ms": r["hrv"].get("normal_band_ms"),
                     "sleep_h": r["sleep"]["last_night_h"],
                     "garmin_readiness": r["garmin"]["score"] if r["garmin"] else None,
                     "illness_flag": r["illness_flag"]["raised"]})
    return {"from": rows[0]["day"], "to": end, "days": rows}


def suggestion(r: dict[str, Any]) -> dict[str, str]:
    """Rule-based training suggestion; every branch states its reason."""
    garmin_level = (r["garmin"] or {}).get("level")
    garmin_note = f"Garmin readiness {garmin_level}" if garmin_level else "Garmin readiness unavailable"
    state = r["ours"]["state"]
    status = r.get("activity_status")
    if status:
        return {"suggest": "training advice paused",
                "why": f"today is tagged '{status}'; rest and recover, then remove the tag"}
    if r["illness_flag"]["raised"]:
        return {"suggest": "rest or very easy movement",
                "why": "illness/strain pattern on two consecutive days"}
    if state == "well below usual" or garmin_level in ("POOR",):
        return {"suggest": "rest or easy recovery session",
                "why": f"our readiness is {state}; {garmin_note}"}
    if state == "below usual" or garmin_level == "LOW":
        return {"suggest": "easy aerobic only, skip intensity",
                "why": f"our readiness is {state}; {garmin_note}"}
    if state == "calibrating":
        return {"suggest": "not enough recovery data for a training suggestion",
                "why": "Personal baselines are still calibrating; " + garmin_note}
    if state == "fresher than usual" and garmin_level in ("HIGH", "PRIME"):
        return {"suggest": "good day for a key session (intervals, tempo or long run)",
                "why": "both our readiness and Garmin's are high"}
    return {"suggest": "planned training is fine",
            "why": f"our readiness is {state}; {garmin_note}"}
