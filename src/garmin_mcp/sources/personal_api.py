"""Official Garmin Personal API source (placeholder).

Garmin reportedly opened free personal API keys around Oct 2026 (key -> 24 h access token,
pull-only, activities + FIT + health). The endpoint list and payload shapes are NOT yet
verified, so this source is intentionally unimplemented rather than guessed. Fill it in once a
key is issued (ROADMAP Phase 0.1).
"""

from __future__ import annotations

from garmin_mcp.sources.base import DataSource


class PersonalAPISource(DataSource):
    name = "personal_api"

    def __init__(self, api_key: str) -> None:
        super().__init__()
        self.api_key = api_key
        raise NotImplementedError(
            "Personal API source is pending: endpoints are unverified until a key is issued. "
            "Use the garminconnect source for now."
        )
