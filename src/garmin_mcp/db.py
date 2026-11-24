"""SQLite storage.

Raw-first storage retains fetched payloads and superseded revisions. Derived tables can be
rebuilt without downloading the same readings again.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS coach_insight_memory (
    day TEXT PRIMARY KEY, evidence TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS coach_checkin (
    day TEXT PRIMARY KEY, rested INTEGER, energy INTEGER, soreness INTEGER, knee INTEGER
);
CREATE TABLE IF NOT EXISTS coach_session (
    id INTEGER PRIMARY KEY, day TEXT NOT NULL, kind TEXT NOT NULL, minutes INTEGER NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_daily (
    dataset TEXT NOT NULL, day TEXT NOT NULL, source TEXT NOT NULL,
    payload TEXT, fetched_at TEXT NOT NULL,
    PRIMARY KEY (dataset, day)
);

CREATE TABLE IF NOT EXISTS raw_range (
    dataset TEXT NOT NULL, start_day TEXT NOT NULL, end_day TEXT NOT NULL, source TEXT NOT NULL,
    payload TEXT, fetched_at TEXT NOT NULL,
    PRIMARY KEY (dataset, start_day, end_day)
);

CREATE TABLE IF NOT EXISTS activities (
    activity_id INTEGER PRIMARY KEY,
    name TEXT, type TEXT, start_time_local TEXT, start_time_gmt TEXT,
    duration_s REAL, distance_m REAL, avg_hr REAL, max_hr REAL, calories REAL,
    elevation_gain_m REAL, garmin_training_load REAL,
    aerobic_te REAL, anaerobic_te REAL, vo2max REAL,
    summary TEXT, details_fetched INTEGER NOT NULL DEFAULT 0,
    fit_path TEXT, fit_parsed INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activities_start ON activities(start_time_local);

CREATE TABLE IF NOT EXISTS activity_details (
    activity_id INTEGER NOT NULL, kind TEXT NOT NULL, payload TEXT, fetched_at TEXT NOT NULL,
    PRIMARY KEY (activity_id, kind)
);

CREATE TABLE IF NOT EXISTS raw_payload_history (
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, dataset TEXT NOT NULL,
    record_key TEXT NOT NULL, source TEXT, fetched_at TEXT NOT NULL, payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_raw_payload_history_key ON raw_payload_history(kind, dataset, record_key);

CREATE TRIGGER IF NOT EXISTS retain_daily_payload BEFORE UPDATE ON raw_daily
WHEN OLD.payload IS NOT NEW.payload OR OLD.source IS NOT NEW.source
BEGIN
    INSERT INTO raw_payload_history(kind, dataset, record_key, source, fetched_at, payload)
    VALUES ('daily', OLD.dataset, OLD.day, OLD.source, OLD.fetched_at, OLD.payload);
END;
CREATE TRIGGER IF NOT EXISTS retain_range_payload BEFORE UPDATE ON raw_range
WHEN OLD.payload IS NOT NEW.payload OR OLD.source IS NOT NEW.source
BEGIN
    INSERT INTO raw_payload_history(kind, dataset, record_key, source, fetched_at, payload)
    VALUES ('range', OLD.dataset, OLD.start_day || '..' || OLD.end_day,
            OLD.source, OLD.fetched_at, OLD.payload);
END;
CREATE TRIGGER IF NOT EXISTS retain_activity_detail BEFORE UPDATE ON activity_details
WHEN OLD.payload IS NOT NEW.payload
BEGIN
    INSERT INTO raw_payload_history(kind, dataset, record_key, fetched_at, payload)
    VALUES ('detail', OLD.kind, OLD.activity_id, OLD.fetched_at, OLD.payload);
END;
CREATE TRIGGER IF NOT EXISTS retain_activity_summary BEFORE UPDATE OF summary ON activities
WHEN OLD.summary IS NOT NULL AND OLD.summary IS NOT NEW.summary
BEGIN
    INSERT INTO raw_payload_history(kind, dataset, record_key, fetched_at, payload)
    VALUES ('summary', 'activities', OLD.activity_id, OLD.updated_at, OLD.summary);
END;

CREATE TABLE IF NOT EXISTS fit_sessions (
    activity_id INTEGER PRIMARY KEY, sport TEXT, sub_sport TEXT, payload TEXT
);

CREATE TABLE IF NOT EXISTS fit_laps (
    activity_id INTEGER NOT NULL, lap_index INTEGER NOT NULL, start_time TEXT,
    timer_s REAL, distance_m REAL, avg_hr REAL, max_hr REAL, avg_speed REAL,
    avg_cadence REAL, avg_power REAL, payload TEXT,
    PRIMARY KEY (activity_id, lap_index)
);

CREATE TABLE IF NOT EXISTS fit_records (
    activity_id INTEGER NOT NULL, ts TEXT NOT NULL,
    heart_rate REAL, speed REAL, cadence REAL, power REAL, altitude REAL,
    distance REAL, lat REAL, lon REAL, temperature REAL,
    vertical_oscillation REAL, stance_time REAL, step_length REAL, extra TEXT
);
CREATE INDEX IF NOT EXISTS idx_fit_records_activity ON fit_records(activity_id, ts);

CREATE TABLE IF NOT EXISTS fit_hrv (
    activity_id INTEGER NOT NULL, seq INTEGER NOT NULL, rr_s REAL NOT NULL,
    PRIMARY KEY (activity_id, seq)
);

CREATE TABLE IF NOT EXISTS fit_lengths (
    activity_id INTEGER NOT NULL, seq INTEGER NOT NULL, length_type TEXT, stroke TEXT,
    time_s REAL, strokes REAL, cadence REAL,
    PRIMARY KEY (activity_id, seq)
);

CREATE TABLE IF NOT EXISTS fit_sets (
    activity_id INTEGER NOT NULL, seq INTEGER NOT NULL, set_type TEXT, category TEXT,
    repetitions REAL, weight_kg REAL, duration_s REAL,
    PRIMARY KEY (activity_id, seq)
);

-- Garmin's own per-activity time in HR/power zones and the thresholds it used.
CREATE TABLE IF NOT EXISTS fit_zones (
    activity_id INTEGER PRIMARY KEY, hr_zone_s TEXT, hr_zone_bounds TEXT, power_zone_s TEXT,
    hr_calc_type TEXT, max_hr REAL, resting_hr REAL, threshold_hr REAL
);

-- Watch profile at the time of the activity (sex, weight, resting HR setting).
CREATE TABLE IF NOT EXISTS fit_profile (
    activity_id INTEGER PRIMARY KEY, gender TEXT, weight_kg REAL, height_m REAL,
    resting_hr REAL
);

CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL, ts TEXT NOT NULL, source TEXT, dataset TEXT, key TEXT,
    status TEXT NOT NULL, error TEXT
);
"""


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def connect(path: Path | str) -> sqlite3.Connection:
    if str(path) != ":memory:" and not Path(path).exists():
        Path(path).touch(mode=0o600, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),)
    )
    conn.commit()
    return conn


