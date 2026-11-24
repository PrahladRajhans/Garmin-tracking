"""Phase 8: analytics & insight engine (levels 1-3). Feeds MCP tools and the dashboard.

Statistical rules (ROADMAP Phase 8; research_notes/.../insights_and_dashboards.md):
- Relationships use baseline-adjusted values (value - its trailing 28-day mean), so seasonal
  drift and long trends don't create fake correlations.
- A relationship is reported only with >= 30 paired days; strength = Pearson r with a 95 %
  moving-block bootstrap CI (block = 7 days, 1000 resamples, fixed seed).
- When many pairs are scanned, p-values (from the bootstrap) are Benjamini-Hochberg adjusted;
  only q < 0.10 are called "notable". Wording is always "associated with", never "causes".
- Trends use the Theil-Sen slope (robust to outliers); "flat" when the 95 % bootstrap CI of the
  slope includes 0.
"""

from __future__ import annotations

import math
import random
import sqlite3
import statistics
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

MIN_PAIRS = 30
BASELINE_DAYS = 28
BOOT = 1000
BLOCK = 7
SEED = 7


# --------------------------------------------------------------------------- daily features
def _tz(conn: sqlite3.Connection) -> ZoneInfo:
    import os

    from garmin_mcp import athlete

    name = os.getenv("GARMIN_TZ") or athlete.get(conn, "timezone") or "UTC"
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC")


def features(conn: sqlite3.Connection, start: str, end: str) -> dict[str, dict[str, float]]:
    """One row of numeric features per day (missing = absent key)."""
    from garmin_mcp.recovery import nightly_hrv

    tz = _tz(conn)
    out: dict[str, dict[str, float]] = {}

    def put(sql: str, mapping: dict[str, int]) -> None:
        for row in conn.execute(sql, (start, end)):
            day = row[0]
            for name, idx in mapping.items():
                v = row[idx]
                if isinstance(v, (int, float)) and math.isfinite(v):
                    out.setdefault(day, {})[name] = float(v)

    put("SELECT day, sleep_s/3600.0, score, avg_sleep_stress, avg_respiration FROM sleep "
        "WHERE day BETWEEN ? AND ? AND sleep_s >= 3*3600",
        {"sleep_h": 1, "sleep_score": 2, "sleep_stress": 3, "sleep_resp": 4})
    put("SELECT day, resting_hr, stress_avg, body_battery_max, steps, "
        "intensity_min_moderate + 2*intensity_min_vigorous FROM daily WHERE day BETWEEN ? AND ?",
        {"rhr": 1, "stress": 2, "bb_max": 3, "steps": 4, "intensity_min": 5})
    for day, value in nightly_hrv(conn, start, end).items():
        out.setdefault(day, {})["hrv"] = float(value)
    put("SELECT day, score FROM readiness WHERE day BETWEEN ? AND ?", {"garmin_readiness": 1})
    try:
        put("SELECT day, load, ctl, atl, tsb FROM fitness WHERE day BETWEEN ? AND ?",
            {"trimp": 1, "ctl": 2, "atl": 3, "tsb": 4})
    except sqlite3.OperationalError:
        pass
    # Bedtime (local hours after noon) and latest training end (local hour).
    for day, ts in conn.execute("SELECT day, sleep_start FROM sleep WHERE day BETWEEN ? AND ? "
                                "AND sleep_start IS NOT NULL AND sleep_s >= 3*3600",
                                (start, end)):
        local = datetime.fromisoformat(ts).replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
        out.setdefault(day, {})["bedtime_h"] = ((local.hour - 12) % 24) + local.minute / 60 + 12
    for start_gmt, dur in conn.execute(
            "SELECT start_time_gmt, duration_s FROM activities WHERE start_time_gmt IS NOT NULL "
            "AND substr(start_time_local,1,10) BETWEEN ? AND ?", (start, end)):
        t = datetime.fromisoformat(start_gmt).replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
        end_local = t + timedelta(seconds=dur or 0)
        d = end_local.date().isoformat()
        hour = end_local.hour + end_local.minute / 60
        row = out.setdefault(d, {})
        row["last_training_end_h"] = max(row.get("last_training_end_h", 0), hour)
    return out


