"""Read-side queries over the tidy tables: health snapshot, day view, trends, activities.

Everything here reads the local database only. Garmin's own scores are labelled as Garmin's;
the few comparisons we add (7-day vs 60-day baselines) are plain arithmetic, shown with their
inputs. Thresholds used for flags are documented inline and in METRICS.md.
"""

from __future__ import annotations

import json
import math
import sqlite3
import statistics
from datetime import date, timedelta
from typing import Any

from garmin_mcp.fit import cadence_units
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
    from garmin_mcp.recovery import nightly_hrv

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
    history = nightly_hrv(conn, (date.fromisoformat(day) - timedelta(days=59)).isoformat(), day)
    hrv_night = history.get(day)
    band = (hrv.get("baseline_low") or hs.get("hrv_low"),
            hrv.get("baseline_high") or hs.get("hrv_high"))
    hrv_status = hrv.get("status") or hs.get("status_hrv")
    cutoff = (date.fromisoformat(day) - timedelta(days=6)).isoformat()
    week_hrv = [v for d, v in history.items() if d >= cutoff]
    hrv7 = statistics.fmean(week_hrv) if week_hrv else None
    hrv60 = statistics.fmean(history.values()) if history else None
    if hrv_night and band[0] is not None and band[1] is not None and hrv_night < band[0]:
        flags.append(f"HRV {hrv_night:.0f} ms below your baseline band ({band[0]:.0f}-"
                     f"{band[1]:.0f}).")
    hrv_out = {
        "last_night_ms": hrv_night,
        "garmin_weekly_avg_ms": hrv.get("weekly_avg"),
        "garmin_baseline_band_ms": list(band) if None not in band else None,
        "garmin_status": hrv_status,
        "avg_7d_ms": _r(hrv7), "avg_60d_ms": _r(hrv60), "days_in_60d": len(history),
        "days_in_7d": len(week_hrv),
        "meaning": "Compare overnight HRV with your usual range and other recovery signals. "
                   "Sleep, recent training, stress and measurement quality can affect it.",
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
        score = rd.get("score")
        number = f" ({score:.0f})" if isinstance(score, (int, float)) else ""
        flags.append(f"Garmin Training Readiness {rd['level']}{number}.")
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
    cadence_scale, cadence_unit = cadence_units(a["type"])
    laps = [dict(r) for r in conn.execute(
        "SELECT lap_index, timer_s, distance_m, avg_hr, max_hr, avg_speed, avg_cadence, "
        "avg_power FROM fit_laps WHERE activity_id=? ORDER BY lap_index", (activity_id,))]
    for lap in laps:
        sp = lap.pop("avg_speed")
        lap["pace_min_km"] = _hms(1000 / sp) if sp else None
        cad = lap.pop("avg_cadence")
        lap["avg_cadence_spm"] = cad * cadence_scale if cad is not None else None
        lap["cadence_unit"] = cadence_unit
    stream = conn.execute(
        "SELECT COUNT(*), AVG(heart_rate), AVG(cadence), AVG(power), AVG(vertical_oscillation),"
        " AVG(stance_time), AVG(step_length), MAX(altitude)-MIN(altitude), AVG(temperature) "
        "FROM fit_records WHERE activity_id=?", (activity_id,)).fetchone()
    form = None
    if stream and stream[0]:
        form = {"samples": stream[0], "avg_hr": _r(stream[1]),
                "avg_cadence_spm": _r(stream[2] * cadence_scale) if stream[2] is not None else None,
                "cadence_unit": cadence_unit,
                "avg_power_w": _r(stream[3]),
                "avg_vertical_oscillation_mm": _r(stream[4]),
                "avg_ground_contact_ms": _r(stream[5]),
                "avg_step_length_mm": _r(stream[6]),
                "altitude_range_m": _r(stream[7]), "avg_temperature_c": _r(stream[8])}
    details = {k: json.loads(v) for k, v in conn.execute(
        "SELECT kind, payload FROM activity_details WHERE activity_id=? AND kind IN "
        "('hr_zones','weather')", (activity_id,))}
    try:
        load = conn.execute("SELECT trimp, trimp_from, rtss, z1_s, z2_s, z3_s FROM activity_load "
                            "WHERE activity_id=?", (activity_id,)).fetchone()
    except sqlite3.OperationalError:  # load tables not built yet (fresh database)
        load = None
    return {
        "load": {"trimp": load[0], "trimp_from": load[1], "rtss": load[2],
                 "seiler_zone_s": list(load[3:6])} if load else None,
        "swim": swim_summary(conn, activity_id),
        "strength": strength_summary(conn, activity_id),
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
        "ORDER BY day", (start, end)) if isinstance(v, (int, float)) and math.isfinite(v)]
    nums = [v for _, v in pts]
    out: dict[str, Any] = {"metric": metric, "from": start, "to": end, "points": len(pts)}
    if nums:
        half = len(nums) // 2 or 1
        out.update(avg=_r(sum(nums) / len(nums), 2), min=min(nums), max=max(nums),
                   first_half_avg=_r(sum(nums[:half]) / half, 2),
                   second_half_avg=_r(sum(nums[half:]) / (len(nums) - half), 2) if len(nums) > half else None)
    out["series"] = pts if days <= 120 else pts[-120:]
    return out


