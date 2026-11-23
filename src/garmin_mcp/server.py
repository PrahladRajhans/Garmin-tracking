"""MCP server. Every tool reads the local database; only `refresh_data` talks to Garmin."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

from garmin_mcp import db, insights
from garmin_mcp.client import parse_date
from garmin_mcp.config import db_path

load_dotenv()

mcp = MCPServer(
    "garmin",
    instructions=(
        "Personal Garmin Forerunner 955 data from a local database (history since the user "
        "started with Garmin). Start with health_snapshot for 'how am I doing' questions. "
        "Values prefixed garmin_ are Garmin's own scores; others are computed transparently. "
        "If data looks stale, call refresh_data."
    ),
)


def _provenance(conn: sqlite3.Connection) -> dict[str, Any]:
    try:
        through = conn.execute("SELECT MAX(day) FROM daily").fetchone()[0]
        last = conn.execute("SELECT MAX(ts) FROM sync_log WHERE status='ok'").fetchone()[0]
    except sqlite3.OperationalError:
        through = last = None
    return {"data_through": through, "last_successful_sync": last,
            "sources": "local database: Garmin Personal API > unofficial Garmin Connect > "
                       "Garmin data export",
            "convention": "garmin_* = Garmin's own values; other numbers are computed by this "
                          "connector (formulas in METRICS.md)"}


def _with_db(fn: Callable[[sqlite3.Connection], Any]) -> Any:
    conn = db.connect(db_path())
    try:
        result = fn(conn)
        if isinstance(result, dict) and "error" not in result:
            result.setdefault("provenance", _provenance(conn))
        return result
    finally:
        conn.close()


@mcp.tool()
def health_snapshot(day: str | None = None) -> dict[str, Any]:
    """Full health picture for a day (default: latest): sleep, HRV, resting HR vs baselines,
    Garmin training readiness and status, load, VO2max, race predictions, everyday activity,
    fitness age, last 7 days of activities, and flags worth attention."""
    return _with_db(lambda c: insights.health_snapshot(c, parse_date(day) if day else None))


@mcp.tool()
def daily_summary(day: str | None = None) -> dict[str, Any]:
    """Every stored metric for one day (YYYY-MM-DD, default today): daily totals, sleep, HRV,
    health status, readiness, training status, race predictions, scores, activities."""
    return _with_db(lambda c: insights.day_view(c, parse_date(day)))


@mcp.tool()
def activities(days: int = 30, activity_type: str | None = None,
               end: str | None = None) -> dict[str, Any]:
    """Activities in the last `days` days (1-3650), newest first, with a per-type summary.
    activity_type filters by substring, e.g. 'running', 'swim', 'strength'."""
    days = max(1, min(days, 3650))
    return _with_db(lambda c: insights.recent_activities(
        c, days=days, end=parse_date(end) if end else None, activity_type=activity_type))


@mcp.tool()
def activity_detail(activity_id: int) -> dict[str, Any]:
    """One activity: summary, Garmin training effect/load, laps with pace, HR zones, weather,
    and running form from the FIT file (cadence, ground contact, vertical oscillation, power)."""
    result = _with_db(lambda c: insights.activity_detail(c, activity_id))
    return result or {"error": f"activity {activity_id} not found"}


@mcp.tool()
def trend(metric: str, days: int = 30, end: str | None = None) -> dict[str, Any]:
    """Time series for one metric as 'table.column' (e.g. 'daily.resting_hr', 'sleep.sleep_s',
    'health_status.hrv', 'readiness.score', 'training.vo2max_run', 'race_predictions.t5k_s').
    Returns points, average, min/max and first-half vs second-half averages. An unknown metric
    returns the list of valid ones."""
    days = max(2, min(days, 3650))
    return _with_db(lambda c: insights.trend(c, metric, days, parse_date(end) if end else None))


@mcp.tool()
def readiness_today(day: str | None = None) -> dict[str, Any]:
    """Our transparent readiness vs your own baselines (HRV 7-day vs normal band, resting HR,
    sleep, respiration as z-scores, each shown) next to Garmin's Training Readiness; HRV
    status with normal band and CV; sleep debt and bedtime consistency; illness/strain flag."""
    from garmin_mcp import recovery

    return _with_db(lambda c: recovery.readiness(
        c, parse_date(day) if day else insights._latest_day(c) or parse_date(None)))


@mcp.tool()
def recovery_trend(days: int = 28, end: str | None = None) -> dict[str, Any]:
    """Day-by-day readiness, HRV 7-day value vs normal band, sleep and Garmin readiness for the
    last `days` days (7-120)."""
    from garmin_mcp import recovery

    days = max(7, min(days, 120))
    return _with_db(lambda c: recovery.recovery_trend(
        c, parse_date(end) if end else insights._latest_day(c) or parse_date(None), days))


@mcp.tool()
def daily_brief(day: str | None = None) -> dict[str, Any]:
    """Morning report: how recovered you are and why, a training suggestion with its reason,
    yesterday's activities, the week so far and flags. Narrate it in 2-4 sentences."""
    return _with_db(lambda c: insights.daily_brief(c, parse_date(day) if day else None))