# --------------------------------------------------------------------------- statistics
def _adjust(series: dict[str, float]) -> dict[str, float]:
    """Subtract the trailing 28-day mean (needs >= 10 prior values)."""
    days = sorted(series)
    out = {}
    for d in days:
        lo = (date.fromisoformat(d) - timedelta(days=BASELINE_DAYS)).isoformat()
        prior = [series[x] for x in days if lo <= x < d]
        if len(prior) >= 10:
            out[d] = series[d] - statistics.fmean(prior)
    return out


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if not sx or not sy:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / (sx * sy)


def _slope(xs: list[float], ys: list[float]) -> float | None:
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / sxx if sxx else None


def _block_bootstrap(pairs: list[tuple[float, float]], stat, rng: random.Random) -> list[float]:
    n = len(pairs)
    blocks = [pairs[i:i + BLOCK] for i in range(n - BLOCK + 1)] or [pairs]
    vals = []
    for _ in range(BOOT):
        sample: list[tuple[float, float]] = []
        while len(sample) < n:
            sample.extend(rng.choice(blocks))
        sample = sample[:n]
        v = stat([p[0] for p in sample], [p[1] for p in sample])
        if v is not None:
            vals.append(v)
    return sorted(vals)


def pair_points(feat: dict[str, dict[str, float]], x: str, y: str,
                lag: int = 0) -> list[tuple[str, float, float]]:
    """(day, adjusted x on day, adjusted y on day+lag): the points behind a relationship."""
    xs = _adjust({d: v[x] for d, v in feat.items() if x in v})
    ys = _adjust({d: v[y] for d, v in feat.items() if y in v})
    out = []
    for d, xv in sorted(xs.items()):
        d2 = (date.fromisoformat(d) + timedelta(days=lag)).isoformat()
        if d2 in ys:
            out.append((d, xv, ys[d2]))
    return out


def explore(conn: sqlite3.Connection, end: str, days: int = 365, top: int = 8) -> dict[str, Any]:
    """Eligible pairs with their points, prioritizing those that pass the evidence rule."""
    rel = relationships(conn, end, days)
    start = (date.fromisoformat(end) - timedelta(days=days)).isoformat()
    feat = features(conn, start, end)
    ok = sorted((r for r in rel["all"] if r.get("status") == "ok"),
                key=lambda r: (not r["notable"], -abs(r["r"])))
    for r in ok[:top]:
        r["points"] = [(d, round(a, 3), round(b, 3))
                       for d, a, b in pair_points(feat, r["x"], r["y"], r["lag_days"])]
    return {"pairs": ok[:top], "tested": rel["pairs_tested"], "eligible": len(ok),
            "notable": len(rel["notable"]), "method": rel["method"]}


def relationship(feat: dict[str, dict[str, float]], x: str, y: str, lag: int = 0,
                 rng: random.Random | None = None) -> dict[str, Any]:
    """Association between baseline-adjusted x on day d and y on day d+lag."""
    rng = rng or random.Random(SEED)
    pairs = [(a, b) for _, a, b in pair_points(feat, x, y, lag)]
    out: dict[str, Any] = {"x": x, "y": y, "lag_days": lag, "n": len(pairs)}
    if len(pairs) < MIN_PAIRS:
        out["status"] = f"insufficient data (< {MIN_PAIRS} paired days)"
        return out
    r = _pearson([p[0] for p in pairs], [p[1] for p in pairs])
    if r is None:
        return {**out, "status": "insufficient variation", "available": False,
                "reason": "one or both baseline-adjusted signals are constant"}
    boot_r = _block_bootstrap(pairs, _pearson, rng)
    slope = _slope([p[0] for p in pairs], [p[1] for p in pairs])
    boot_s = _block_bootstrap(pairs, _slope, rng)
    if not boot_r or not boot_s:
        return {**out, "status": "insufficient variation", "available": False,
                "reason": "not enough varying bootstrap samples to estimate uncertainty"}
    lo, hi = boot_r[int(0.025 * len(boot_r))], boot_r[int(0.975 * len(boot_r)) - 1]
    # two-sided bootstrap p: share of resamples on the other side of 0, doubled
    p = min(1.0, 2 * min(sum(v <= 0 for v in boot_r), sum(v >= 0 for v in boot_r)) / len(boot_r))
    out.update(status="ok", r=round(r, 3) if r is not None else None,
               r_ci95=[round(lo, 3), round(hi, 3)], p_boot=round(p, 4),
               slope=round(slope, 3) if slope is not None else None,
               slope_ci95=[round(boot_s[int(0.025 * len(boot_s))], 3),
                           round(boot_s[int(0.975 * len(boot_s)) - 1], 3)])
    return out


