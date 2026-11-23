"""Parse FIT activity files with Garmin's official SDK and store streams in SQLite."""

from __future__ import annotations

import sqlite3
from typing import Any

from garmin_fit_sdk import Decoder, Stream

from garmin_mcp.db import dumps

SEMICIRCLE_TO_DEG = 180.0 / 2**31

# Columns pulled out of each record; everything else goes to `extra` JSON.
_RECORD_MAP = {
    "heart_rate": ("heart_rate",),
    "speed": ("enhanced_speed", "speed"),
    "cadence": ("cadence",),
    "power": ("power",),
    "altitude": ("enhanced_altitude", "altitude"),
    "distance": ("distance",),
    "temperature": ("temperature",),
    "vertical_oscillation": ("vertical_oscillation",),
    "stance_time": ("stance_time",),
    "step_length": ("step_length",),
}
_CONSUMED = {k for keys in _RECORD_MAP.values() for k in keys} | {
    "timestamp",
    "position_lat",
    "position_long",
}


class FitDecodeError(ValueError):
    pass


def decode(data: bytes) -> dict[str, list[dict[str, Any]]]:
    messages, errors = Decoder(Stream.from_byte_array(bytearray(data))).read()
    if errors and not messages.get("record_mesgs") and not messages.get("session_mesgs"):
        raise FitDecodeError("; ".join(str(e) for e in errors))
    return messages


def _first(rec: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = rec.get(key)
        if value is not None:
            return value
    return None


def _deg(value: Any) -> float | None:
    return value * SEMICIRCLE_TO_DEG if isinstance(value, (int, float)) else None


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else None)


def store(conn: sqlite3.Connection, activity_id: int, data: bytes) -> dict[str, int]:
    """Decode a FIT file and replace this activity's stored streams. Returns row counts."""
    messages = decode(data)
    for table in ("fit_records", "fit_laps", "fit_hrv", "fit_sessions"):
        conn.execute(f"DELETE FROM {table} WHERE activity_id=?", (activity_id,))

    records = []
    for rec in messages.get("record_mesgs", []):
        if rec.get("timestamp") is None:
            continue
        extra = {k: v for k, v in rec.items() if k not in _CONSUMED and v is not None}
        records.append(
            (
                activity_id,
                _iso(rec["timestamp"]),
                *(_first(rec, keys) for keys in _RECORD_MAP.values()),
                _deg(rec.get("position_lat")),
                _deg(rec.get("position_long")),
                dumps(extra) if extra else None,
            )
        )
    cols = ["activity_id", "ts", *_RECORD_MAP.keys(), "lat", "lon", "extra"]
    conn.executemany(
        f"INSERT INTO fit_records({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
        records,
    )

    laps = [
        (
            activity_id,
            i,
            _iso(lap.get("start_time")),
            lap.get("total_timer_time"),
            lap.get("total_distance"),
            lap.get("avg_heart_rate"),
            lap.get("max_heart_rate"),
            _first(lap, ("enhanced_avg_speed", "avg_speed")),
            _first(lap, ("avg_running_cadence", "avg_cadence")),
            lap.get("avg_power"),
            dumps(lap),
        )
        for i, lap in enumerate(messages.get("lap_mesgs", []))
    ]
    conn.executemany("INSERT INTO fit_laps VALUES (?,?,?,?,?,?,?,?,?,?,?)", laps)

    # Beat-to-beat intervals (only present when HRV logging is enabled on the watch).
    rr = [t for msg in messages.get("hrv_mesgs", []) for t in (msg.get("time") or []) if t]
    conn.executemany(
        "INSERT INTO fit_hrv(activity_id, seq, rr_s) VALUES (?,?,?)",
        [(activity_id, i, float(t)) for i, t in enumerate(rr)],
    )

    sessions = messages.get("session_mesgs", [])
    if sessions:
        s = sessions[0]
        conn.execute(
            "INSERT INTO fit_sessions(activity_id, sport, sub_sport, payload) VALUES (?,?,?,?)",
            (activity_id, str(s.get("sport")), str(s.get("sub_sport")), dumps(sessions)),
        )
    conn.execute("UPDATE activities SET fit_parsed=1 WHERE activity_id=?", (activity_id,))
    return {"records": len(records), "laps": len(laps), "rr_intervals": len(rr)}
