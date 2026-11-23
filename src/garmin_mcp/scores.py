"""Phase 10: three glanceable daily scores (Whoop-style presentation, our own open formulas).

These are OUR scores, not Whoop's or Garmin's; each is defined below, shown beside Garmin's
nearest equivalent, and sense-checked against it (see `sense_checks`).

Recovery % (0-100)
    = 100 * Phi(composite_z), where composite_z is our transparent readiness (recovery.py:
    mean of signed, clipped z-scores of HRV, resting HR, sleep, respiration vs your baselines)
    and Phi is the standard normal CDF. 50 % = a normal day for you. Bands (Whoop-style):
    >= 67 green "recovered", 34-66 yellow "moderate", <= 33 red "low".
Sleep % (0-100+)
    = last night's sleep / sleep need * 100 (Whoop's "sleep performance" concept). Need =
    Garmin's sleep need when available, else 8 h (AASM/SRS adult guidance is >= 7 h; 8 h is the
    common midpoint used by consumer apps). Records < 3 h count as incomplete (no score).
Strain (0-21, log scale)
    = min(21, 6.3 * ln(1 + TRIMP_day / 20)). Log scale like Whoop: each extra point needs more
    work. Calibrated (design choice) so an easy 30-min run (TRIMP ~40-70) lands ~7-10, a hard
    2-hour effort (TRIMP ~250) ~16-17, and 21 is near-unreachable. First version anchored
    TRIMP 250 = 21, which put a 27-min easy run at 16 (too high; caught by sense check).
    Training sessions only (no all-day background strain yet).
Strain target
    from recovery: green 10-14, yellow 8-12, red 0-8 (heuristic bands, Whoop-style).
"""

from __future__ import annotations

import math
import sqlite3
import statistics
from datetime import date, timedelta
from typing import Any

from garmin_mcp import recovery

STRAIN_A, STRAIN_B = 6.3, 20.0
DEFAULT_NEED_H = 8.0
BANDS = ((67, "green", "recovered"), (34, "yellow", "moderate"), (0, "red", "low"))
TARGETS = {"green": (10, 14), "yellow": (8, 12), "red": (0, 8)}