def bh_adjust(results: list[dict[str, Any]]) -> None:
    ok = [r for r in results if r.get("status") == "ok"]
    m = len(ok)
    ranked = sorted(ok, key=lambda r: r["p_boot"])
    prev = 1.0
    for i, r in reversed(list(enumerate(ranked, 1))):
        q = min(prev, r["p_boot"] * m / i)
        r["q_bh"] = round(q, 4)
        prev = q


def theil_sen(points: list[tuple[float, float]]) -> float | None:
    slopes = [(y2 - y1) / (x2 - x1) for i, (x1, y1) in enumerate(points)
              for x2, y2 in points[i + 1:] if x2 != x1]
    return statistics.median(slopes) if slopes else None


# --------------------------------------------------------------------------- level 2
UNITS = {"sleep_h": "h", "sleep_score": "pts", "hrv": "ms", "rhr": "bpm", "stress": "pts",
         "trimp": "TRIMP", "steps": "steps", "bedtime_h": "h", "last_training_end_h": "h",
         "garmin_readiness": "pts", "bb_max": "pts", "intensity_min": "min",
         "sleep_stress": "pts"}
LABELS = {"sleep_h": "sleep duration", "sleep_score": "sleep score", "hrv": "overnight HRV",
          "rhr": "resting HR", "stress": "daytime stress", "trimp": "training load",
          "steps": "steps", "bedtime_h": "bedtime (later = higher)",
          "last_training_end_h": "time training ended", "garmin_readiness":
          "Garmin readiness", "bb_max": "Body Battery high", "intensity_min":
          "intensity minutes", "sleep_stress": "stress during sleep"}

# (x, y, lag): x on day d vs y on day d+lag. Sleep rows are dated by wake-up day.
PAIRS = [
    ("sleep_h", "hrv", 0), ("sleep_h", "rhr", 0), ("sleep_h", "garmin_readiness", 0),
    ("bedtime_h", "sleep_h", 0), ("bedtime_h", "hrv", 0),
    ("trimp", "hrv", 1), ("trimp", "rhr", 1), ("trimp", "sleep_score", 1),
    ("last_training_end_h", "sleep_score", 1), ("last_training_end_h", "hrv", 1),
    ("stress", "sleep_score", 1), ("stress", "hrv", 1), ("steps", "sleep_score", 1),
    ("intensity_min", "sleep_h", 1),
]


def _describe(r: dict[str, Any]) -> str:
    x, y = LABELS.get(r["x"], r["x"]), LABELS.get(r["y"], r["y"])
    when = "the same night/day" if r["lag_days"] == 0 else "the next day"
    s = r["slope"]
    ux, uy = UNITS.get(r["x"], ""), UNITS.get(r["y"], "")
    per = {"h": 1, "bpm": 1, "ms": 1, "min": 30, "pts": 10, "steps": 1000, "TRIMP": 50}.get(ux, 1)
    return (f"For you, {per} {ux} more {x} than usual is associated with "
            f"{s * per:+.1f} {uy} {y} {when} (r = {r['r']}, 95% CI {r['r_ci95'][0]} to "
            f"{r['r_ci95'][1]}, n = {r['n']} days). Association, not proof of cause.")


def relationships(conn: sqlite3.Connection, end: str, days: int = 365) -> dict[str, Any]:
    start = (date.fromisoformat(end) - timedelta(days=days)).isoformat()
    feat = features(conn, start, end)
    rng = random.Random(SEED)
    res = [relationship(feat, x, y, lag, rng) for x, y, lag in PAIRS]
    bh_adjust(res)
    for r in res:
        if r.get("status") == "ok":
            r["notable"] = r.get("q_bh", 1) < 0.10 and abs(r["r"]) >= 0.15
            r["statement"] = _describe(r)
    notable = sorted((r for r in res if r.get("notable")), key=lambda r: -abs(r["r"]))
    return {"from": start, "to": end, "pairs_tested": len(res), "notable": notable,
            "all": res,
            "method": "baseline-adjusted (28-day trailing mean) values; Pearson r with 95% "
                      "block-bootstrap CI; Benjamini-Hochberg q < 0.10 and |r| >= 0.15 = notable"}


