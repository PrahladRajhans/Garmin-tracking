"""Phase 4: thresholds, training load, fitness/fatigue/form, intensity, performance.

Every formula is stated here and in METRICS.md, and pinned by unit tests. Garmin's own values
are kept beside ours (never blended). Choices that are ours, not a published standard, are
labelled "design choice".

Formulas
- Banister TRIMP (per sample): dt_min * x * a * e^(b*x), x = (HR - HRrest)/(HRmax - HRrest),
  men a=0.64 b=1.92, women a=0.86 b=1.67 (Banister 1991; Morton et al. 1990).
- CTL/ATL: exponentially weighted, lambda = 1 - e^(-1/N), N = 42 / 7 days. TrainingPeaks uses
  lambda = 1/N (about 7% faster for ATL); design choice: exponential form.
  TSB (form) = yesterday's CTL - yesterday's ATL (TrainingPeaks convention).
- Ramp rate: CTL today - CTL 7 days ago.
- Foster monotony = mean / SD of daily load over 7 days; strain = weekly load * monotony.
- rTSS: hours * IF^2 * 100, IF = normalised graded speed / threshold speed (speeds in m/s).
  Graded speed uses the Minetti 2002 energy-cost polynomial (TrainingPeaks' own grade model
  is unpublished): C(i) = 155.4i^5 - 30.4i^4 - 43.3i^3 + 46.3i^2 + 19.5i + 3.6 J/kg/m.
- Seiler 3 zones from HR (design choice anchored on LTHR): Z1 < 0.90*LTHR, Z2 0.90-1.00*LTHR,
  Z3 >= LTHR. Treff polarisation index PI = log10(Z1/Z2 * Z3 * 100) (fractions; only when
  Z1 > Z3 > Z2; Z2=0 -> 0.01); PI > 2 = polarised.
- VDOT (Daniels & Gilbert 1979): VO2 = -4.60 + 0.182258 v + 0.000104 v^2 (v m/min);
  %max = 0.8 + 0.1894393 e^(-0.012778 t) + 0.2989558 e^(-0.1932605 t) (t min); VDOT = VO2/%max.
- Riegel: T2 = T1 * (D2/D1)^1.06 (fitted on trained runners; recreational often 1.07-1.10).
- Critical speed (2-parameter): distance = CS * t + D', fitted on best efforts 3-20 min.
"""

from __future__ import annotations

import itertools
import math
import sqlite3
import statistics
from datetime import date, datetime, timedelta
from typing import Any

BANISTER = {"male": (0.64, 1.92), "female": (0.86, 1.67)}
CTL_DAYS, ATL_DAYS = 42, 7
CURVE_WINDOWS_S = [60, 120, 180, 300, 600, 720, 1200, 1800, 2700, 3600, 5400, 7200]
RACES_M = {"5k": 5000, "10k": 10000, "half": 21097.5, "marathon": 42195}
RUN_TYPES = ("running", "trail_running", "track_running")  # treadmill excluded: wrist speed


# --------------------------------------------------------------------------- formulas
def banister_trimp(hr: float, dt_min: float, rest: float, hrmax: float, sex: str) -> float:
    if hrmax <= rest or hr is None:
        return 0.0
    x = min(max((hr - rest) / (hrmax - rest), 0.0), 1.0)
    a, b = BANISTER.get(sex, BANISTER["male"])
    return dt_min * x * a * math.exp(b * x)


def minetti_cost(grade: float) -> float:
    i = max(-0.45, min(0.45, grade))
    return 155.4 * i**5 - 30.4 * i**4 - 43.3 * i**3 + 46.3 * i**2 + 19.5 * i + 3.6


def vdot(distance_m: float, time_s: float) -> float | None:
    if distance_m <= 0 or time_s < 240:
        return None
    t = time_s / 60
    v = distance_m / t
    vo2 = -4.60 + 0.182258 * v + 0.000104 * v * v
    pct = 0.8 + 0.1894393 * math.exp(-0.012778 * t) + 0.2989558 * math.exp(-0.1932605 * t)
    return vo2 / pct