def dumps(payload: Any) -> str:
    return json.dumps(payload, default=str, separators=(",", ":"))


def has_daily(conn: sqlite3.Connection, dataset: str, day: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM raw_daily WHERE dataset=? AND day=?", (dataset, day)
    ).fetchone()
    return row is not None


def put_daily(conn: sqlite3.Connection, dataset: str, day: str, source: str, payload: Any) -> None:
    conn.execute(
        "INSERT INTO raw_daily(dataset, day, source, payload, fetched_at) VALUES (?,?,?,?,?) "
        "ON CONFLICT(dataset,day) DO UPDATE SET source=excluded.source, payload=excluded.payload, "
        "fetched_at=excluded.fetched_at",
        (dataset, day, source, dumps(payload), now_iso()),
    )


def put_range(
    conn: sqlite3.Connection, dataset: str, start: str, end: str, source: str, payload: Any
) -> None:
    conn.execute(
        "INSERT INTO raw_range(dataset, start_day, end_day, source, payload, fetched_at) "
        "VALUES (?,?,?,?,?,?) ON CONFLICT(dataset,start_day,end_day) "
        "DO UPDATE SET source=excluded.source, payload=excluded.payload, fetched_at=excluded.fetched_at",
        (dataset, start, end, source, dumps(payload), now_iso()),
    )


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def upsert_activity(conn: sqlite3.Connection, summary: dict[str, Any]) -> int:
    """Insert/update an activity from a Garmin activity-list item. Returns the activity id."""
    activity_id = int(summary["activityId"])
    activity_type = summary.get("activityType") or {}
    values = {
        "activity_id": activity_id,
        "name": summary.get("activityName"),
        "type": activity_type.get("typeKey") if isinstance(activity_type, dict) else None,
        "start_time_local": summary.get("startTimeLocal"),
        "start_time_gmt": summary.get("startTimeGMT"),
        "duration_s": _num(summary.get("duration")),
        "distance_m": _num(summary.get("distance")),
        "avg_hr": _num(summary.get("averageHR")),
        "max_hr": _num(summary.get("maxHR")),
        "calories": _num(summary.get("calories")),
        "elevation_gain_m": _num(summary.get("elevationGain")),
        "garmin_training_load": _num(summary.get("activityTrainingLoad")),
        "aerobic_te": _num(summary.get("aerobicTrainingEffect")),
        "anaerobic_te": _num(summary.get("anaerobicTrainingEffect")),
        "vo2max": _num(summary.get("vO2MaxValue")),
        "summary": dumps(summary),
        "updated_at": now_iso(),
    }
    cols = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    updates = ", ".join(f"{c}=excluded.{c}" for c in values if c != "activity_id")
    conn.execute(
        f"INSERT INTO activities({cols}) VALUES ({marks}) "
        f"ON CONFLICT(activity_id) DO UPDATE SET {updates}",
        tuple(values.values()),
    )
    return activity_id


