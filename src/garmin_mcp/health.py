"""Phase 12 health analytics: sleep breakdown, heart-rate dip, activity status, pace of ageing,
shift detection, monthly report.

- Sleep breakdown: Garmin's own sub-score ratings and optimal ranges (duration, stress,
  awakenings, restlessness, REM/light/deep %) from the Personal API sleep payload; export
  nights use the export's component scores.
- Heart-rate dip (Bevel-style): (awake daytime mean HR - sleep mean HR) / awake mean * 100,
  awake mean from the all-day HR timeline outside the sleep window. A nocturnal dip of
  >= 10 % is the usual "dipper" threshold from cardiovascular research (heuristic here).
- Activity status: days tagged sick / injured / break are excluded from baselines and pause
  training advice (Bevel's "activity status").
- Pace of ageing (Whoop-style scale): Theil-Sen slope of Garmin's fitness age in years per
  calendar year over 180 days; 1.0 = calendar pace, < 1 slower, < 0 getting younger.
- Shift detection: the single most likely mean shift in a series (two-segment split with the
  largest standardised difference; reported only if both sides have >= 14 days and the shift is
  >= 1 within-segment SD). A simple, transparent changepoint check, not PELT.
"""

from __future__ import annotations

import json
import sqlite3
import statistics
from datetime import date, datetime, timedelta
from typing import Any

STATUS_TAGS = {"sick", "injured", "break", "illness"}


# --------------------------------------------------------------------------- activity status
def status_days(conn: sqlite3.Connection) -> dict[str, str]:
    from garmin_mcp import athlete

    athlete.ensure(conn)
    out = {}
    for (text,) in conn.execute("SELECT text FROM athlete_notes WHERE kind='tag'"):
        day, _, tag = text.partition("|")
        if tag.strip() in STATUS_TAGS:
            out[day.strip()] = tag.strip()
    return out


# --------------------------------------------------------------------------- sleep
def sleep_breakdown(conn: sqlite3.Connection, day: str) -> dict[str, Any]:
    row = conn.execute("SELECT payload FROM raw_daily WHERE dataset IN ('pa_sleep','sleep') AND "
                       "day=? AND payload!='null' ORDER BY dataset LIMIT 1", (day,)).fetchone()
    out: dict[str, Any] = {"day": day}
    if row:
        p = json.loads(row[0])
        p = p.get("dailySleepDTO", p)
        sc = p.get("sleepScores") or {}
        parts = {}
        for key, label in (("totalDuration", "Duration"), ("deepPercentage", "Deep sleep"),
                           ("remPercentage", "REM sleep"), ("lightPercentage", "Light sleep"),
                           ("awakeCount", "Awakenings"), ("restlessness", "Restlessness"),
                           ("stress", "Stress during sleep")):
            c = sc.get(key)
            if isinstance(c, dict):
                parts[label] = {"rating": (c.get("qualifierKey") or "").title() or None,
                                "value": c.get("value"),
                                "optimal": [c.get("optimalStart"), c.get("optimalEnd")]}
        out.update(source="Garmin", overall=(sc.get("overall") or {}).get("value"),
                   rating=((sc.get("overall") or {}).get("qualifierKey") or "").title() or None,
                   parts=parts, feedback=p.get("sleepScoreFeedback"),
                   avg_sleep_hr=p.get("avgHeartRate"))
    else:
        row = conn.execute("SELECT payload FROM raw_daily WHERE dataset='ex_sleep' AND day=?",
                           (day,)).fetchone()
        if row:
            p = json.loads(row[0])
            p = p if isinstance(p, dict) else p[0]
            sc = p.get("sleepScores") or {}
            out.update(source="Garmin export", overall=sc.get("overallScore"),
                       parts={k.replace("Score", ""): {"score": v} for k, v in sc.items()
                              if k.endswith("Score") and k != "overallScore"},
                       feedback=sc.get("feedback"))
    dip = heart_rate_dip(conn, day)
    if dip:
        out["heart_rate_dip"] = dip
    return out


def heart_rate_dip(conn: sqlite3.Connection, day: str) -> dict[str, Any] | None:
    sl = conn.execute("SELECT sleep_start, sleep_end, avg_hr FROM sleep WHERE day=? AND "
                      "sleep_s >= 3*3600", (day,)).fetchone()
    if not sl or not sl[2]:
        return None
    # awake HR from the previous day's all-day timeline (the day before this night)
    prev = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    row = conn.execute("SELECT payload FROM raw_daily WHERE dataset IN ('pa_heart_rate',"
                       "'heart_rate') AND day=? AND payload!='null' LIMIT 1", (prev,)).fetchone()
    if not row:
        return None
    values = (json.loads(row[0]) or {}).get("heartRateValues") or []
    start = datetime.fromisoformat(sl[0]).timestamp() * 1000 if sl[0] else None
    awake = [hr for ts, hr in values if hr and (start is None or ts < start - 30 * 60 * 1000)]
    if len(awake) < 60:
        return None
    day_mean = statistics.fmean(awake)
    dip = (day_mean - sl[2]) / day_mean * 100
    return {"awake_mean_hr": round(day_mean, 1), "sleep_mean_hr": sl[2],
            "dip_pct": round(dip, 1),
            "label": "healthy dip" if dip >= 10 else "small dip",
            "meaning": "A heart-rate drop of >= 10 % from day to night usually means good "
                       "overnight recovery; small dips often follow late meals, alcohol, "
                       "late training or illness."}