def weekday_patterns(conn: sqlite3.Connection, end: str, days: int = 365) -> dict[str, Any]:
    start = (date.fromisoformat(end) - timedelta(days=days)).isoformat()
    feat = features(conn, start, end)
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    out = {}
    for m in ("sleep_h", "hrv", "rhr", "steps", "trimp", "stress", "bedtime_h"):
        byd: dict[int, list[float]] = {}
        for d, v in feat.items():
            if m in v:
                byd.setdefault(date.fromisoformat(d).weekday(), []).append(v[m])
        if sum(len(x) for x in byd.values()) >= 28:
            out[m] = {names[k]: round(statistics.fmean(v), 2) for k, v in sorted(byd.items())}
    return {"from": start, "to": end, "means_by_weekday": out,
            "note": "Descriptive averages; small differences are noise."}


# --------------------------------------------------------------------------- level 3 / trends
TREND_METRICS = {"hrv": ("health_status", "hrv"), "rhr": ("daily", "resting_hr"),
                 "sleep_h": ("sleep", "sleep_s"), "vo2max": ("training", "vo2max_run"),
                 "ctl": ("fitness", "ctl"), "steps": ("daily", "steps")}


def trends(conn: sqlite3.Connection, end: str, days: int = 90) -> dict[str, Any]:
    """Robust trend per metric over `days`: Theil-Sen slope per 30 days, bootstrap CI."""
    from garmin_mcp.recovery import nightly_hrv

    start = (date.fromisoformat(end) - timedelta(days=days)).isoformat()
    rng = random.Random(SEED)
    out = {}
    for name, (table, col) in TREND_METRICS.items():
        try:
            rows = (sorted(nightly_hrv(conn, start, end).items()) if name == "hrv" else
                    conn.execute(f"SELECT day, {col} FROM {table} WHERE day BETWEEN ? AND ? AND "
                                 f"{col} IS NOT NULL ORDER BY day", (start, end)).fetchall())
        except sqlite3.OperationalError:
            continue
        if name == "sleep_h":
            rows = [(d, v / 3600) for d, v in rows if v >= 3 * 3600]
        if len(rows) < 14:
            continue
        d0 = date.fromisoformat(rows[0][0])
        pts = [((date.fromisoformat(d) - d0).days, v) for d, v in rows]
        if len(pts) > 120:  # keep Theil-Sen O(n^2) cheap
            step = len(pts) / 120
            pts = [pts[int(i * step)] for i in range(120)]
        slope = theil_sen(pts)
        boots = []
        for _ in range(200):
            sample = [rng.choice(pts) for _ in pts]
            s = theil_sen(sample)
            if s is not None:
                boots.append(s)
        boots.sort()
        lo, hi = boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots)) - 1]
        direction = "flat" if lo <= 0 <= hi else ("rising" if slope > 0 else "falling")
        out[name] = {"per_30_days": round(slope * 30, 2), "ci95": [round(lo * 30, 2),
                                                                     round(hi * 30, 2)],
                     "direction": direction, "points": len(rows),
                     "latest": round(rows[-1][1], 2)}
    return {"from": start, "to": end, "trends": out,
            "method": "Theil-Sen slope, 95% bootstrap CI; flat if CI includes 0"}


def load_flags(conn: sqlite3.Connection, end: str) -> list[dict[str, Any]]:
    """Load-change flags (never worded as injury risk)."""
    flags = []
    e = date.fromisoformat(end)
    try:
        wk = conn.execute("SELECT SUM(load) FROM fitness WHERE day > ? AND day <= ?",
                          ((e - timedelta(days=7)).isoformat(), end)).fetchone()[0] or 0
        prev = conn.execute("SELECT SUM(load)/4.0 FROM fitness WHERE day > ? AND day <= ?",
                            ((e - timedelta(days=35)).isoformat(),
                             (e - timedelta(days=7)).isoformat())).fetchone()[0] or 0
    except sqlite3.OperationalError:
        return flags
    if prev > 20 and wk > 1.3 * prev:
        flags.append({"flag": "load jump", "detail": f"7-day load {wk:.0f} vs 4-week weekly "
                      f"average {prev:.0f} (+{(wk / prev - 1) * 100:.0f}%)",
                      "suggest": "keep the next days easy if legs or knee feel it"})
    lr = conn.execute(
        "SELECT MAX(CASE WHEN substr(start_time_local,1,10) > ? THEN distance_m END), "
        "MAX(CASE WHEN substr(start_time_local,1,10) <= ? THEN distance_m END) FROM activities "
        "WHERE type LIKE '%run%' AND substr(start_time_local,1,10) > ? AND "
        "substr(start_time_local,1,10) <= ?",
        ((e - timedelta(days=7)).isoformat(), (e - timedelta(days=7)).isoformat(),
         (e - timedelta(days=37)).isoformat(), end)).fetchone()
    if lr and lr[0] and lr[1] and lr[0] > 1.3 * lr[1]:
        flags.append({"flag": "long-run jump", "detail": f"longest run this week "
                      f"{lr[0] / 1000:.1f} km vs {lr[1] / 1000:.1f} km in the prior 30 days",
                      "suggest": "extend long runs by ~10-15% at a time"})
    return flags