def put_activity_detail(
    conn: sqlite3.Connection, activity_id: int, kind: str, payload: Any
) -> None:
    conn.execute(
        "INSERT INTO activity_details(activity_id, kind, payload, fetched_at) VALUES (?,?,?,?) "
        "ON CONFLICT(activity_id,kind) DO UPDATE SET payload=excluded.payload, fetched_at=excluded.fetched_at",
        (activity_id, kind, dumps(payload), now_iso()),
    )


def log(
    conn: sqlite3.Connection,
    run_id: str,
    source: str,
    dataset: str,
    key: str,
    status: str,
    error: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO sync_log(run_id, ts, source, dataset, key, status, error) "
        "VALUES (?,?,?,?,?,?,?)",
        (run_id, now_iso(), source, dataset, key, status, error),
    )


def coverage(conn: sqlite3.Connection) -> dict[str, Any]:
    """What data is stored: per-dataset day counts and date range, activity totals, last sync."""
    daily = [
        dict(r)
        for r in conn.execute(
            "SELECT dataset, COUNT(*) AS days, MIN(day) AS first_day, MAX(day) AS last_day, "
            "SUM(payload IS NULL OR payload='null') AS empty_days "
            "FROM raw_daily GROUP BY dataset ORDER BY dataset"
        )
    ]
    ranges = [
        dict(r)
        for r in conn.execute(
            "SELECT dataset, COUNT(*) AS chunks, MIN(start_day) AS first_day, "
            "MAX(end_day) AS last_day FROM raw_range GROUP BY dataset ORDER BY dataset"
        )
    ]
    acts = dict(
        conn.execute(
            "SELECT COUNT(*) AS activities, MIN(start_time_local) AS first, "
            "MAX(start_time_local) AS last, SUM(fit_parsed) AS with_fit FROM activities"
        ).fetchone()
    )
    last = conn.execute(
        "SELECT run_id, MAX(ts) AS finished, SUM(status='error') AS errors, COUNT(*) AS calls "
        "FROM sync_log GROUP BY run_id ORDER BY finished DESC LIMIT 1"
    ).fetchone()
    tidy = {}
    for t in ("daily", "sleep", "hrv", "health_status", "readiness", "training",
              "race_predictions", "scores", "fitness_age"):
        try:
            tidy[t] = dict(conn.execute(
                f"SELECT COUNT(*) AS days, MIN(day) AS first_day, MAX(day) AS last_day FROM {t}"
            ).fetchone())
        except sqlite3.OperationalError:
            pass  # not built yet
    completed = conn.execute("SELECT value FROM meta WHERE key='last_full_sync'").fetchone()
    retry = conn.execute("SELECT 1 FROM meta WHERE key='sync_retry_required'").fetchone()
    revisions = dict(conn.execute("SELECT kind, COUNT(*) FROM raw_payload_history GROUP BY kind"))
    return {"tidy": tidy, "daily": daily, "ranges": ranges, "activities": acts, "raw_revisions": revisions,
            "last_sync": dict(last) if last else None,
            "last_full_sync": completed[0] if completed else None, "retry_required": retry is not None}