# --------------------------------------------------------------------------- daily brief
def daily_brief(conn: sqlite3.Connection, day: str | None = None, *,
                signals: dict | None = None, patterns: list[dict] | None = None) -> dict[str, Any]:
    """Morning-report style brief: the facts Claude narrates (Athlete-Intelligence style)."""
    from garmin_mcp import coach_loop, daily_focus, engine, recovery, signal_context, training_plan

    day = day or _latest_day(conn) or date.today().isoformat()
    r = recovery.readiness(conn, day)
    recommendation = recovery.suggestion(r)
    if signals is None:
        signals = signal_context.collect(conn, day, with_history=False)
    if patterns is None:
        patterns = engine.relationships(conn, day)["notable"]
    snap = health_snapshot(conn, day)
    by_type = snap["recent_activities"]["by_type"]
    running_km = sum(by_type.get(t, {}).get("km", 0) for t in training_plan.RUN_ACTIVITY_TYPES)
    focus = daily_focus.daily_focus(
        r, signals, recommendation, training_status=snap["training"]["garmin_status"],
        running_km=running_km, patterns=patterns)
    week_ahead = training_plan.week(conn, day, r)
    knee_pause = coach_loop.knee_pause(conn, day)
    if knee_pause and focus["title"] not in {
            "Pause training today.", "Rest today or choose very easy movement."}:
        detail = "Your previous evening check-in flagged knee soreness."
        focus.update(title="Skip running today.", detail=detail, target="training", findings=[],
                     evidence_keys=("knee_checkin",))
        recommendation = {**recommendation, "suggest": "skip running today", "reason": detail}
        week_ahead = {"plan": "Leave running out today and reassess tomorrow.", "basis": detail}
    yesterday = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    return {
        "day": day,
        "suggestion": recommendation,
        "focus": focus,
        "week_ahead": week_ahead,
        "knee_pause": knee_pause,
        "readiness": {"ours": {k: r["ours"][k] for k in ("composite_z", "state", "components", "minimum_signals",
                                                          "holding_back", "helping")},
                      "garmin": r["garmin"]},
        "hrv": {k: r["hrv"].get(k) for k in ("state", "rolling_7d_ms", "normal_band_ms",
                                              "last_night_ms", "cv_7d_pct")},
        "sleep": r["sleep"],
        "illness_flag": r["illness_flag"]["raised"],
        "illness_details": r["illness_flag"],
        "garmin_training_status": snap["training"]["garmin_status"],
        "yesterday_activities": recent_activities(conn, days=1, end=yesterday)["activities"],
        "week_so_far": snap["recent_activities"],
        "intensity_minutes_7d": snap["everyday_activity"]["intensity_minutes_7d"],
        "flags": snap["flags"],
        "narrate_as": "Lead with focus. Connect the action to the recorded changes in plain language.",
    }


# --------------------------------------------------------------------------- sport detail
def swim_summary(conn: sqlite3.Connection, activity_id: int) -> dict[str, Any] | None:
    """Pool swim: pace/100 m, strokes per length, SWOLF (time + strokes per length) by stroke."""
    sess = conn.execute("SELECT payload FROM fit_sessions WHERE activity_id=?",
                        (activity_id,)).fetchone()
    pool = None
    if sess:
        s0 = (json.loads(sess[0]) or [{}])[0]
        pool = s0.get("pool_length")
    rows = conn.execute("SELECT stroke, time_s, strokes FROM fit_lengths WHERE activity_id=? "
                        "AND length_type='active' AND time_s > 0", (activity_id,)).fetchall()
    if not rows or not pool:
        return None
    by: dict[str, list[tuple[float, float]]] = {}
    for stroke, t, n in rows:
        by.setdefault(stroke, []).append((t, n or 0))
    out = {}
    for stroke, vals in by.items():
        t_avg = sum(t for t, _ in vals) / len(vals)
        n_avg = sum(n for _, n in vals) / len(vals)
        out[stroke] = {"lengths": len(vals), "pace_per_100m": _hms(t_avg / pool * 100),
                       "strokes_per_length": _r(n_avg), "swolf": _r(t_avg + n_avg)}
    total_t = sum(t for _, t, _ in rows)
    return {"pool_length_m": pool, "active_lengths": len(rows),
            "distance_m": round(len(rows) * pool),
            "pace_per_100m": _hms(total_t / (len(rows) * pool) * 100), "by_stroke": out,
            "meaning": "SWOLF = seconds + strokes per length; lower is more efficient. Compare "
                       "only within the same stroke and pool length."}