def tag_impact(conn: sqlite3.Connection, end: str, days: int = 365) -> dict[str, Any]:
    """Whoop-style behaviour impact: next-day HRV, sleep score and resting HR on tagged days vs
    untagged days (baseline-adjusted). Needs >= 5 tagged days per tag."""
    from garmin_mcp import athlete

    athlete.ensure(conn)
    start = (date.fromisoformat(end) - timedelta(days=days)).isoformat()
    tags: dict[str, set[str]] = {}
    for (text,) in conn.execute("SELECT text FROM athlete_notes WHERE kind='tag'"):
        try:
            raw_day, tag = text.split("|", 1)
            day = date.fromisoformat(raw_day.strip()).isoformat()
        except ValueError:
            continue
        if start <= day < end:
            tags.setdefault(tag.strip().lower(), set()).add(day)
    feat = features(conn, start, end)
    adj = {m: _adjust({d: v[m] for d, v in feat.items() if m in v})
           for m in ("hrv", "sleep_score", "rhr")}
    out = {}
    for tag, tdays in tags.items():
        row = {"tagged_days": len(tdays)}
        for m, series in adj.items():
            nxt = lambda d: (date.fromisoformat(d) + timedelta(days=1)).isoformat()
            on = [series[nxt(d)] for d in tdays if nxt(d) in series]
            off = [v for d, v in series.items()
                   if (date.fromisoformat(d) - timedelta(days=1)).isoformat() not in tdays]
            if len(on) >= 5 and len(off) >= 20:
                row[m] = {"next_day_diff": round(statistics.fmean(on) - statistics.fmean(off), 2),
                          "n_tagged": len(on)}
        out[tag] = row
    return {"tags": out, "how_to_tag": "add_tag(day, tag), e.g. alcohol, late meal, travel, "
                                       "illness, caffeine late",
            "note": "differences vs your baseline the following day; needs >= 5 tagged days"}


# --------------------------------------------------------------------------- level 1
def calendar(conn: sqlite3.Connection, end: str, days: int = 365) -> dict[str, Any]:
    start = (date.fromisoformat(end) - timedelta(days=days)).isoformat()
    feat = features(conn, start, end)
    keep = ("sleep_h", "hrv", "rhr", "trimp", "steps", "garmin_readiness", "stress")
    return {"from": start, "to": end,
            "days": {d: {k: round(v[k], 2) for k in keep if k in v} for d, v in sorted(feat.items())}}


def records(conn: sqlite3.Connection) -> dict[str, Any]:
    """Personal bests timeline from the pace curve (outdoor runs) and longest sessions."""
    from garmin_mcp.loads import RUN_TYPES, _pace, best_efforts

    timeline: dict[int, list[dict[str, Any]]] = {}
    best: dict[int, float] = {}
    for aid, start in conn.execute(
            f"SELECT activity_id, start_time_local FROM activities WHERE type IN "
            f"({','.join('?' * len(RUN_TYPES))}) AND fit_parsed=1 ORDER BY start_time_local",
            RUN_TYPES):
        for w, dist in best_efforts(conn, aid).items():
            if dist > best.get(w, 0) * 1.001:
                best[w] = dist
                timeline.setdefault(w, []).append({"date": start[:10], "distance_m": round(dist),
                                                   "pace": _pace(w / dist * 1000)})
    longest = {t: {"km": round(d / 1000, 2), "date": s[:10]} for t, d, s in conn.execute(
        "SELECT type, MAX(distance_m), start_time_local FROM activities WHERE distance_m > 0 "
        "GROUP BY type")}
    return {"pace_bests_timeline": {f"{w // 60} min": v for w, v in sorted(timeline.items())},
            "longest_by_type": longest}


