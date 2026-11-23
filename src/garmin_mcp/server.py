"""MCP server. Every tool reads the local database; only `refresh_data` talks to Garmin."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
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
