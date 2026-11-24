"""Paths and settings, all overridable with environment variables."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_NARRATOR_MODEL = "qwen3.5:4b"


def data_dir() -> Path:
    path = Path(os.getenv("GARMIN_DATA_DIR", str(Path.home() / ".garmin-mcp"))).expanduser()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    path = os.getenv("GARMIN_DB_PATH")
    return Path(path).expanduser() if path else data_dir() / "garmin.db"


def fit_dir() -> Path:
    path = data_dir() / "fit"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path
