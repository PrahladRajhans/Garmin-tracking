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


def _with_db(fn: Callable[[sqlite3.Connection], Any]) -> Any:
    conn = db.connect(db_path())
    try:
        return fn(conn)
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
