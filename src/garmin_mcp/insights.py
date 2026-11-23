"""Read-side queries over the tidy tables: health snapshot, day view, trends, activities.

Everything here reads the local database only. Garmin's own scores are labelled as Garmin's;
the few comparisons we add (7-day vs 60-day baselines) are plain arithmetic, shown with their
inputs. Thresholds used for flags are documented inline and in METRICS.md.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from typing import Any

from garmin_mcp.normalize import TABLES


# --------------------------------------------------------------------------- primitives
def _r(value: Any, nd: int = 1) -> Any:
    return round(value, nd) if isinstance(value, float) else value


def _latest_day(conn: sqlite3.Connection, table: str = "daily") -> str | None:
    row = conn.execute(f"SELECT MAX(day) FROM {table}").fetchone()
    return row[0] if row else None


def _row(conn: sqlite3.Connection, table: str, day: str) -> dict[str, Any] | None:
    cur = conn.execute(f"SELECT * FROM {table} WHERE day=?", (day,))
    row = cur.fetchone()
    return dict(zip([c[0] for c in cur.description], row)) if row else None


def _last_known(conn: sqlite3.Connection, table: str, col: str, upto: str,
                max_age_days: int = 120) -> tuple[Any, str | None]:
    """Most recent non-null value on or before `upto` (Garmin updates some metrics rarely)."""
    lo = (date.fromisoformat(upto) - timedelta(days=max_age_days)).isoformat()
    row = conn.execute(
        f"SELECT {col}, day FROM {table} WHERE {col} IS NOT NULL AND day<=? AND day>=? "
        "ORDER BY day DESC LIMIT 1", (upto, lo)).fetchone()
    return (row[0], row[1]) if row else (None, None)


def _avg(conn: sqlite3.Connection, table: str, col: str, end: str, days: int,
         skip_last: bool = False) -> tuple[float | None, int]:
    hi = date.fromisoformat(end) - timedelta(days=1 if skip_last else 0)
    lo = hi - timedelta(days=days - 1)
    row = conn.execute(
        f"SELECT AVG({col}), COUNT({col}) FROM {table} WHERE day BETWEEN ? AND ?",
        (lo.isoformat(), hi.isoformat())).fetchone()
    return (row[0], row[1]) if row else (None, 0)


def _sum(conn: sqlite3.Connection, table: str, col: str, end: str, days: int) -> float | None:
    lo = (date.fromisoformat(end) - timedelta(days=days - 1)).isoformat()
    row = conn.execute(f"SELECT SUM({col}) FROM {table} WHERE day BETWEEN ? AND ?",
                       (lo, end)).fetchone()
    return row[0] if row else None


def _hms(seconds: Any) -> str | None:
    if not isinstance(seconds, (int, float)):
        return None
    s = round(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else \
        f"{s // 60}:{s % 60:02d}"


def _hours(seconds: Any) -> float | None:
    return round(seconds / 3600, 2) if isinstance(seconds, (int, float)) else None


# --------------------------------------------------------------------------- snapshot
def health_snapshot(conn: sqlite3.Connection, day: str | None = None) -> dict[str, Any]:
    day = day or _latest_day(conn) or date.today().isoformat()
    flags: list[str] = []

    # Sleep: the sleep row dated `day` is the night that ended that morning.
    sleep = _row(conn, "sleep", day) or {}
    sleep_night = day
    if not sleep:
        flags.append(f"No sleep recorded for the night ending {day} (watch not worn, or not "
                     "synced yet). Showing the last recorded night.")
        last = conn.execute("SELECT MAX(day) FROM sleep WHERE day<=?", (day,)).fetchone()[0]
        if last:
            sleep, sleep_night = _row(conn, "sleep", last) or {}, last
    lo28 = (date.fromisoformat(day) - timedelta(days=28)).isoformat()
    sleep_avg28 = conn.execute(
        "SELECT AVG(sleep_s) FROM sleep WHERE day >= ? AND day < ? AND sleep_s >= 3*3600",
        (lo28, day)).fetchone()[0]  # nights under 3 h are incomplete records
    sleep_h = _hours(sleep.get("sleep_s"))
    if sleep_h is not None and sleep_h < 3:
        flags.append(f"Sleep record for the night ending {sleep_night} is only {sleep_h} h: "
                     "likely incomplete (watch off or nap only).")
    elif sleep_h is not None and sleep_h < 6:
        flags.append(f"Short sleep: {sleep_h} h on the night ending {sleep_night} (under 6 h).")
    stages = {k: sleep.get(f"{k}_s") for k in ("deep", "light", "rem", "awake")}
    total = sum(v for k, v in stages.items() if k != "awake" and v) or None
    sleep_out = {
        "night_ending": sleep_night if sleep else None,
        "hours": sleep_h,
        "garmin_sleep_score": sleep.get("score"),
        "stages_pct": {k: _r(100 * v / total) for k, v in stages.items()
                       if v is not None and total and k != "awake"} or None,
        "avg_28d_hours": _hours(sleep_avg28),
        "avg_28d_note": "valid nights only (>= 3 h)",
        "sleep_need_hours": _r(sleep["sleep_need_min"] / 60, 2)
        if sleep.get("sleep_need_min") else None,
        "avg_sleep_stress": sleep.get("avg_sleep_stress"),
        "meaning": "Duration and consistency matter most; compare tonight's hours with your "
                   "28-day average and Garmin's sleep need.",
    }

    # HRV: Garmin HRV status (Personal API/unofficial) or health-status HRV (export).
    hrv = _row(conn, "hrv", day) or {}
    hs = _row(conn, "health_status", day) or {}
    hrv_night = hrv.get("last_night_avg") or hs.get("hrv")
    band = (hrv.get("baseline_low") or hs.get("hrv_low"),
            hrv.get("baseline_high") or hs.get("hrv_high"))
    hrv_status = hrv.get("status") or hs.get("status_hrv")
    hrv7, _ = _avg(conn, "health_status", "hrv", day, 7)
    hrv60, n60 = _avg(conn, "health_status", "hrv", day, 60)
    if hrv_night and band[0] and hrv_night < band[0]:
        flags.append(f"HRV {hrv_night:.0f} ms below your baseline band ({band[0]:.0f}-"
                     f"{band[1]:.0f}).")
    hrv_out = {
        "last_night_ms": hrv_night,
        "garmin_weekly_avg_ms": hrv.get("weekly_avg"),
        "garmin_baseline_band_ms": list(band) if band[0] else None,
        "garmin_status": hrv_status,
        "avg_7d_ms": _r(hrv7), "avg_60d_ms": _r(hrv60), "days_in_60d": n60,
        "meaning": "Overnight HRV inside your own baseline band = recovered nervous system; "
                   "a sustained drop below it suggests fatigue, illness or stress.",
    }

    # Resting heart rate vs baseline (heuristic flag: +5 bpm over the 60-day mean).
    daily = _row(conn, "daily", day) or {}
    rhr = daily.get("resting_hr") or hs.get("rhr")
    rhr7, _ = _avg(conn, "daily", "resting_hr", day, 7)
    rhr60, _ = _avg(conn, "daily", "resting_hr", day, 60, skip_last=True)
    if rhr and rhr60 and rhr - rhr60 >= 5:
        flags.append(f"Resting HR {rhr:.0f} bpm is {rhr - rhr60:.0f} above your 60-day "
                     "average.")
    rhr_out = {"today_bpm": rhr, "avg_7d_bpm": _r(rhr7), "avg_60d_bpm": _r(rhr60),
               "meaning": "A resting HR several bpm above your normal often precedes illness "
                          "or reflects accumulated fatigue."}

    # Garmin Training Readiness.
    rd = _row(conn, "readiness", day) or {}
    if rd.get("level") in ("LOW", "POOR"):
        flags.append(f"Garmin Training Readiness {rd.get('level')} ({rd.get('score'):.0f}).")
    readiness_out = {
        "garmin_score": rd.get("score"), "garmin_level": rd.get("level"),
        "morning_score": rd.get("morning_score"),
        "factors_pct": {k.replace("_factor_pct", ""): rd.get(k) for k in TABLES["readiness"]
                        if k.endswith("_factor_pct")} if rd else None,
        "recovery_time_hours": _r(rd["recovery_time_min"] / 60)
        if rd.get("recovery_time_min") is not None else None,
        "garmin_feedback": rd.get("feedback"),
        "meaning": "Garmin's composite of sleep, recovery time, load, HRV and stress history; "
                   "factors near 100% are helping, low ones are what's holding you back.",
    } if rd else None

    # Training status, load, performance.
    tr = _row(conn, "training", day) or {}
    vo2, vo2_day = _last_known(conn, "training", "vo2max_run", day)
    if tr.get("status") in ("DETRAINING", "UNPRODUCTIVE", "OVERREACHING", "STRAINED"):
        flags.append(f"Garmin Training Status: {tr['status']}.")
    rp_row = conn.execute("SELECT * FROM race_predictions WHERE day<=? ORDER BY day DESC LIMIT 1",
                          (day,)).fetchone()
    race = None
    if rp_row:
        rp = dict(zip([c[0] for c in conn.execute("SELECT * FROM race_predictions LIMIT 0")
                       .description], rp_row))
        race = {"as_of": rp["day"], "5k": _hms(rp["t5k_s"]), "10k": _hms(rp["t10k_s"]),
                "half": _hms(rp["half_s"]), "marathon": _hms(rp["marathon_s"])}
    endurance, _ = _last_known(conn, "scores", "endurance_score", day)
    hill, _ = _last_known(conn, "scores", "hill_score", day)
    training_out = {
        "garmin_status": tr.get("status"), "garmin_fitness_trend": tr.get("fitness_trend"),
        "garmin_acute_load": tr.get("acute_load"), "garmin_chronic_load": tr.get("chronic_load"),
        "garmin_load_ratio": tr.get("acwr"), "garmin_load_ratio_status": tr.get("acwr_status"),
        "vo2max_run": vo2, "vo2max_as_of": vo2_day,
        "garmin_race_predictions": race,
        "garmin_endurance_score": endurance, "garmin_hill_score": hill,
        "note": "Load ratio is Garmin's acute:chronic view; shown as context, not an injury "
                "predictor (see METRICS.md).",
    }

    # Everyday activity.
    im7 = (_sum(conn, "daily", "intensity_min_moderate", day, 7) or 0) + \
        2 * (_sum(conn, "daily", "intensity_min_vigorous", day, 7) or 0)
    if im7 < 150:
        flags.append(f"Intensity minutes last 7 days: {im7:.0f} of the 150 WHO target "
                     "(vigorous counts double).")
    steps7, _ = _avg(conn, "daily", "steps", day, 7)
    activity_out = {
        "steps_today": daily.get("steps"), "steps_avg_7d": _r(steps7, 0),
        "intensity_minutes_7d": im7,
        "stress_avg": daily.get("stress_avg"),
        "body_battery_high_low": [daily.get("body_battery_max"), daily.get("body_battery_min")],
    }

    fa = conn.execute("SELECT * FROM fitness_age WHERE day<=? ORDER BY day DESC LIMIT 1",
                      (day,)).fetchone()
    fitness_age_out = None
    if fa:
        f = dict(zip([c[0] for c in conn.execute("SELECT * FROM fitness_age LIMIT 0")
                      .description], fa))
        fitness_age_out = {"garmin_fitness_age": _r(f["fitness_age"]),
                           "chronological_age": f["chronological_age"],
                           "achievable_age": _r(f["achievable_age"]),
                           "inputs": {"rhr": f["rhr"], "bmi": f["bmi"],
                                      "vigorous_days_per_week": f["vigorous_days_avg"],
                                      "vigorous_min_per_week": f["vigorous_min_avg"]}}

    return {
        "day": day,
        "flags": flags or ["Nothing unusual against your baselines."],
        "sleep": sleep_out, "hrv": hrv_out, "resting_hr": rhr_out,
        "garmin_training_readiness": readiness_out, "training": training_out,
        "everyday_activity": activity_out, "fitness_age": fitness_age_out,
        "recent_activities": recent_activities(conn, days=7, end=day)["summary"],
        "data_freshness": {t: _latest_day(conn, t) for t in TABLES},
    }


# --------------------------------------------------------------------------- other views
def day_view(conn: sqlite3.Connection, day: str) -> dict[str, Any]:
    out = {t: _row(conn, t, day) for t in TABLES}
    out["activities"] = recent_activities(conn, days=1, end=day)["activities"]
    return {"day": day, **{k: v for k, v in out.items() if v}}


def recent_activities(conn: sqlite3.Connection, days: int = 30, end: str | None = None,
                      activity_type: str | None = None) -> dict[str, Any]:
    end = end or date.today().isoformat()
    start = (date.fromisoformat(end) - timedelta(days=days - 1)).isoformat()
    q = ("SELECT activity_id, start_time_local, type, name, duration_s, distance_m, avg_hr, "
         "max_hr, aerobic_te, anaerobic_te, garmin_training_load, vo2max FROM activities "
         "WHERE substr(start_time_local,1,10) BETWEEN ? AND ?")
    args: list[Any] = [start, end]
    if activity_type:
        q += " AND type LIKE ?"
        args.append(f"%{activity_type}%")
    rows = [dict(r) for r in conn.execute(q + " ORDER BY start_time_local DESC", args)]
    acts = [{"id": r["activity_id"], "start": r["start_time_local"], "type": r["type"],
             "name": r["name"], "duration": _hms(r["duration_s"]),
             "distance_km": _r(r["distance_m"] / 1000, 2) if r["distance_m"] else None,
             "avg_hr": r["avg_hr"], "garmin_aerobic_te": _r(r["aerobic_te"]),
             "garmin_load": _r(r["garmin_training_load"])} for r in rows]
    by_type: dict[str, dict[str, float]] = {}
    for r in rows:
        t = by_type.setdefault(r["type"] or "other", {"count": 0, "hours": 0.0, "km": 0.0})
        t["count"] += 1
        t["hours"] = round(t["hours"] + (r["duration_s"] or 0) / 3600, 2)
        t["km"] = round(t["km"] + (r["distance_m"] or 0) / 1000, 2)
    return {"from": start, "to": end, "summary": {"count": len(rows), "by_type": by_type},
            "activities": acts}


def activity_detail(conn: sqlite3.Connection, activity_id: int) -> dict[str, Any] | None:
    a = conn.execute("SELECT * FROM activities WHERE activity_id=?", (activity_id,)).fetchone()
    if not a:
        return None
    a = dict(a)
    summary = json.loads(a.pop("summary") or "{}")
    laps = [dict(r) for r in conn.execute(
        "SELECT lap_index, timer_s, distance_m, avg_hr, max_hr, avg_speed, avg_cadence, "
        "avg_power FROM fit_laps WHERE activity_id=? ORDER BY lap_index", (activity_id,))]
    for lap in laps:
        sp = lap.pop("avg_speed")
        lap["pace_min_km"] = _hms(1000 / sp) if sp else None
        cad = lap.pop("avg_cadence")
        # FIT running cadence counts one foot; x2 = steps per minute (same as the run average).
        lap["avg_cadence_spm"] = cad * 2 if cad and a["type"] and "run" in a["type"] else cad
    stream = conn.execute(
        "SELECT COUNT(*), AVG(heart_rate), AVG(cadence), AVG(power), AVG(vertical_oscillation),"
        " AVG(stance_time), AVG(step_length), MAX(altitude)-MIN(altitude), AVG(temperature) "
        "FROM fit_records WHERE activity_id=?", (activity_id,)).fetchone()
    form = None
    if stream and stream[0]:
        form = {"samples": stream[0], "avg_hr": _r(stream[1]),
                # FIT running cadence is one foot (strides/min); x2 = steps/min.
                "avg_cadence_spm": _r(stream[2] * 2) if stream[2] else None,
                "avg_power_w": _r(stream[3]),
                "avg_vertical_oscillation_mm": _r(stream[4]),
                "avg_ground_contact_ms": _r(stream[5]),
                "avg_step_length_mm": _r(stream[6]),
                "altitude_range_m": _r(stream[7]), "avg_temperature_c": _r(stream[8])}
    details = {k: json.loads(v) for k, v in conn.execute(
        "SELECT kind, payload FROM activity_details WHERE activity_id=? AND kind IN "
        "('hr_zones','weather')", (activity_id,))}
    return {
        "id": activity_id, "name": a["name"], "type": a["type"], "start": a["start_time_local"],
        "duration": _hms(a["duration_s"]),
        "distance_km": _r(a["distance_m"] / 1000, 2) if a["distance_m"] else None,
        "avg_hr": a["avg_hr"], "max_hr": a["max_hr"], "calories": a["calories"],
        "elevation_gain_m": a["elevation_gain_m"],
        "garmin": {"aerobic_te": a["aerobic_te"], "anaerobic_te": a["anaerobic_te"],
                   "training_load": _r(a["garmin_training_load"]), "vo2max": a["vo2max"],
                   "te_label": summary.get("trainingEffectLabel")},
        "running_form_from_fit": form, "laps": laps,
        "hr_zones": details.get("hr_zones"), "weather": details.get("weather"),
    }


def trend(conn: sqlite3.Connection, metric: str, days: int = 30,
          end: str | None = None) -> dict[str, Any]:
    """metric = 'table.column', e.g. 'daily.resting_hr', 'sleep.sleep_s', 'hrv.last_night_avg'."""
    table, _, col = metric.partition(".")
    if table not in TABLES or col not in TABLES[table]:
        valid = [f"{t}.{c}" for t, cs in TABLES.items() for c in cs]
        return {"error": f"unknown metric {metric!r}", "valid_metrics": valid}
    end = end or _latest_day(conn, table) or date.today().isoformat()
    start = (date.fromisoformat(end) - timedelta(days=days - 1)).isoformat()
    pts = [(d, v) for d, v in conn.execute(
        f"SELECT day, {col} FROM {table} WHERE day BETWEEN ? AND ? AND {col} IS NOT NULL "
        "ORDER BY day", (start, end))]
    nums = [v for _, v in pts if isinstance(v, (int, float))]
    out: dict[str, Any] = {"metric": metric, "from": start, "to": end, "points": len(pts)}
    if nums:
        half = len(nums) // 2 or 1
        out.update(avg=_r(sum(nums) / len(nums), 2), min=min(nums), max=max(nums),
                   first_half_avg=_r(sum(nums[:half]) / half, 2),
                   second_half_avg=_r(sum(nums[half:]) / max(len(nums) - half, 1), 2))
    out["series"] = pts if days <= 120 else pts[-120:]
    return out


# --------------------------------------------------------------------------- daily brief
def daily_brief(conn: sqlite3.Connection, day: str | None = None) -> dict[str, Any]:
    """Morning-report style brief: the facts Claude narrates (Athlete-Intelligence style)."""
    from garmin_mcp import recovery

    day = day or _latest_day(conn) or date.today().isoformat()
    r = recovery.readiness(conn, day)
    snap = health_snapshot(conn, day)
    yesterday = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    return {
        "day": day,
        "suggestion": recovery.suggestion(r),
        "readiness": {"ours": {k: r["ours"][k] for k in ("composite_z", "state",
                                                          "holding_back", "helping")},
                      "garmin": r["garmin"]},
        "hrv": {k: r["hrv"].get(k) for k in ("state", "rolling_7d_ms", "normal_band_ms",
                                              "last_night_ms", "cv_7d_pct")},
        "sleep": r["sleep"],
        "illness_flag": r["illness_flag"]["raised"],
        "garmin_training_status": snap["training"]["garmin_status"],
        "yesterday_activities": recent_activities(conn, days=1, end=yesterday)["activities"],
        "week_so_far": snap["recent_activities"],
        "intensity_minutes_7d": snap["everyday_activity"]["intensity_minutes_7d"],
        "flags": snap["flags"],
        "narrate_as": "2-4 sentences: how recovered, why, what to do today, one thing to watch.",
    }