def time_for_vdot(distance_m: float, target: float) -> float:
    lo, hi = 60.0, 60.0 * 60 * 12
    for _ in range(80):  # bisection on time; vdot decreases as time increases
        mid = (lo + hi) / 2
        v = vdot(distance_m, mid)
        if v is None or v > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def riegel(t1: float, d1: float, d2: float, exponent: float = 1.06) -> float:
    return t1 * (d2 / d1) ** exponent


def ewma(prev: float, value: float, days: int) -> float:
    lam = 1 - math.exp(-1 / days)
    return prev + lam * (value - prev)


def polarization_index(z1: float, z2: float, z3: float) -> float | None:
    total = z1 + z2 + z3
    if total <= 0:
        return None
    f1, f2, f3 = z1 / total, z2 / total, z3 / total
    if not (f1 > f3 > f2 or (f2 == 0 and f1 > f3 > 0)):
        return None
    f2 = f2 or 0.01
    return math.log10(f1 / f2 * f3 * 100)


# --------------------------------------------------------------------------- data access
def _ts(value: str) -> float:
    return datetime.fromisoformat(value).timestamp()


def _records(conn: sqlite3.Connection, activity_id: int) -> list[tuple]:
    return conn.execute(
        "SELECT ts, heart_rate, speed, altitude, distance FROM fit_records WHERE activity_id=? "
        "ORDER BY ts", (activity_id,)).fetchall()


def _age(conn: sqlite3.Connection) -> float | None:
    try:
        row = conn.execute("SELECT chronological_age FROM fitness_age WHERE chronological_age IS "
                           "NOT NULL ORDER BY day DESC LIMIT 1").fetchone()
    except sqlite3.OperationalError:
        return None
    return row[0] if row else None


def _sex(conn: sqlite3.Connection) -> tuple[str, str]:
    row = conn.execute("SELECT gender FROM fit_profile WHERE gender IN ('male','female') "
                       "ORDER BY activity_id DESC LIMIT 1").fetchone()
    return (row[0], "watch profile") if row else ("male", "ASSUMED (no profile found)")


# --------------------------------------------------------------------------- thresholds
def best_rolling_hr(records: list[tuple], window_s: int) -> float | None:
    pts = [(_ts(r[0]), r[1]) for r in records if r[1]]
    if len(pts) < 2 or pts[-1][0] - pts[0][0] < window_s:
        return None
    best, j, acc, w = None, 0, 0.0, 0.0
    # time-weighted average over a sliding window
    for i in range(1, len(pts)):
        dt = min(pts[i][0] - pts[i - 1][0], 10)
        acc += pts[i][1] * dt
        w += dt
        while pts[i][0] - pts[j][0] > window_s and j < i - 1:
            dtj = min(pts[j + 1][0] - pts[j][0], 10)
            acc -= pts[j + 1][1] * dtj
            w -= dtj
            j += 1
        if pts[i][0] - pts[0][0] >= window_s and w > 0:
            avg = acc / w
            best = avg if best is None or avg > best else best
    return best