@mcp.tool()
def training_load(days: int = 42, end: str | None = None) -> dict[str, Any]:
    """Fitness (CTL), fatigue (ATL), form (TSB), ramp rate, monotony and strain from TRIMP,
    plus current thresholds (HRmax, resting HR, LTHR) with Garmin's values beside them."""
    from garmin_mcp import loads

    def run(c: sqlite3.Connection) -> dict[str, Any]:
        e = parse_date(end) if end else insights._latest_day(c) or parse_date(None)
        lo = (date.fromisoformat(e) - timedelta(days=max(7, min(days, 730)) - 1)).isoformat()
        series = [dict(zip(("day", "load", "ctl", "atl", "tsb", "ramp", "monotony", "strain"), r))
                  for r in c.execute("SELECT * FROM fitness WHERE day BETWEEN ? AND ? ORDER BY day",
                                     (lo, e))]
        return {"today": series[-1] if series else None, "series": series,
                "thresholds": loads.thresholds(c, e),
                "meaning": "CTL = long-term load (fitness), ATL = 7-day load (fatigue), "
                           "TSB = CTL - ATL (form, yesterday's values). Units: Banister TRIMP. "
                           "TSB bands are heuristics, not validated thresholds."}

    return _with_db(run)


@mcp.tool()
def performance(days: int = 90, end: str | None = None) -> dict[str, Any]:
    """Running performance: pace-duration curve, critical speed, effective VO2max, and race
    predictions from several methods beside Garmin's, with notes on reliability."""
    from garmin_mcp import loads

    def run(c: sqlite3.Connection) -> dict[str, Any]:
        e = parse_date(end) if end else insights._latest_day(c) or parse_date(None)
        d = max(30, min(days, 730))
        return {"race_predictions": loads.race_predictions(c, e, d),
                "pace_curve": loads.pace_curve(c, e, d)["curve"]}

    return _with_db(run)


@mcp.tool()
def weekly_review(end: str | None = None) -> dict[str, Any]:
    """Last 7 days vs the previous 4 weeks: sessions, hours, run km, load, intensity balance,
    fitness/form, longest run, sleep and readiness. Narrate as a weekly recap."""
    return _with_db(lambda c: insights.weekly_review(c, parse_date(end) if end else None))


@mcp.tool()
def sense_checks(end: str | None = None) -> dict[str, Any]:
    """Self-checks of our calculations against Garmin's values and physics (load correlation,
    VO2max, cadence x stride = speed, HR-zone times, thresholds). Run when numbers look odd."""
    from garmin_mcp import loads

    return _with_db(lambda c: loads.sense_checks(
        c, parse_date(end) if end else insights._latest_day(c) or parse_date(None)))


# ----------------------------------------------------------------- Phase 5: coaching
@mcp.tool()
def run_analysis(activity_id: int) -> dict[str, Any]:
    """Deep dive into one run: pacing and km splits, efficiency factor, aerobic decoupling, HR
    drift, running form (cadence, step length, ground contact, vertical oscillation/ratio,
    power) compared with YOUR norm at the same pace, similar past runs, personal heat effect,
    Garmin training effect, and facts for an activity recap."""
    from garmin_mcp import coaching

    return _with_db(lambda c: coaching.run_analysis(c, activity_id))


@mcp.tool()
def running_form_trends(days: int = 365, end: str | None = None) -> dict[str, Any]:
    """Monthly running-form and efficiency trends within your usual pace band (so changes
    reflect form, not speed), plus efficiency/decoupling of steady runs."""
    from garmin_mcp import coaching

    return _with_db(lambda c: coaching.running_form_trends(
        c, parse_date(end) if end else insights._latest_day(c) or parse_date(None),
        max(60, min(days, 1100))))


@mcp.tool()
def activity_stream(activity_id: int, every_s: int = 10) -> dict[str, Any]:
    """Downsampled time series of one activity (HR, pace, cadence, altitude, power, distance)."""
    from garmin_mcp import coaching

    return _with_db(lambda c: coaching.activity_stream(c, activity_id, max(1, min(every_s, 120))))


