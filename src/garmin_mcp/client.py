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


def _saved_timezone() -> str | None:
    """Timezone saved via update_athlete_setting('timezone', ...), if any."""
    try:
        import json
        import sqlite3

        from garmin_mcp.config import db_path

        path = db_path()
        if not path.exists():
            return None
        conn = sqlite3.connect(str(path))
        try:
            row = conn.execute("SELECT value FROM athlete_settings WHERE key='timezone'").fetchone()
        finally:
            conn.close()
        return json.loads(row[0]) if row and row[0] else None
    except Exception:  # noqa: BLE001 - table may not exist yet
        return None


def today() -> date:
    """Today in GARMIN_TZ (IANA name, e.g. Asia/Kolkata) if set, else the computer's local date."""
    tz = os.getenv("GARMIN_TZ") or _saved_timezone()
    if tz:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(tz)).date()
    return date.today()


def parse_date(value: str | None) -> str:
    """Validate a YYYY-MM-DD string; default to today."""
    if not value:
        return today().isoformat()
    return date.fromisoformat(value).isoformat()