def thresholds(conn: sqlite3.Connection, asof: str | None = None) -> dict[str, Any]:
    """Effective thresholds as of a date, with Garmin's values beside our estimates."""
    asof = asof or date.today().isoformat()
    lo = (date.fromisoformat(asof) - timedelta(days=365)).isoformat()
    sex, sex_src = _sex(conn)

    observed_max = conn.execute(
        "SELECT MAX(max_hr) FROM activities WHERE substr(start_time_local,1,10) BETWEEN ? AND ?",
        (lo, asof)).fetchone()[0]
    garmin_max = conn.execute(
        "SELECT z.max_hr FROM fit_zones z JOIN activities a USING(activity_id) "
        "WHERE substr(a.start_time_local,1,10) <= ? ORDER BY a.start_time_local DESC LIMIT 1",
        (asof,)).fetchone()
    garmin_lthr = conn.execute(
        "SELECT z.threshold_hr FROM fit_zones z JOIN activities a USING(activity_id) "
        "WHERE z.threshold_hr > 0 AND substr(a.start_time_local,1,10) <= ? "
        "ORDER BY a.start_time_local DESC LIMIT 1", (asof,)).fetchone()
    try:
        rest_vals = [r[0] for r in conn.execute(
            "SELECT resting_hr FROM daily WHERE day BETWEEN ? AND ? AND resting_hr IS NOT NULL",
            ((date.fromisoformat(asof) - timedelta(days=60)).isoformat(), asof))]
    except sqlite3.OperationalError:  # tidy tables not built yet (fresh database)
        rest_vals = []
    rest = statistics.median(rest_vals) if rest_vals else None

    best20 = None
    for (aid,) in conn.execute(
        "SELECT activity_id FROM activities WHERE type IN ({}) AND duration_s >= 1500 AND "
        "substr(start_time_local,1,10) BETWEEN ? AND ?".format(",".join("?" * len(RUN_TYPES))),
        (*RUN_TYPES, lo, asof)):
        v = best_rolling_hr(_records(conn, aid), 1200)
        if v and (best20 is None or v > best20):
            best20 = v

    # Robust observed peak: the highest value reached in at least two activities (within 3 bpm),
    # so a single optical spike cannot set HRmax. Then never below the Tanaka age estimate
    # (208 - 0.7 * age; Tanaka et al. 2001, SD ~10 bpm), because training runs are submaximal.
    peaks = sorted((r[0] for r in conn.execute(
        "SELECT max_hr FROM activities WHERE max_hr IS NOT NULL AND "
        "substr(start_time_local,1,10) <= ?", (asof,))), reverse=True)
    robust = next((p for i, p in enumerate(peaks) if any(abs(p - q) <= 3 for q in peaks[i + 1:])),
                  None)
    age = _age(conn)
    tanaka = round(208 - 0.7 * age) if age else None
    candidates = [v for v in (robust, tanaka) if v]
    hrmax = max(candidates) if candidates else observed_max
    lthr = round(best20) if best20 else (garmin_lthr[0] if garmin_lthr else None)
    notes = []
    from garmin_mcp import athlete

    overrides = {}
    if (v := athlete.get(conn, "hr_max_override")) is not None:
        hrmax, overrides["hr_max"] = float(v), "your setting"
    if (v := athlete.get(conn, "lthr_override")) is not None:
        lthr, overrides["lthr"] = float(v), "your setting"
    tp = athlete.get(conn, "threshold_pace_override")
    if observed_max and robust and observed_max - robust >= 8:
        notes.append(f"Single-activity peak of {observed_max:.0f} bpm was never repeated (next "
                     f"repeatable peak {robust:.0f}); treated as a probable optical spike.")
    if garmin_max and observed_max and garmin_max[0] - observed_max >= 8 and \
            "hr_max" not in overrides:
        notes.append(f"Garmin's max-HR setting ({garmin_max[0]:.0f}) is {garmin_max[0] - observed_max:.0f}"
                     f" bpm above the highest HR recorded in the last year ({observed_max:.0f}); "
                     f"using {hrmax:.0f} (repeatable peak vs age estimate). Override if you have "
                     "tested a higher max.")
    if garmin_lthr and best20 and abs(garmin_lthr[0] - best20) >= 5:
        notes.append(f"Garmin's lactate-threshold HR ({garmin_lthr[0]:.0f}) differs from your best "
                     f"sustained 20-min HR on a run ({best20:.0f}); using the 20-min value "
                     "(Friel-style estimate; lower if no run was a hard 20-30 min effort).")
    return {
        "asof": asof, "sex": sex, "sex_source": sex_src,
        "hr_max": hrmax, "hr_rest": round(rest, 1) if rest else None, "lthr": lthr,
        "garmin": {"hr_max_setting": garmin_max[0] if garmin_max else None,
                   "lthr": garmin_lthr[0] if garmin_lthr else None},
        "observed_hr_max": observed_max, "repeatable_peak": robust, "tanaka_estimate": tanaka,
        "age": age, "overrides": overrides,
        "threshold_speed_override": athlete.pace_to_speed(tp) if tp else None,
        "sources": {"hr_max": "max(repeatable activity peak, Tanaka 208-0.7*age); your override "
                              "wins",
                    "hr_rest": "median daily resting HR, last 60 days",
                    "lthr": "best 20-min rolling HR on a run >= 25 min, last 365 days"},
        "notes": notes,
    }