def streaks(conn: sqlite3.Connection, end: str) -> dict[str, Any]:
    days = {r[0] for r in conn.execute("SELECT DISTINCT substr(start_time_local,1,10) FROM "
                                       "activities")}
    active = {r[0] for r in conn.execute("SELECT day FROM daily WHERE intensity_min_moderate + "
                                         "2*intensity_min_vigorous >= 30")}
    def run(s: set[str]) -> tuple[int, int]:
        cur = best = 0
        d = date.fromisoformat(end) - timedelta(days=800)
        current = 0
        while d <= date.fromisoformat(end):
            if d.isoformat() in s:
                cur += 1
                best = max(best, cur)
            else:
                cur = 0
            current = cur
            d += timedelta(days=1)
        return current, best
    a, b = run(days)
    c, dd = run(active)
    return {"activity_days": {"current": a, "best": b},
            "days_with_30plus_intensity_min": {"current": c, "best": dd}}


def personal_ranges(conn: sqlite3.Connection, end: str) -> dict[str, Any]:
    """Current-day measurements only; current Garmin bands or prior personal observations."""
    from garmin_mcp import recovery

    lo60 = (date.fromisoformat(end) - timedelta(days=60)).isoformat()
    cursor = conn.execute("SELECT * FROM health_status WHERE day=?", (end,))
    hs = cursor.fetchone()
    h = dict(zip((d[0] for d in cursor.description), hs, strict=True)) if hs else {}
    series = recovery.load_series(conn, end, 61)
    out = {}

    def valid(value):
        return isinstance(value, (int, float)) and math.isfinite(value) and value > 0

    def put(name, value, prior, bounds=None, minimum=21):
        if not valid(value):
            return
        source = "Garmin current-day baseline"
        if not bounds or not all(valid(v) for v in bounds) or bounds[0] > bounds[1]:
            prior = [v for v in prior if valid(v)]
            sd = statistics.stdev(prior) if len(prior) >= minimum else None
            bounds = [round(statistics.fmean(prior) - sd, 1),
                      round(statistics.fmean(prior) + sd, 1)] if sd else None
            source = "your prior 60-day mean +/- 1 SD" if bounds else "baseline calibrating"
        state = ("in range" if bounds[0] <= value <= bounds[1] else
                 "below" if value < bounds[0] else "above") if bounds else "calibrating"
        out[name] = {"value": value, "range": bounds, "state": state, "source": source,
                     "as_of": end, "range_available": bounds is not None}

    for name, key, field in (("hrv_ms", "hrv", "hrv"), ("resting_hr_bpm", "rhr", "rhr"),
                              ("respiration_brpm", "resp", "respiration")):
        prior = [v for d, v in series[key].items() if lo60 <= d < end]
        value = series[key].get(end)
        put(name, value if value is not None else h.get(field), prior,
            [h.get(field + "_low"), h.get(field + "_high")])
    for name, col in (("sleep_spo2_pct", "avg_spo2"), ("sleep_hr_bpm", "avg_hr")):
        row = conn.execute(f"SELECT {col} FROM sleep WHERE day=? AND sleep_s>=3*3600", (end,)).fetchone()
        prior = [r[0] for r in conn.execute(f"SELECT {col} FROM sleep WHERE day>=? AND day<? "
                                           "AND sleep_s>=3*3600 AND " + col + " IS NOT NULL",
                                           (lo60, end))]
        put(name, row[0] if row else None, prior, minimum=14)
    outside = sum(v["state"] in ("above", "below") for v in out.values())
    return {"day": end, "metrics": out, "outside_range": outside,
            "meaning": "Descriptive comparisons, not a diagnosis. Missing/stale measurements "
                       "are excluded; a range needs sufficient prior observations."}