# --------------------------------------------------------------------------- trends
def pace_of_ageing(conn: sqlite3.Connection, end: str, days: int = 180) -> dict[str, Any]:
    from garmin_mcp.engine import theil_sen

    lo = (date.fromisoformat(end) - timedelta(days=days)).isoformat()
    rows = conn.execute("SELECT day, fitness_age, chronological_age FROM fitness_age WHERE day "
                        "BETWEEN ? AND ? AND fitness_age IS NOT NULL ORDER BY day",
                        (lo, end)).fetchall()
    if len(rows) < 30:
        return {"available": False, "reason": f"needs >= 30 days of fitness age, have "
                                              f"{len(rows)}"}
    d0 = date.fromisoformat(rows[0][0])
    span = (date.fromisoformat(rows[-1][0]) - d0).days
    if span < 90:
        return {"available": False, "fitness_age_now": round(rows[-1][1], 1),
                "reason": f"fitness-age history spans {span} days; a yearly pace needs >= 90 "
                          "days or day-to-day wobble gets multiplied into a false trend"}
    pts = [((date.fromisoformat(d) - d0).days, v) for d, v, _ in rows]
    if len(pts) > 120:
        step = len(pts) / 120
        pts = [pts[int(i * step)] for i in range(120)]
    slope = theil_sen(pts) or 0.0
    per_year = slope * 365
    return {"available": True, "fitness_age_now": round(rows[-1][1], 1),
            "chronological_age": rows[-1][2],
            "pace_of_ageing": round(per_year, 2),
            "meaning": "Pace of ageing = years of fitness age gained per calendar year (trend). "
                       "1.0 = ageing with the calendar; below 1.0 = slower; 0 = not ageing; "
                       "negative = getting fitter. Garmin fitness age moves with resting HR, "
                       "vigorous minutes and body fat, so short windows are noisy.",
            "window_days": days}


def detect_shift(series: list[tuple[str, float]], min_seg: int = 14) -> dict[str, Any] | None:
    if len(series) < 2 * min_seg:
        return None
    vals = [v for _, v in series]
    best = None
    for k in range(min_seg, len(vals) - min_seg + 1):
        a, b = vals[:k], vals[k:]
        sd = statistics.pstdev(a + b) or 1
        pooled = (statistics.pstdev(a) + statistics.pstdev(b)) / 2 or sd
        diff = statistics.fmean(b) - statistics.fmean(a)
        z = abs(diff) / pooled
        if best is None or z > best[0]:
            best = (z, k, diff)
    if not best or best[0] < 1:
        return None
    z, k, diff = best
    return {"date": series[k][0], "change": round(diff, 2), "size_sd": round(z, 2),
            "before_mean": round(statistics.fmean(vals[:k]), 2),
            "after_mean": round(statistics.fmean(vals[k:]), 2)}


def shifts(conn: sqlite3.Connection, end: str, days: int = 180) -> dict[str, Any]:
    lo = (date.fromisoformat(end) - timedelta(days=days)).isoformat()
    out = {}
    for name, sql in (("resting_hr", ("SELECT day, resting_hr FROM daily WHERE day BETWEEN ? AND"
                                      " ? AND resting_hr IS NOT NULL ORDER BY day")),
                      ("hrv", ("SELECT day, hrv FROM health_status WHERE day BETWEEN ? AND ? AND"
                              " hrv IS NOT NULL ORDER BY day")),
                      ("sleep_h", ("SELECT day, sleep_s/3600.0 FROM sleep WHERE day BETWEEN ? "
                                  "AND ? AND sleep_s >= 3*3600 ORDER BY day"))):
        found = detect_shift(conn.execute(sql, (lo, end)).fetchall())
        if found:
            out[name] = found
    return {"window_days": days, "shifts": out,
            "method": "largest two-segment mean shift; reported if >= 1 SD and >= 14 days each "
                      "side"}