# --------------------------------------------------------------------------- per activity
def activity_load(conn: sqlite3.Connection, activity: dict[str, Any], th: dict[str, Any],
                  threshold_speed: float | None) -> dict[str, Any]:
    recs = _records(conn, activity["activity_id"])
    rest, hrmax, lthr, sex = th["hr_rest"], th["hr_max"], th["lthr"], th["sex"]
    trimp, zones, graded_dist, moving_s = 0.0, [0.0, 0.0, 0.0], 0.0, 0.0
    stream = False
    if recs and rest and hrmax:
        prev = None
        for r in recs:
            t = _ts(r[0])
            if prev is not None:
                dt = min(t - prev[0], 10.0)  # cap gaps (pauses) at 10 s
                hr = r[1]
                if hr:
                    stream = True
                    trimp += banister_trimp(hr, dt / 60, rest, hrmax, sex)
                    if lthr:
                        zones[0 if hr < 0.9 * lthr else 1 if hr < lthr else 2] += dt
                if r[2] and r[2] > 0.5 and r[4] is not None and prev[4] is not None:
                    dd = r[4] - prev[4]
                    da = (r[3] - prev[3]) if r[3] is not None and prev[3] is not None else 0
                    grade = da / dd if dd > 2 else 0.0
                    graded_dist += r[2] * dt * minetti_cost(grade) / minetti_cost(0)
                    moving_s += dt
            prev = (t, r[1], r[2], r[3], r[4])
    if not stream and activity.get("avg_hr") and activity.get("duration_s") and rest and hrmax:
        trimp = banister_trimp(activity["avg_hr"], activity["duration_s"] / 60, rest, hrmax, sex)
    rtss = None
    if threshold_speed and moving_s > 300 and activity["type"] in RUN_TYPES:  # only with a maximal CS
        ngs = graded_dist / moving_s
        rtss = moving_s / 3600 * (ngs / threshold_speed) ** 2 * 100
    return {"trimp": round(trimp, 1), "trimp_from": "hr stream" if stream else "average hr",
            "rtss": round(rtss, 1) if rtss else None,
            "zone_s": [round(z) for z in zones]}


# --------------------------------------------------------------------------- performance
def best_efforts(conn: sqlite3.Connection, activity_id: int) -> dict[int, float]:
    """Best distance covered in each window (s) from the FIT distance stream."""
    pts = [(_ts(r[0]), r[4]) for r in _records(conn, activity_id) if r[4] is not None]
    out: dict[int, float] = {}
    if len(pts) < 2:
        return out
    for w in CURVE_WINDOWS_S:
        if pts[-1][0] - pts[0][0] < w:
            continue
        best, j = 0.0, 0
        for i in range(len(pts)):
            while j < len(pts) and pts[j][0] - pts[i][0] < w:
                j += 1
            if j >= len(pts):
                break
            span = pts[j][0] - pts[i][0]
            best = max(best, (pts[j][1] - pts[i][1]) * w / span)
        if best > 0:
            out[w] = best
    return out


def pace_curve(conn: sqlite3.Connection, end: str, days: int = 180) -> dict[str, Any]:
    lo = (date.fromisoformat(end) - timedelta(days=days - 1)).isoformat()
    best: dict[int, tuple[float, int, str]] = {}
    for aid, start in conn.execute(
        "SELECT activity_id, start_time_local FROM activities WHERE type IN ({}) AND "
        "fit_parsed=1 AND substr(start_time_local,1,10) BETWEEN ? AND ?".format(",".join("?" * len(RUN_TYPES))), (*RUN_TYPES, lo, end)):
        for w, dist in best_efforts(conn, aid).items():
            if w not in best or dist > best[w][0]:
                best[w] = (dist, aid, start[:10])
    curve = [{"window_s": w, "distance_m": round(d, 1), "pace_min_km": _pace(w / d * 1000),
              "activity_id": a, "date": dte} for w, (d, a, dte) in sorted(best.items())]
    return {"from": lo, "to": end, "curve": curve}