def strength_summary(conn: sqlite3.Connection, activity_id: int) -> dict[str, Any] | None:
    rows = conn.execute("SELECT category, repetitions, weight_kg, duration_s FROM fit_sets "
                        "WHERE activity_id=? AND set_type='active'", (activity_id,)).fetchall()
    if not rows:
        return None
    by: dict[str, dict[str, float]] = {}
    for cat, reps, w, dur in rows:
        name = (cat or "unlabelled").split("/")[0]
        e = by.setdefault(name, {"sets": 0, "reps": 0, "volume_kg": 0.0})
        e["sets"] += 1
        e["reps"] += reps or 0
        e["volume_kg"] += (reps or 0) * (w or 0)
    return {"sets": len(rows), "reps": sum(r[1] or 0 for r in rows),
            "volume_kg": _r(sum((r[1] or 0) * (r[2] or 0) for r in rows)),
            "by_exercise": by,
            "note": "Exercise names and weights come from the watch's rep detection or your "
                    "edits in Garmin Connect; unlabelled sets were not identified."}


# --------------------------------------------------------------------------- weekly review
def weekly_review(conn: sqlite3.Connection, end: str | None = None) -> dict[str, Any]:
    """Last 7 days vs the 4 weeks before: volume, load, intensity, form, recovery."""
    from garmin_mcp import loads, recovery

    end = end or _latest_day(conn) or date.today().isoformat()
    e = date.fromisoformat(end)
    start = (e - timedelta(days=6)).isoformat()
    prev_start = (e - timedelta(days=34)).isoformat()
    prev_end = (e - timedelta(days=7)).isoformat()

    def agg(a: str, b: str) -> dict[str, Any]:
        r = conn.execute(
            "SELECT COUNT(*), SUM(a.duration_s), SUM(CASE WHEN a.type LIKE '%run%' THEN "
            "a.distance_m END), SUM(l.trimp), SUM(l.garmin_load), SUM(l.z1_s), SUM(l.z2_s), "
            "SUM(l.z3_s) FROM activities a JOIN activity_load l USING(activity_id) "
            "WHERE l.day BETWEEN ? AND ?", (a, b)).fetchone()
        return {"sessions": r[0], "hours": _r((r[1] or 0) / 3600, 2),
                "run_km": _r((r[2] or 0) / 1000, 1), "trimp": _r(r[3] or 0.0),
                "garmin_load": _r(r[4] or 0.0), "zone_s": [r[5] or 0, r[6] or 0, r[7] or 0]}

    week, prev4 = agg(start, end), agg(prev_start, prev_end)
    avg_prev = {k: _r(prev4[k] / 4, 1) for k in ("sessions", "hours", "run_km", "trimp")}
    z = week["zone_s"]
    tz = sum(z) or 1
    fit = conn.execute("SELECT ctl, atl, tsb, ramp, monotony, strain FROM fitness WHERE day=?",
                       (end,)).fetchone()
    longest = conn.execute(
        "SELECT name, distance_m, duration_s FROM activities WHERE type LIKE '%run%' AND "
        "substr(start_time_local,1,10) BETWEEN ? AND ? ORDER BY distance_m DESC LIMIT 1",
        (start, end)).fetchone()
    trend = recovery.recovery_trend(conn, end, 7)["days"]
    sleep_vals = [d["sleep_h"] for d in trend if d["sleep_h"]]
    change = (week["trimp"] / avg_prev["trimp"] - 1) * 100 if avg_prev["trimp"] else None
    return {
        "week": {"from": start, "to": end, **week,
                 "intensity_pct": [round(100 * x / tz) for x in z],
                 "polarization_index": loads.polarization_index(*z)},
        "previous_4wk_weekly_avg": avg_prev,
        "load_change_pct": _r(change, 0) if change is not None else None,
        "fitness": dict(zip(("ctl", "atl", "tsb", "ramp", "monotony", "strain"), fit))
        if fit else None,
        "longest_run": {"name": longest[0], "km": _r(longest[1] / 1000, 2),
                        "duration": _hms(longest[2])} if longest and longest[1] else None,
        "recovery": {"avg_sleep_h": _r(sum(sleep_vals) / len(sleep_vals), 2)
                     if sleep_vals else None,
                     "sleep_nights": len(sleep_vals),
                     "readiness_states": [d["state"] for d in trend],
                     "illness_flag_days": sum(1 for d in trend if d["illness_flag"])},
        "by_type": recent_activities(conn, days=7, end=end)["summary"]["by_type"],
        "narrate_as": "Weekly recap: volume and load vs usual, intensity balance, form, "
                      "recovery, one focus for next week.",
    }