def phi(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def strain_from_trimp(trimp: float) -> float:
    return round(min(21.0, STRAIN_A * math.log1p(max(trimp, 0) / STRAIN_B)), 1)


def band(pct: float | None) -> tuple[str, str] | tuple[None, None]:
    if pct is None:
        return None, None
    for lo, color, label in BANDS:
        if pct >= lo:
            return color, label
    return BANDS[-1][1], BANDS[-1][2]


def daily_scores(conn: sqlite3.Connection, day: str) -> dict[str, Any]:
    r = recovery.readiness(conn, day)
    z = r["ours"]["composite_z"]
    rec = round(100 * phi(z)) if z is not None else None
    color, label = band(rec)

    sleep_row = conn.execute("SELECT sleep_s, sleep_need_min, score FROM sleep WHERE day=?",
                             (day,)).fetchone()
    sleep_pct = need_h = hours = None
    if sleep_row and sleep_row[0] and sleep_row[0] >= 3 * 3600:
        hours = sleep_row[0] / 3600
        need_h = (sleep_row[1] / 60) if sleep_row[1] else DEFAULT_NEED_H
        sleep_pct = round(hours / need_h * 100)
    try:
        trimp = conn.execute("SELECT load FROM fitness WHERE day=?", (day,)).fetchone()
    except sqlite3.OperationalError:
        trimp = None
    strain = strain_from_trimp(trimp[0]) if trimp and trimp[0] is not None else 0.0
    target = TARGETS.get(color) if color else None
    garmin = r["garmin"] or {}
    return {
        "day": day,
        "recovery": {"pct": rec, "band": color, "label": label,
                     "calibrating": z is None,
                     "signals_used": sum(c["z"] is not None for c in r["ours"]["components"]),
                     "signals_total": len(r["ours"]["components"]),
                     "drivers_down": r["ours"]["holding_back"], "drivers_up": r["ours"]["helping"],
                     "garmin_readiness": garmin.get("score"),
                     "garmin_level": garmin.get("level")},
        "sleep": {"pct": sleep_pct, "hours": round(hours, 2) if hours else None,
                  "need_h": round(need_h, 2) if need_h else None,
                  "need_source": "Garmin sleep need" if sleep_row and sleep_row[1] else
                  f"{DEFAULT_NEED_H:.0f} h default",
                  "garmin_sleep_score": sleep_row[2] if sleep_row else None,
                  "debt_7d_h": r["sleep"]["debt_7d_h"],
                  "incomplete": bool(sleep_row and sleep_row[0] and sleep_row[0] < 3 * 3600)},
        "strain": {"value": strain, "trimp": round(trimp[0], 1) if trimp and trimp[0] else 0.0,
                   "target_range": target},
    }


def bedtime_suggestion(conn: sqlite3.Connection, day: str, wake_local: str | None = None
                       ) -> dict[str, Any]:
    """Suggested bedtime = usual wake time - (need + share of 7-day debt), debt repaid over a
    week (max +1 h/night). Usual wake time = median of the last 14 valid nights (local)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from garmin_mcp import engine

    tz = engine._tz(conn)
    lo = (date.fromisoformat(day) - timedelta(days=14)).isoformat()
    wakes = []
    for (ts,) in conn.execute("SELECT sleep_end FROM sleep WHERE day BETWEEN ? AND ? AND "
                              "sleep_end IS NOT NULL AND sleep_s >= 3*3600", (lo, day)):
        t = datetime.fromisoformat(ts).replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
        wakes.append(t.hour * 60 + t.minute)
    if len(wakes) < 5:
        return {"available": False, "reason": "needs 5 valid nights in 14 days"}
    wakes.sort()
    wake = wakes[len(wakes) // 2]
    s = daily_scores(conn, day)["sleep"]
    need = (s["need_h"] or DEFAULT_NEED_H) * 60
    extra = min(60, (s["debt_7d_h"] or 0) * 60 / 7)
    bed = (wake - need - extra) % 1440
    return {"available": True, "usual_wake": f"{wake // 60:02d}:{wake % 60:02d}",
            "suggested_bedtime": f"{int(bed) // 60:02d}:{int(bed) % 60:02d}",
            "includes_debt_repayment_min": round(extra), "timezone": str(tz)}


def history(conn: sqlite3.Connection, end: str, days: int = 30) -> list[dict[str, Any]]:
    out = []
    for i in range(days - 1, -1, -1):
        d = (date.fromisoformat(end) - timedelta(days=i)).isoformat()
        s = daily_scores(conn, d)
        out.append({"day": d, "recovery": s["recovery"]["pct"], "band": s["recovery"]["band"],
                    "sleep_pct": s["sleep"]["pct"], "strain": s["strain"]["value"],
                    "garmin_readiness": s["recovery"]["garmin_readiness"]})
    return out


def sense_checks(conn: sqlite3.Connection, end: str, days: int = 180) -> list[dict[str, Any]]:
    """Our scores vs Garmin's nearest equivalents (should move together, not be equal)."""
    from garmin_mcp.loads import _pearson

    h = history(conn, end, days)
    checks = []
    pairs = [(x["recovery"], x["garmin_readiness"]) for x in h
             if x["recovery"] is not None and x["garmin_readiness"] is not None]
    r = _pearson([p[0] for p in pairs], [p[1] for p in pairs])
    checks.append({"check": "Recovery % vs Garmin Training Readiness", "ok": None if r is None
                   else r > 0.3, "detail": f"r = {r:.2f} over {len(pairs)} days" if r is not None
                   else "not enough days", "tolerance": "r > 0.3 (different inputs: Garmin adds "
                   "load and recovery time)"})
    rows = conn.execute("SELECT day, score FROM sleep WHERE day > ? AND day <= ? AND "
                        "sleep_s >= 3*3600 AND score IS NOT NULL",
                        ((date.fromisoformat(end) - timedelta(days=days)).isoformat(), end)
                        ).fetchall()
    sp = {x["day"]: x["sleep_pct"] for x in h}
    pairs = [(sp[d], s) for d, s in rows if sp.get(d) is not None]
    r = _pearson([p[0] for p in pairs], [p[1] for p in pairs])
    checks.append({"check": "Sleep % vs Garmin sleep score", "ok": None if r is None else r > 0.3,
                   "detail": f"r = {r:.2f} over {len(pairs)} nights" if r is not None
                   else "not enough nights",
                   "tolerance": "r > 0.3 (Garmin's score also weighs stages and stress)"})
    vals = [x["strain"] for x in h]
    checks.append({"check": "Strain within 0-21", "ok": all(0 <= v <= 21 for v in vals),
                   "detail": f"max {max(vals) if vals else None}", "tolerance": "0-21"})
    rec = [x["recovery"] for x in h if x["recovery"] is not None]
    if rec:
        share_green = sum(v >= 67 for v in rec) / len(rec)
        share_red = sum(v <= 33 for v in rec) / len(rec)
        checks.append({"check": "Recovery bands are balanced (not stuck)",
                       "ok": 0.05 <= share_green <= 0.6 and 0.03 <= share_red <= 0.5,
                       "detail": f"green {share_green:.0%}, red {share_red:.0%} of {len(rec)} days",
                       "tolerance": "green 5-60 %, red 3-50 % (a z-based score should spread)"})
    return checks


def weight_study(conn: sqlite3.Connection, end: str, days: int = 180) -> dict[str, Any]:
    """Does each readiness signal carry information, and would other weights do better?

    For every day: the four clipped component scores (HRV 7-day, resting HR, sleep, breathing).
    Outcomes, each checked separately:
      - next night's HRV (ln, vs the previous 60 nights, z) - physiology one day ahead;
      - Garmin readiness the same day - Garmin's own view, for comparison only.
    Composites compared: equal weights (current), without breathing, HRV + RHR only.
    Rule: weights change only if a variant beats the current one on BOTH outcomes by > 0.05 r.
    """
    from garmin_mcp.engine import _pearson

    e = date.fromisoformat(end)
    hrv = dict(conn.execute("SELECT day, COALESCE(h.last_night_avg, s.hrv) FROM health_status s "
                            "LEFT JOIN hrv h USING(day) WHERE day <= ?", (end,)).fetchall())
    garmin = dict(conn.execute("SELECT day, score FROM readiness WHERE day <= ?", (end,)))

    def hrv_z(d: str) -> float | None:
        v = hrv.get(d)
        if not v:
            return None
        dd = date.fromisoformat(d)
        prior = [math.log(hrv[x]) for x in ((dd - timedelta(days=k)).isoformat()
                                            for k in range(1, 61)) if hrv.get(x)]
        if len(prior) < 21:
            return None
        sd = statistics.pstdev(prior)
        return (math.log(v) - statistics.fmean(prior)) / sd if sd else None

    names = ["HRV (7-day vs normal)", "Resting HR (today vs 60-day)",
             "Sleep (last night vs 28-day)", "Respiration (last night vs 60-day)"]
    rows = []
    for k in range(days, 0, -1):
        d = (e - timedelta(days=k)).isoformat()
        r = recovery.readiness(conn, d)
        comp = {c["name"]: c["contribution"] for c in r["ours"]["components"]}
        nxt = hrv_z((date.fromisoformat(d) + timedelta(days=1)).isoformat())
        rows.append((comp, nxt, garmin.get(d)))

    def corr(f: Any, idx: int) -> dict[str, Any]:
        pts = [(f(c), o[idx - 1]) for c, *o in rows]
        pts = [(a, b) for a, b in pts if a is not None and b is not None]
        r = _pearson([a for a, _ in pts], [b for _, b in pts]) if len(pts) >= 30 else None
        return {"r": round(r, 3) if r is not None else None, "n": len(pts)}

    def mean_of(keys: list[str]) -> Any:
        def f(c: dict[str, float | None]) -> float | None:
            v = [c[k] for k in keys if c.get(k) is not None]
            return statistics.fmean(v) if v else None
        return f

    signals = {n: {"next_night_hrv": corr(lambda c, n=n: c.get(n), 1),
                   "garmin_readiness": corr(lambda c, n=n: c.get(n), 2)} for n in names}
    variants = {"equal weights (current)": names, "without breathing": names[:3],
                "HRV + resting HR": names[:2]}
    comp = {v: {"next_night_hrv": corr(mean_of(k), 1), "garmin_readiness": corr(mean_of(k), 2)}
            for v, k in variants.items()}
    base = comp["equal weights (current)"]
    better = [v for v, c in comp.items() if v != "equal weights (current)" and all(
        (c[o]["r"] or -1) > (base[o]["r"] or -1) + 0.05 for o in c)]
    return {"window_days": days, "signals": signals, "composites": comp,
            "decision": f"switch to: {better[0]}" if better else
                        "keep equal weights (no variant better on both outcomes by > 0.05 r)",
            "method": weight_study.__doc__.strip().splitlines()[0]}
