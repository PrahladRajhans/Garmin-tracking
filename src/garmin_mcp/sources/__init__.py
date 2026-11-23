"""Data sources. Each exposes the same small interface so the sync engine stays source-agnostic."""

from garmin_mcp.sources.base import DataSource

__all__ = ["DataSource"]