# --------------------------------------------------------------------------- monthly report
def monthly_report(conn: sqlite3.Connection, month: str) -> dict[str, Any]:
    """month = 'YYYY-MM'. Totals and averages, compared with the previous month."""

    def stats(m: str) -> dict[str, Any]:
        a = conn.execute(
            "SELECT COUNT(*), SUM(duration_s)/3600.0, SUM(CASE WHEN type LIKE '%run%' THEN "
            "distance_m END)/1000.0 FROM activities WHERE substr(start_time_local,1,7)=?",
            (m,)).fetchone()
        s = conn.execute("SELECT AVG(sleep_s)/3600.0, COUNT(*) FROM sleep WHERE "
                         "substr(day,1,7)=? AND sleep_s >= 3*3600", (m,)).fetchone()
        d = conn.execute("SELECT AVG(resting_hr), AVG(steps) FROM daily WHERE substr(day,1,7)=?",
                         (m,)).fetchone()
        h = conn.execute("SELECT AVG(hrv) FROM health_status WHERE substr(day,1,7)=?",
                         (m,)).fetchone()

        def r(v: Any, nd: int = 1) -> Any:
            return round(v, nd) if isinstance(v, (int, float)) else v

        return {"sessions": a[0], "hours": r(a[1]), "run_km": r(a[2]),
                "avg_sleep_h": r(s[0], 2), "nights": s[1], "avg_resting_hr": r(d[0]),
                "avg_steps": r(d[1], 0), "avg_hrv": r(h[0])}

    y, m = (int(x) for x in month.split("-"))
    prev = f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"
    cur, before = stats(month), stats(prev)
    change = {k: (round(cur[k] - before[k], 2) if isinstance(cur[k], (int, float)) and
                  isinstance(before[k], (int, float)) else None) for k in cur}
    return {"month": month, "this_month": cur, "previous_month": before, "change": change}


# --------------------------------------------------------------------------- marathon shape
def marathon_shape(conn: sqlite3.Connection, end: str) -> dict[str, Any]:
    """Runalyze Marathon shape (from Runalyze source MarathonShape.php / BasicEndurance.php).

    V = effective VO2max (floor 25). Weekly target = V^1.135 km; long-run target = ln(V/4)*12 km.
    Long runs (> 13 km, last 70 days) score (2 - 2/70*days_ago) * ((d-13)/(target-13))^2.
    Weekly window: 182 days (or since first run, min 70).
    Shape = 0.67 * weekly% + 0.33 * long-run%. Race needs distance_km^1.23 % of shape
    (5K 7 %, 10K 17 %, half 42 %, marathon 100 %).
    """
    import math

    from garmin_mcp import loads

    hrmax = loads.thresholds(conn, end).get("hr_max") or 190
    v = loads.effective_vo2max(conn, end, hrmax).get("value") or garmin_vo2(conn)
    if not v:
        return {"available": False, "reason": "no VO2max estimate yet"}
    v = max(25.0, v)
    weekly_target = v ** 1.135
    long_target = math.log(v / 4) * 12
    endd = date.fromisoformat(end)
    first = conn.execute("SELECT MIN(substr(start_time_local,1,10)) FROM activities WHERE type "
                         "LIKE '%run%'").fetchone()[0]
    window = 182
    if first:
        window = max(70, min(182, (endd - date.fromisoformat(first)).days + 1))
    lo = (endd - timedelta(days=window - 1)).isoformat()
    runs = conn.execute("SELECT substr(start_time_local,1,10), distance_m FROM activities WHERE "
                        "type LIKE '%run%' AND substr(start_time_local,1,10) BETWEEN ? AND ?",
                        (lo, end)).fetchall()
    km = sum((d or 0) for _, d in runs) / 1000
    weekly_pct = km * 7 / window / weekly_target
    pts = 0.0
    for day, dist in runs:
        ago = (endd - date.fromisoformat(day)).days
        dk = (dist or 0) / 1000
        if ago < 70 and dk > 13:
            pts += (2 - 2 / 70 * ago) * ((dk - 13) / (long_target - 13)) ** 2
    long_pct = pts * 7 / 70
    shape = round(100 * (0.67 * weekly_pct + 0.33 * long_pct))
    need = {k: round(d ** 1.23, 1) for k, d in (("5K", 5), ("10K", 10), ("Half", 21.0975),
                                                  ("Marathon", 42.195))}
    return {"available": True, "marathon_shape_pct": max(0, min(100, shape)),
            "vo2max_used": round(v, 1),
            "weekly_km_avg": round(km * 7 / window, 1), "weekly_km_target": round(weekly_target, 1),
            "long_run_target_km": round(long_target, 1), "long_run_points_pct": round(
                100 * long_pct), "needed_for": need,
            "ready_for": [k for k, n in need.items() if shape >= n],
            "meaning": "How ready your endurance base is for a marathon at your current fitness "
                       "(100 % = fully prepared). Built from weekly km (2/3) and long runs over "
                       "13 km in the last 10 weeks (1/3)."}


def garmin_vo2(conn: sqlite3.Connection) -> float | None:
    row = conn.execute("SELECT vo2max FROM activities WHERE vo2max IS NOT NULL ORDER BY "
                       "start_time_local DESC LIMIT 1").fetchone()
    return row[0] if row else None