@mcp.tool()
def sport_trends(sport: str = "swim", days: int = 365, end: str | None = None) -> dict[str, Any]:
    """Trends for 'swim' (pace/100 m, SWOLF by stroke) or 'strength' (sessions, sets, reps)."""
    from garmin_mcp import coaching

    def run(c: sqlite3.Connection) -> dict[str, Any]:
        e = parse_date(end) if end else insights._latest_day(c) or parse_date(None)
        fn = coaching.strength_trends if sport.startswith("str") else coaching.swim_trends
        return fn(c, e, max(30, min(days, 1100)))

    return _with_db(run)


@mcp.tool()
def metric_glossary(metric: str | None = None) -> dict[str, Any]:
    """What a metric means, its typical range, unit and how to improve it. No argument lists all."""
    from garmin_mcp.coaching import GLOSSARY

    if metric:
        key = metric.lower().replace(" ", "_")
        return GLOSSARY.get(key) or {"error": f"unknown metric {metric!r}",
                                     "available": sorted(GLOSSARY)}
    return GLOSSARY


@mcp.tool()
def fitness_age() -> dict[str, Any]:
    """Garmin fitness age vs your age, and the levers Garmin reports (vigorous days/minutes,
    resting HR, BMI) with targets and the fitness age you would reach."""
    from garmin_mcp import coaching

    return _with_db(coaching.fitness_age)


# ----------------------------------------------------------------- Phase 6: athlete context
@mcp.tool()
def athlete_context() -> dict[str, Any]:
    """Profile, your saved settings and goals, recent notes, and OPEN QUESTIONS (inputs not yet
    provided, e.g. tested max HR, goal race). Read before giving personalised advice."""
    from garmin_mcp import athlete

    return _with_db(athlete.context)


@mcp.tool()
def update_athlete_setting(key: str, value: str, note: str | None = None) -> dict[str, Any]:
    """Save a setting the user stated, e.g. hr_max_override=198, goal_race='{"distance_km":10,
    "date":"2027-03-01","target":"50:00"}', timezone='Asia/Kolkata'. Overrides apply to all
    calculations after the next refresh_data/rebuild. Only save what the user said."""
    import json as _json

    from garmin_mcp import athlete
    from garmin_mcp.normalize import rebuild

    if key not in athlete.PLACEHOLDERS:
        return {"error": f"unknown key {key!r}", "allowed": sorted(athlete.PLACEHOLDERS)}
    try:
        parsed: Any = _json.loads(value)
    except ValueError:
        parsed = value

    def run(c: sqlite3.Connection) -> dict[str, Any]:
        athlete.set_value(c, key, parsed, note)
        rebuild(c)
        return {"saved": {key: parsed}, "recalculated": True}

    return _with_db(run)


@mcp.tool()
def add_athlete_note(text: str, kind: str = "note") -> dict[str, Any]:
    """Store a coaching note, decision or preference the user stated (kind: note, decision,
    preference, injury)."""
    from garmin_mcp import athlete

    return _with_db(lambda c: (athlete.add_note(c, kind, text), {"saved": True})[1])


@mcp.tool()
def goal_check() -> dict[str, Any]:
    """Reality check of the saved goal race against current fitness: required pace vs predicted
    times (several methods + Garmin), weeks available and volume. Asks for the goal if unset."""
    from garmin_mcp import goals

    return _with_db(goals.goal_check)


# ----------------------------------------------------------------- Phase 7: workouts
@mcp.tool()
def workout_templates() -> dict[str, Any]:
    """Ready-made workout specs (easy, tempo, VO2 intervals, calibration test) using your HR
    thresholds. Pass one (edited as needed) to create_workout."""
    from garmin_mcp import workouts

    return _with_db(workouts.templates)


@mcp.tool()
def create_workout(spec: str, upload: bool = False,
                   schedule_date: str | None = None) -> dict[str, Any]:
    """Build a structured running workout from a JSON spec, validate it (paces 2:30-12:00/km,
    HR below your max) and return Garmin's workout JSON. With upload=true it is sent to Garmin
    Connect (unofficial login, Mac only) and optionally scheduled (YYYY-MM-DD); sync the watch to
    receive it. Spec: {"name":..., "steps":[{"type":"warmup|interval|recovery|cooldown",
    "duration":"m:ss" or "distance_m":800, "pace":"5:00-5:10" | "hr":"150-160" | "hr_zone":2},
    {"type":"repeat","times":5,"steps":[...]}]}. Only upload when the user asks."""
    import json as _json

    from garmin_mcp import workouts

    try:
        parsed = _json.loads(spec)
    except ValueError as exc:
        return {"error": f"spec is not valid JSON: {exc}"}
    return _with_db(lambda c: workouts.create(c, parsed, upload, schedule_date))