def _pace(sec_per_km: float) -> str:
    s = round(sec_per_km)
    return f"{s // 60}:{s % 60:02d}"


def critical_speed(curve: list[dict[str, Any]]) -> dict[str, Any] | None:
    pts = [(c["window_s"], c["distance_m"]) for c in curve if 180 <= c["window_s"] <= 1200]
    if len(pts) < 3:
        return None
    n = len(pts)
    mt = sum(t for t, _ in pts) / n
    md = sum(d for _, d in pts) / n
    sxx = sum((t - mt) ** 2 for t, _ in pts)
    cs = sum((t - mt) * (d - md) for t, d in pts) / sxx
    dprime = md - cs * mt
    ss_res = sum((d - (cs * t + dprime)) ** 2 for t, d in pts)
    ss_tot = sum((d - md) ** 2 for _, d in pts) or 1
    r2 = 1 - ss_res / ss_tot
    return {"cs_m_s": round(cs, 3), "cs_pace_min_km": _pace(1000 / cs) if cs > 0 else None,
            "d_prime_m": round(dprime, 1), "r2": round(r2, 4), "points": n,
            "maximal": 50 <= dprime <= 400 and r2 > 0.95,
            "caution": None if (50 <= dprime <= 400 and r2 > 0.95) else
            "best efforts look submaximal (D' outside 50-400 m): CS here reflects your usual "
            "training pace, not your threshold. Run a hard 3-5 min and 12-20 min effort to "
            "calibrate."}


def swain_pct_vo2max(pct_hrmax: float) -> float:
    """Swain et al. 1994: %HRmax = 0.6463 * %VO2max + 37.182 (percent units)."""
    return (pct_hrmax * 100 - 37.182) / 0.6463 / 100


def effective_vo2max(conn: sqlite3.Connection, end: str, hrmax: float,
                     days: int = 90) -> dict[str, Any]:
    """Runalyze-style effective VO2max: Daniels VO2 at the run's speed divided by the fraction
    of VO2max implied by its average %HRmax (Swain 1994). Works for submaximal runs; sensitive
    to HRmax and wrist-HR quality. Median of runs >= 20 min at >= 70% HRmax."""
    lo = (date.fromisoformat(end) - timedelta(days=days - 1)).isoformat()
    vals = []
    for aid, dist, dur, hr, start in conn.execute(
        "SELECT activity_id, distance_m, duration_s, avg_hr, start_time_local FROM activities "
        "WHERE type IN ({}) AND duration_s >= 1200 AND distance_m > 0 AND avg_hr > 0 AND "
        "substr(start_time_local,1,10) BETWEEN ? AND ?".format(",".join("?" * len(RUN_TYPES))),
        (*RUN_TYPES, lo, end)):
        pct_hr = hr / hrmax
        if pct_hr < 0.70:
            continue
        v = dist / (dur / 60)
        vo2 = -4.60 + 0.182258 * v + 0.000104 * v * v
        vals.append((round(vo2 / swain_pct_vo2max(pct_hr), 1), start[:10], aid))
    if not vals:
        return {"value": None, "runs": 0}
    med = statistics.median(v for v, _, _ in vals)
    return {"value": round(med, 1), "runs": len(vals),
            "per_run": sorted(vals, key=lambda x: x[1])[-10:],
            "method": "median over runs: Daniels VO2(speed) / Swain %VO2max(avg %HRmax)"}


