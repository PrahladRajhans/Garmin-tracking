"""Athlete context (ROADMAP 6.1): settings, goals, preferences and coaching notes.

Inputs the user has not supplied yet are explicit placeholders (value None, with a question),
so tools can say exactly what is missing instead of guessing. Settings override derived values
(e.g. a tested max HR replaces the observed one) and every override is reported.
"""

from __future__ import annotations

import json
import math
import sqlite3
from typing import Any

from garmin_mcp.db import now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS athlete_settings (
    key TEXT PRIMARY KEY, value TEXT, updated_at TEXT NOT NULL, note TEXT
);
CREATE TABLE IF NOT EXISTS athlete_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL
);
"""

# key -> (question for the user, type, how it is used)
PLACEHOLDERS: dict[str, tuple[str, str, str]] = {
    "hr_max_override": (("Have you tested a max heart rate, or seen one above the highest your "
                        "watch recorded?"), "bpm",
                        "replaces observed HRmax in TRIMP, zones and effective VO2max"),
    "lthr_override": ("Do you know your lactate-threshold heart rate from a test?", "bpm",
                      "replaces the 20-min estimate for zones and readiness"),
    "threshold_pace_override": ("Do you know your threshold pace (about 1-hour race pace)?",
                                "min/km as 'm:ss'", ("enables rTSS when critical speed is "
                                "unreliable")),
    "goal_race": ("Target race? (distance, date, target time)", "json",
                  "goal reality check, weekly review focus"),
    "weekly_run_km_target": ("Weekly running volume you aim for?", "km", "volume tracking"),
    "goals": ("Main goals (e.g. sub-25 5K, better sleep, fitness age)?", "text",
              "framing for briefs and recaps"),
    "preferred_long_run_day": ("Preferred long-run day?", "weekday", "weekly review"),
    "timezone": ("Your timezone (IANA, e.g. Asia/Kolkata)?", "IANA name",
                 "defines 'today'; default: the computer's local time"),
    "injuries_or_limits": ("Any injuries or limits to respect?", "text",
                           "workout suggestions"),
}


def ensure(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def get(conn: sqlite3.Connection, key: str, *, ensure_schema: bool = True) -> Any:
    if ensure_schema:
        ensure(conn)
    elif not _has(conn, "athlete_settings"):
        return None
    row = conn.execute("SELECT value FROM athlete_settings WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row and row[0] is not None else None


def set_value(conn: sqlite3.Connection, key: str, value: Any, note: str | None = None) -> None:
    ensure(conn)
    conn.execute("INSERT OR REPLACE INTO athlete_settings VALUES (?,?,?,?)",
                 (key, json.dumps(value), now_iso(), note))
    conn.commit()


def add_note(conn: sqlite3.Connection, kind: str, text: str) -> None:
    ensure(conn)
    conn.execute("INSERT INTO athlete_notes(ts, kind, text) VALUES (?,?,?)",
                 (now_iso(), kind, text))
    conn.commit()


def context(conn: sqlite3.Connection) -> dict[str, Any]:
    """Everything known about the athlete, and the open questions (placeholders)."""
    ensure(conn)
    settings = {k: json.loads(v) for k, v in conn.execute(
        "SELECT key, value FROM athlete_settings") if v is not None}
    missing = [{"key": k, "question": q, "unit": u, "used_for": use}
               for k, (q, u, use) in PLACEHOLDERS.items() if settings.get(k) is None]
    notes = [dict(zip(("ts", "kind", "text"), r)) for r in conn.execute(
        "SELECT ts, kind, text FROM athlete_notes ORDER BY id DESC LIMIT 20")]
    prof = conn.execute("SELECT gender, weight_kg, height_m FROM fit_profile ORDER BY "
                        "activity_id DESC LIMIT 1").fetchone()
    fa = conn.execute("SELECT chronological_age FROM fitness_age WHERE chronological_age IS NOT "
                      "NULL ORDER BY day DESC LIMIT 1").fetchone() if _has(conn, "fitness_age") \
        else None
    return {
        "profile": {"sex": prof[0] if prof else None, "weight_kg": prof[1] if prof else None,
                    "height_m": prof[2] if prof else None, "age": fa[0] if fa else None,
                    "source": "watch profile (FIT) and Garmin fitness age"},
        "settings": settings,
        "open_questions": missing,
        "recent_notes": notes,
    }


def _has(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone() is not None


def pace_to_speed(pace: str) -> float | None:
    """'5:30' min/km -> m/s."""
    try:
        m, s = pace.split(":")
        minutes, seconds = int(m), int(s)
        if minutes < 0 or not 0 <= seconds < 60 or minutes * 60 + seconds <= 0:
            return None
        return 1000 / (minutes * 60 + seconds)
    except (ValueError, AttributeError):
        return None


def validate_setting(key: str, value: Any) -> str | None:
    """Reject malformed overrides without inventing physiological reference ranges."""
    if value is None:
        return None
    if key in {"hr_max_override", "lthr_override", "weekly_run_km_target"}:
        try:
            number = float(value)
            if (isinstance(value, bool) or not math.isfinite(number) or number < 0
                    or (number == 0 and key != "weekly_run_km_target")):
                return "setting must be finite and positive (weekly km may be zero)"
        except (TypeError, ValueError, OverflowError):
            return "setting must be a number"
    if key == "threshold_pace_override" and pace_to_speed(value) is None:
        return "pace must be a positive m:ss value with seconds below 60"
    if key == "goal_race":
        from garmin_mcp.goals import parse_goal

        try:
            parse_goal(value)
        except (TypeError, ValueError) as error:
            return str(error)
    if key == "timezone":
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except (ValueError, TypeError, ZoneInfoNotFoundError):
            return "timezone must be a valid IANA name, such as Asia/Kolkata"
    return None


def seed_from_file(conn: sqlite3.Connection, path: str | None = None) -> list[str]:
    """Apply settings from config/athlete.json (in the private repo) for keys not yet set in
    this machine's database, so every machine gets them without manual steps. Settings you
    change later via update_athlete_setting are never overwritten."""
    from pathlib import Path

    p = Path(path) if path else Path(__file__).resolve().parents[2] / "config" / "athlete.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    ensure(conn)
    applied = []
    for key, value in data.items():
        if (key in PLACEHOLDERS and value is not None and not validate_setting(key, value)
                and get(conn, key) is None):
            set_value(conn, key, value, "seeded from config/athlete.json")
            applied.append(key)
    return applied