def form_percent(conn: sqlite3.Connection, end: str) -> dict[str, Any] | None:
    """intervals.icu-style form as % of fitness = (CTL - ATL) / CTL * 100 (verified on their
    docs); -30 % is their green/red boundary (heuristic)."""
    try:
        row = conn.execute("SELECT ctl, atl FROM fitness WHERE day<=? ORDER BY day DESC LIMIT 1",
                           (end,)).fetchone()
    except sqlite3.OperationalError:
        return None
    if not row or not row[0]:
        return None
    if row[0] < 20:  # tiny fitness base: one session swings the % wildly
        return {"form_pct": None, "tsb": round(row[0] - row[1], 1), "ctl": row[0],
                "atl": row[1], "zone": "not meaningful at low fitness load (CTL < 20)",
                "note": "build regular training first; absolute TSB shown instead"}
    pct = (row[0] - row[1]) / row[0] * 100
    zone = ("fresh" if pct > 5 else "neutral" if pct > -10 else "optimal training"
            if pct > -30 else "high fatigue")
    return {"form_pct": round(pct, 1), "zone": zone, "ctl": row[0], "atl": row[1],
            "note": "zones: > +5 fresh, -10..+5 neutral, -30..-10 optimal training, < -30 high "
                    "fatigue (intervals.icu-style heuristic)"}


# --------------------------------------------------------------------------- insight feed
def insight_feed(conn: sqlite3.Connection, end: str | None = None, *,
                 include_relationships: bool = True,
                 signals: dict[str, Any] | None = None) -> dict[str, Any]:
    """Ranked insights across levels for the brief and dashboard."""
    from garmin_mcp import recovery, signal_context

    end = end or conn.execute("SELECT MAX(day) FROM daily").fetchone()[0]
    if signals is None:
        signals = signal_context.collect(conn, end, with_history=False)
    items: list[dict[str, Any]] = []
    r = recovery.readiness(conn, end)
    advice = recovery.suggestion(r)
    items.append({"level": 1, "kind": "today", "title": f"Readiness: {r['ours']['state']}",
                  "detail": f"{advice['suggest']}; {advice['why']}",
                  "priority": 1})
    hrv = r["hrv"]
    if hrv.get("state") in ("below normal", "above normal"):
        items.append({"level": 3, "kind": "hrv_guided",
                      "title": f"HRV-guided: 7-day HRV {hrv['state']}",
                      "detail": "Below normal: favour easy/low intensity today (HRV-guided "
                                "training, Plews/Kiviniemi style)." if hrv["state"] ==
                                "below normal" else "Above baseline alone does not establish readiness for hard training.",
                      "priority": 2})
    for key, signal in signals.items():
        state = signal["state"]
        if state in ("above", "below"):
            items.append({"level": 1, "kind": "signal_shift", "metric": key,
                          "title": f'{signal["label"]} is {state} your usual range',
                          "detail": signal_context.describe(key, state), "priority": 2})
    pr = personal_ranges(conn, end)
    if pr["outside_range"] >= 2:
        items.append({"level": 2, "kind": "vitals", "title": f"{pr['outside_range']} vitals "
                      "outside your personal range", "detail": ", ".join(
                          f"{k} {v['state']}" for k, v in pr["metrics"].items()
                          if v["state"] in ("above", "below")), "priority": 1})
    for f in load_flags(conn, end):
        items.append({"level": 3, "kind": "load", "title": f["flag"].capitalize(),
                      "detail": f"{f['detail']}. {f['suggest']}", "priority": 2})
    t = trends(conn, end, 90)["trends"]
    for name, v in t.items():
        if v["direction"] != "flat":
            good = {"hrv": "rising", "vo2max": "rising", "ctl": "rising", "steps": "rising",
                    "sleep_h": "rising", "rhr": "falling"}[name]
            items.append({"level": 1, "kind": "trend",
                          "title": f"{name} {v['direction']} over 90 days",
                          "detail": f"{v['per_30_days']:+} per 30 days (95% CI {v['ci95'][0]} "
                                    f"to {v['ci95'][1]})",
                          "metric": name, "direction": v["direction"],
                          "per_30_days": v["per_30_days"], "points": v["points"],
                          "tone": "positive" if v["direction"] == good else "watch",
                          "priority": 3})
    if include_relationships:
        rel = relationships(conn, end, 365)
        for n in rel["notable"][:4]:
            items.append({"level": 2, "kind": "relationship", "title":
                          f"{LABELS.get(n['x'], n['x'])} & {LABELS.get(n['y'], n['y'])}",
                          "detail": n["statement"], "priority": 4})
    items.sort(key=lambda i: i["priority"])
    return {"day": end, "insights": items,
            "personal_signals": {key: {**{k: v for k, v in value.items() if k != "days"},
                                       "interpretation": signal_context.describe(key, value["state"])}
                                 for key, value in signals.items()},
            "rules": "Level 1 = what happened, 2 = associations in your own data, 3 = what to "
                     "do; statistics in engine.py docstring"}