def race_predictions(conn: sqlite3.Connection, end: str, days: int = 90) -> dict[str, Any]:
    curve = pace_curve(conn, end, days)["curve"]
    efforts = [(c["window_s"], c["distance_m"]) for c in curve if 300 <= c["window_s"] <= 3600]
    vd = [(vdot(d, t), t, d) for t, d in efforts]
    vd = [x for x in vd if x[0]]
    out: dict[str, Any] = {"window_days": days, "based_on": None, "vdot": None, "predictions": {}}
    if vd:
        best_v, t1, d1 = max(vd)
        out["vdot"] = round(best_v, 1)
        out["based_on"] = {"duration_s": t1, "distance_m": round(d1), "pace": _pace(t1 / d1 * 1000)}
        cs = critical_speed(pace_curve(conn, end, days)["curve"])
        th = thresholds(conn, end)
        eff = effective_vo2max(conn, end, th["hr_max"], days) if th["hr_max"] else {"value": None}
        out["effective_vo2max"] = eff
        for name, dist in RACES_M.items():
            row = {}
            if eff.get("value"):
                row["effective_vo2max"] = _hms(time_for_vdot(dist, eff["value"]))
            row["best_effort_vdot"] = _hms(time_for_vdot(dist, best_v))
            row["best_effort_riegel_1.06"] = _hms(riegel(t1, d1, dist))
            if cs and cs.get("maximal") and dist <= 10000 and cs["cs_m_s"] > 0:
                row["critical_speed"] = _hms(max(dist - cs["d_prime_m"], 0) / cs["cs_m_s"])
            out["predictions"][name] = row
        out["critical_speed"] = cs
        out["best_effort_note"] = ("best-effort methods use your fastest recorded stretches; if "
                                   "those were not race efforts they describe training pace, "
                                   "not capability")
    g = conn.execute("SELECT t5k_s, t10k_s, half_s, marathon_s FROM race_predictions "
                     "WHERE day<=? ORDER BY day DESC LIMIT 1", (end,)).fetchone()
    if g:
        for name, val in zip(RACES_M, g):
            out["predictions"].setdefault(name, {})["garmin"] = _hms(val)
    km8 = conn.execute(
        "SELECT COALESCE(SUM(distance_m), 0) / 1000.0 / 8 FROM activities WHERE type LIKE '%run%'"
        " AND substr(start_time_local,1,10) BETWEEN ? AND ?",
        ((date.fromisoformat(end) - timedelta(days=55)).isoformat(), end)).fetchone()[0]
    out["weekly_run_km_8wk"] = round(km8, 1)
    if km8 < 30:
        out["volume_warning"] = (f"Average {km8:.1f} km/week over 8 weeks: half-marathon and "
                                 "marathon predictions assume endurance you have not trained; "
                                 "expect to be slower (rule of thumb: marathon needs ~40+ km/week).")
    out["note"] = ("Predictions assume race-specific training; marathon predictions from short "
                   "efforts are optimistic for low weekly volume. Riegel exponent 1.06 is for "
                   "trained runners.")
    return out


