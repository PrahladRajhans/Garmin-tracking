"""Paths and settings, all overridable with environment variables."""

from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    path = Path(os.getenv("GARMIN_DATA_DIR", str(Path.home() / ".garmin-mcp"))).expanduser()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return Path(os.getenv("GARMIN_DB_PATH", str(data_dir() / "garmin.db"))).expanduser()


def fit_dir() -> Path:
    path = data_dir() / "fit"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path
