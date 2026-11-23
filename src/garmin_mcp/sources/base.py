"""Source interface."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

DailyFetcher = Callable[[str], Any]
RangeFetcher = Callable[[str, str], Any]


class DataSource:
    """Base class. Subclasses fill the dataset maps and activity methods.

    - ``daily``: dataset name -> fn(day) for data keyed by calendar day.
    - ``ranges``: dataset name -> fn(start, end) for slow-moving metrics fetched as a window.
    - ``activity_details``: kind -> fn(activity_id) for extra per-activity payloads.
    """

    name = "base"
    #: Split windowed fetches into chunks of this many days (None = one call).
    range_chunk_days: int | None = None

    def __init__(self) -> None:
        self.daily: dict[str, DailyFetcher] = {}
        self.ranges: dict[str, RangeFetcher] = {}
        self.activity_details: dict[str, Callable[[int], Any]] = {}

    def list_activities(self, start: str, end: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def download_fit(self, activity_id: int) -> bytes | None:
        """Return raw .fit bytes, or None if unavailable."""
        return None