def _hms(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    s = round(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


# --------------------------------------------------------------------------- build tables
def rebuild(conn: sqlite3.Connection, asof: str | None = None) -> dict[str, Any]:
    """Compute per-activity load and the daily fitness/fatigue/form series."""
    th = thresholds(conn, asof)
    asof = th["asof"]
    cs = critical_speed(pace_curve(conn, asof, 180)["curve"])
    threshold_speed = th.get("threshold_speed_override") or (
        cs["cs_m_s"] if cs and cs.get("maximal") else None)  # no rTSS otherwise
    conn.execute("DROP TABLE IF EXISTS activity_load")
    conn.execute("CREATE TABLE activity_load (activity_id INTEGER PRIMARY KEY, day TEXT, type TEXT,"
                 " trimp REAL, trimp_from TEXT, rtss REAL, z1_s REAL, z2_s REAL, z3_s REAL,"
                 " garmin_load REAL)")
    rows = []
    for a in conn.execute("SELECT activity_id, type, start_time_local, duration_s, avg_hr, "
                          "garmin_training_load FROM activities").fetchall():
        a = dict(zip(("activity_id", "type", "start", "duration_s", "avg_hr", "garmin_load"), a))
        if not a["start"]:
            continue
        load = activity_load(conn, a, th, threshold_speed)
        rows.append((a["activity_id"], a["start"][:10], a["type"], load["trimp"],
                     load["trimp_from"], load["rtss"], *load["zone_s"], a["garmin_load"]))
    conn.executemany("INSERT INTO activity_load VALUES (?,?,?,?,?,?,?,?,?,?)", rows)

    conn.execute("DROP TABLE IF EXISTS fitness")
    conn.execute("CREATE TABLE fitness (day TEXT PRIMARY KEY, load REAL, ctl REAL, atl REAL, "
                 "tsb REAL, ramp REAL, monotony REAL, strain REAL)")
    daily = dict(conn.execute("SELECT day, SUM(trimp) FROM activity_load GROUP BY day"))
    if daily:
        d = date.fromisoformat(min(daily))
        last = date.fromisoformat(max(max(daily), asof))
        ctl = atl = 0.0
        hist: list[tuple] = []
        loads: list[float] = []
        while d <= last:
            key = d.isoformat()
            load = daily.get(key, 0.0) or 0.0
            tsb = ctl - atl  # yesterday's values (TrainingPeaks convention)
            ctl, atl = ewma(ctl, load, CTL_DAYS), ewma(atl, load, ATL_DAYS)
            loads.append(load)
            week = loads[-7:]
            mono = (statistics.fmean(week) / statistics.stdev(week)
                    if len(week) == 7 and statistics.stdev(week) > 0 else None)
            ramp = ctl - hist[-7][2] if len(hist) >= 7 else None
            hist.append((key, load, ctl, atl, tsb, ramp, mono, sum(week) * mono if mono else None))
            d += timedelta(days=1)
        conn.executemany("INSERT INTO fitness VALUES (?,?,?,?,?,?,?,?)",
                         [(k, round(lo, 1), round(c, 1), round(a, 1), round(t, 1),
                           round(r, 1) if r is not None else None,
                           round(m, 2) if m else None, round(s, 1) if s else None)
                          for k, lo, c, a, t, r, m, s in hist])
    conn.commit()
    return {"thresholds": th, "critical_speed": cs, "activities": len(rows),
            "fitness_days": conn.execute("SELECT COUNT(*) FROM fitness").fetchone()[0]}


# --------------------------------------------------------------------------- sense checks
def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 10:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy) if sx and sy else None


def zone_time_check(conn: sqlite3.Connection) -> dict[str, Any]:
    """Recompute Garmin's own HR-zone times from the FIT HR stream with Garmin's bounds.
    Agreement proves our stream integration (timing, gaps, units) is right."""
    import json

    errs = []
    for aid, secs, bounds in conn.execute(
            "SELECT activity_id, hr_zone_s, hr_zone_bounds FROM fit_zones LIMIT 60"):
        g = json.loads(secs or "null")
        b = json.loads(bounds or "null")
        if not g or not b:
            continue
        ours = [0.0] * len(g)
        recs = _records(conn, aid)
        for prev, cur in itertools.pairwise(recs):
            if not prev[1]:
                continue
            dt = _ts(cur[0]) - _ts(prev[0])
            if dt > 10:
                continue
            # Garmin zone upper bounds are exclusive (verified: 0-1% agreement).
            idx = next((i for i, hi in enumerate(b) if prev[1] < hi), len(b))
            if idx < len(ours):
                ours[idx] += dt
        total = sum(g)
        if total > 600:
            errs.append(sum(abs(o - x) for o, x in zip(ours, g)) / total * 100)
    return {"activities": len(errs),
            "median_abs_error_pct": round(statistics.median(errs), 1) if errs else None}


def sense_checks(conn: sqlite3.Connection, asof: str) -> dict[str, Any]:
    """Compare our numbers with Garmin's and with physics. Each check states its tolerance."""
    th = thresholds(conn, asof)
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool | None, detail: str, tolerance: str) -> None:
        checks.append({"check": name, "ok": ok, "detail": detail, "tolerance": tolerance})

    # 1. Our 7-day load vs Garmin's acute load (different models; should move together).
    rows = conn.execute(
        "SELECT f.day, f.atl, t.acute_load FROM fitness f JOIN training t USING(day) "
        "WHERE t.acute_load IS NOT NULL AND f.day >= ?",
        ((date.fromisoformat(asof) - timedelta(days=365)).isoformat(),)).fetchall()
    r = _pearson([x[1] for x in rows], [x[2] for x in rows])
    add("ATL (TRIMP) vs Garmin acute load correlation", None if r is None else r > 0.7,
        f"r = {r:.2f} over {len(rows)} days" if r is not None else "not enough days",
        "r > 0.7 (different models, same direction)")

    # 2. Effective VO2max vs Garmin VO2max.
    eff = effective_vo2max(conn, asof, th["hr_max"], 180) if th["hr_max"] else {"value": None}
    g = conn.execute("SELECT vo2max_run FROM training WHERE vo2max_run IS NOT NULL AND day<=? "
                     "ORDER BY day DESC LIMIT 1", (asof,)).fetchone()
    if eff.get("value") and g:
        diff = eff["value"] - g[0]
        add("Effective VO2max vs Garmin VO2max", abs(diff) <= 10,
            f"ours {eff['value']} vs Garmin {g[0]} ({diff:+.1f})",
            "within 10 (Daniels VDOT-scale vs Firstbeat physiology differ systematically)")

    # 3. Speed physics: cadence (one foot) x 2 x step length = speed.
    row = conn.execute(
        "SELECT AVG(r.cadence * 2 * r.step_length / 1000 / 60), AVG(r.speed) FROM fit_records r "
        "JOIN activities a USING(activity_id) WHERE a.type IN ('running','trail_running') AND "
        "r.speed > 1.5 AND r.cadence > 60 AND r.step_length > 0").fetchone()
    if row and row[0] and row[1]:
        pct = (row[0] - row[1]) / row[1] * 100
        add("Running physics: cadence x stride = speed", abs(pct) <= 5,
            f"{row[0]:.2f} vs {row[1]:.2f} m/s ({pct:+.1f}%)", "within 5%")

    # 4. HR-zone time recomputed vs Garmin's own zone times.
    z = zone_time_check(conn)
    if z["median_abs_error_pct"] is not None:
        add("HR-zone time vs Garmin's FIT zone times", z["median_abs_error_pct"] <= 5,
            f"median total abs error {z['median_abs_error_pct']}% over {z['activities']} activities",
            "<= 5% of moving time")

    # 5. Threshold consistency.
    if th["lthr"] and th["hr_max"]:
        add("LTHR below HRmax", th["lthr"] < th["hr_max"],
            f"LTHR {th['lthr']} vs HRmax {th['hr_max']}", "LTHR < HRmax")
    obs = th.get("observed_hr_max") or th["hr_max"]
    add("Garmin max-HR setting vs observed", th["garmin"]["hr_max_setting"] is None or
        abs((th["garmin"]["hr_max_setting"] or 0) - (obs or 0)) < 8,
        f"Garmin {th['garmin']['hr_max_setting']} vs observed {obs}"
        + (" (you set an override)" if "hr_max" in th.get("overrides", {}) else ""),
        "within 8 bpm")

    # 6. Training load per run: our TRIMP vs Garmin load should correlate across runs.
    rows = conn.execute("SELECT trimp, garmin_load FROM activity_load WHERE type IN "
                        "('running','trail_running','treadmill_running') AND garmin_load > 0"
                        ).fetchall()
    r = _pearson([x[0] for x in rows], [x[1] for x in rows])
    add("Per-run TRIMP vs Garmin training load", None if r is None else r > 0.6,
        f"r = {r:.2f} over {len(rows)} runs" if r is not None else "fewer than 10 runs",
        "r > 0.6")
    # 7. Our stream-derived running form vs Garmin's own session averages.
    from garmin_mcp import coaching

    for k, v in coaching.session_unit_check(conn).items():
        add(f"Running form unit check: {k}", v["median_abs_diff_pct"] <= 3,
            f"median diff {v['median_abs_diff_pct']}% over {v['runs']} runs",
            "within 3% of Garmin's FIT session average")
    # 8. Phase 10 scores vs Garmin's nearest equivalents.
    from garmin_mcp import scores

    for c in scores.sense_checks(conn, asof):
        add(c["check"], c["ok"], c["detail"], c["tolerance"])
    return {"asof": asof, "all_ok": all(c["ok"] is not False for c in checks),
            "checks": checks, "threshold_notes": th["notes"]}