@mcp.tool()
def garmin_workouts(action: str = "list", workout_id: int | None = None) -> dict[str, Any]:
    """List workouts saved in Garmin Connect, or delete one (action='delete', workout_id).
    Needs the unofficial login (Mac). Only delete when the user asks."""
    from garmin_mcp import workouts

    if action == "delete":
        if not workout_id:
            return {"error": "workout_id required"}
        return workouts.delete_on_garmin(workout_id)
    return workouts.list_on_garmin()


# ----------------------------------------------------------------- Phase 8: insight engine
def _end(c: sqlite3.Connection, end: str | None) -> str:
    return parse_date(end) if end else insights._latest_day(c) or parse_date(None)


@mcp.tool()
def insight_feed(end: str | None = None) -> dict[str, Any]:
    """Ranked insights (level 1 what happened, level 2 associations in your data, level 3 what
    to do): readiness, HRV-guided advice, vitals outside range, load flags, 90-day trends,
    notable relationships. Start here for 'what should I know?'."""
    from garmin_mcp import engine

    return _with_db(lambda c: engine.insight_feed(c, _end(c, end)))


@mcp.tool()
def relationships(days: int = 365, end: str | None = None) -> dict[str, Any]:
    """Associations in your own data (e.g. sleep -> next-day HRV, stress -> HRV, bedtime ->
    sleep, training load -> next-day resting HR), baseline-adjusted with bootstrap CIs and
    false-discovery control. Association, not causation."""
    from garmin_mcp import engine

    return _with_db(lambda c: engine.relationships(c, _end(c, end), max(90, min(days, 1100))))


@mcp.tool()
def trends_and_patterns(days: int = 90, end: str | None = None) -> dict[str, Any]:
    """Robust trends (HRV, resting HR, sleep, VO2max, fitness, steps) with confidence intervals,
    weekday patterns, streaks, personal ranges and form as % of fitness."""
    from garmin_mcp import engine

    def run(c: sqlite3.Connection) -> dict[str, Any]:
        e = _end(c, end)
        return {"trends": engine.trends(c, e, max(30, min(days, 730))),
                "weekday_patterns": engine.weekday_patterns(c, e),
                "streaks": engine.streaks(c, e), "personal_ranges": engine.personal_ranges(c, e),
                "form": engine.form_percent(c, e), "load_flags": engine.load_flags(c, e)}

    return _with_db(run)


@mcp.tool()
def records_and_calendar(days: int = 365, end: str | None = None) -> dict[str, Any]:
    """Personal-best timeline (pace curve), longest sessions per sport, and a per-day calendar
    of sleep, HRV, resting HR, load, steps and readiness for heatmaps."""
    from garmin_mcp import engine

    return _with_db(lambda c: {"records": engine.records(c),
                               "calendar": engine.calendar(c, _end(c, end),
                                                           max(30, min(days, 1100)))})


@mcp.tool()
def add_tag(day: str, tag: str) -> dict[str, Any]:
    """Tag a day with a behaviour or context (alcohol, late meal, travel, illness, late
    caffeine, sick, injured). Used for Whoop-style impact estimates on next-day HRV/sleep."""
    from garmin_mcp import athlete

    d = parse_date(day)
    return _with_db(lambda c: (athlete.add_note(c, "tag", f"{d}|{tag.strip().lower()}"),
                               {"tagged": d, "tag": tag})[1])


@mcp.tool()
def tag_impact(days: int = 365) -> dict[str, Any]:
    """How tagged days relate to next-day HRV, sleep score and resting HR vs your baseline."""
    from garmin_mcp import engine

    return _with_db(lambda c: engine.tag_impact(c, _end(c, None), max(30, min(days, 1100))))


# ----------------------------------------------------------------- Phase 9: dashboard
@mcp.tool()
def build_dashboard() -> dict[str, Any]:
    """Rebuild the personal dashboard (one HTML file, opens in any browser or phone). It is also
    rebuilt automatically after every sync. Returns the file path."""
    from garmin_mcp import dashboard

    return _with_db(lambda c: {"path": str(dashboard.build(c)),
                               "open_with": "open <path> (Mac) or any browser"})


@mcp.tool()
def refresh_data(days: int = 3) -> dict[str, Any]:
    """Sync the last `days` days (1-30) from Garmin into the local database, then rebuild the
    tidy tables. Use when data looks stale."""
    from garmin_mcp.sync import run_sync

    return run_sync(days=max(1, min(days, 30)))


@mcp.tool()
def data_coverage() -> dict[str, Any]:
    """What is stored locally: date range per dataset, activity counts, last sync and errors."""
    return _with_db(db.coverage)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
