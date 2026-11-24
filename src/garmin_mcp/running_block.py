"""Recorded running volume and comparable effort evidence for a training block."""

from datetime import date, timedelta
from math import isfinite
from statistics import median

from garmin_mcp import coach_loop, coaching
from garmin_mcp.loads import RUN_TYPES

WEEKS = 12
FIT_LIMIT = 48
READINGS_MIN = 3


def _positive(value):
    return isinstance(value, (int, float)) and isfinite(value) and value > 0


def _totals(rows):
    return {
        "runs": len(rows),
        "days": len({row["day"] for row in rows}),
        "km": round(sum(row["km"] or 0 for row in rows), 1),
        "distance_count": sum(row["km"] is not None for row in rows),
        "longest_km": round(max((row["km"] or 0 for row in rows), default=0), 1),
    }


def _next_check(recent, previous, efforts, latest):
    match = (latest or {}).get("comparable_effort", {})
    if match.get("available"):
        low, high = match["observed_hr_range_bpm"]
        pulse = match["this_run"]["avg_hr_bpm"]
        if not low <= pulse <= high:
            return {
                "title": "Repeat the effort before drawing a conclusion",
                "action": "On your next easy run, use a similar route and duration. Keep effort conversational "
                          "and note differences in heat, hills and watch fit.",
                "basis": f"Moving heart rate was {pulse:g} bpm against an earlier span of {low:g}–{high:g} bpm.",
                "target": f'run-{latest["activity_id"]}-compare',
            }
    if recent["runs"] == 0:
        return {
            "title": "Rebuild the running record",
            "action": "If you’re ready to run, choose an easy outing you can repeat and record how it felt.",
            "basis": "No runs were recorded in the last four completed weeks.", "target": "running-block",
        }
    if previous["runs"] and recent["days"] < previous["days"]:
        return {
            "title": "Build a repeatable rhythm",
            "action": "Pick a familiar day for an easy run and keep it short enough to repeat comfortably.",
            "basis": f'{recent["days"]} recorded running days in the last four completed weeks, '
                     f'compared with {previous["days"]} in the four before.',
            "target": "running-block",
        }
    return {
        "title": "Make the next easy run a benchmark",
        "action": "Use a familiar route at conversational effort. Record how it felt and compare pace and "
                  "moving heart rate with similar outings.",
        "basis": (f"{len(efforts)} steady outdoor runs with usable heart rate in the sampled block."
                  if efforts else "A steady outdoor recording gives the dashboard a pace and heart-rate reference."),
        "target": "running-efforts",
    }


def collect(conn, end, *, read_metrics=coaching.run_metrics, latest=None):
    """Build a dated view without using activities recorded after the snapshot."""
    end_day = date.fromisoformat(end)
    monday = end_day - timedelta(days=end_day.weekday())
    start = monday - timedelta(weeks=WEEKS)
    kinds = coach_loop.KINDS["run"]
    placeholders = ",".join("?" for _ in kinds)
    weeks = [{"start": (start + timedelta(weeks=i)).isoformat(),
               "complete": i < WEEKS, "activities": []} for i in range(WEEKS + 1)]
    for aid, day, kind, metres, parsed in conn.execute(
        f"SELECT activity_id, substr(start_time_local,1,10), type, distance_m, fit_parsed "
        f"FROM activities WHERE type IN ({placeholders}) AND start_time_local>=? AND start_time_local<? "
        "AND date(substr(start_time_local,1,10)) IS NOT NULL "
        "ORDER BY start_time_local DESC, activity_id DESC",
        (*kinds, start.isoformat(), (end_day + timedelta(days=1)).isoformat()),
    ):
        days = (date.fromisoformat(day) - start).days
        weeks[days // 7]["activities"].append(
            {"id": aid, "day": day, "kind": kind, "km": metres / 1000 if _positive(metres) else None,
             "fit": bool(parsed)})
    recent = _totals([row for week in weeks[-5:-1] for row in week["activities"]])
    previous = _totals([row for week in weeks[-9:-5] for row in week["activities"]])
    candidates = [row for week in reversed(weeks) for row in week["activities"]
                  if row["fit"] and row["kind"] in RUN_TYPES]
    efforts = []
    for row in candidates[:FIT_LIMIT]:
        metrics = read_metrics(conn, row["id"])
        if (not metrics or not metrics["steady"] or not _positive(metrics["avg_hr"])
                or metrics["moving_s"] < 0.8 * metrics["recorded_elapsed_s"]):
            continue
        efforts.append({
            "id": row["id"], "day": row["day"], "kind": row["kind"], "km": row["km"],
            "pace_s_per_km": round(1000 / metrics["avg_speed"]),
            "pulse": metrics["avg_hr"], "moving_s": metrics["moving_s"],
            "decoupling_pct": metrics.get("decoupling_pct"),
        })
    decoupling = [e["decoupling_pct"] for e in efforts if e["decoupling_pct"] is not None]
    cutoff = (end_day - timedelta(days=27)).isoformat()
    latest = latest if latest and cutoff <= latest["date"] <= end else None
    next_check = _next_check(recent, previous, efforts, latest)
    if coach_loop.knee_pause(conn, end):
        next_check = {"title": "Leave running out today",
                      "action": "Reassess tomorrow before choosing a repeat run.",
                      "basis": "Your previous evening check-in flagged knee soreness.", "target": "today"}
    return {
        "weeks": [{**_totals(week["activities"]), "start": week["start"],
                   "complete": week["complete"]} for week in weeks],
        "recent": recent, "previous": previous,
        "efforts": efforts, "effort_candidates": len(candidates),
        "sampled": min(len(candidates), FIT_LIMIT),
        "median_decoupling": round(median(decoupling), 1) if len(decoupling) >= READINGS_MIN else None,
        "decoupling_count": len(decoupling),
        "has_runs": any(week["activities"] for week in weeks),
        "latest_detail_id": latest["activity_id"] if latest else None,
        "next": next_check,
    }
