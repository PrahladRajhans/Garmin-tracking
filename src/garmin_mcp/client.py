"""Lazily-authenticated wrapper around the unofficial `garminconnect` library.

`Garmin.login(tokenstore)` resumes a saved session from the token directory, and
only falls back to email/password (then saves fresh tokens) when needed.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from garminconnect import Garmin

DEFAULT_TOKEN_DIR = Path.home() / ".garminconnect"

_client: Garmin | None = None


def token_dir() -> Path:
    return Path(os.getenv("GARMIN_TOKEN_DIR", str(DEFAULT_TOKEN_DIR))).expanduser()


def get_client() -> Garmin:
    """Return a cached, authenticated Garmin client."""
    global _client
    if _client is None:
        client = Garmin(os.getenv("GARMIN_EMAIL"), os.getenv("GARMIN_PASSWORD"))
        client.login(str(token_dir()))
        _client = client
    return _client


def parse_date(value: str | None) -> str:
    """Validate a YYYY-MM-DD string; default to today."""
    if not value:
        return date.today().isoformat()
    return date.fromisoformat(value).isoformat()
