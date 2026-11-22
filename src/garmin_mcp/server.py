"""MCP server exposing Garmin Connect data as tools."""

from __future__ import annotations

from typing import Any

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

from garmin_mcp.client import get_client, parse_date

load_dotenv()

mcp = MCPServer("garmin")


@mcp.tool()
def get_daily_summary(day: str | None = None) -> dict[str, Any]:
    """Daily stats (steps, calories, resting HR, stress, body battery). day = YYYY-MM-DD, default today."""
    return get_client().get_stats(parse_date(day))


@mcp.tool()
def get_sleep(day: str | None = None) -> dict[str, Any]:
    """Sleep data for the night ending on `day` (YYYY-MM-DD, default today)."""
    return get_client().get_sleep_data(parse_date(day))


@mcp.tool()
def get_heart_rate(day: str | None = None) -> dict[str, Any]:
    """Heart-rate timeline and resting HR for `day` (YYYY-MM-DD, default today)."""
    return get_client().get_heart_rates(parse_date(day))


@mcp.tool()
def get_recent_activities(limit: int = 10) -> list[dict[str, Any]]:
    """Most recent activities (newest first). limit: 1-100."""
    limit = max(1, min(limit, 100))
    return get_client().get_activities(0, limit)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
