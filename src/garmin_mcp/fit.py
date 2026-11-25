"""Parse FIT activity files with Garmin's official SDK and store streams in SQLite."""

from __future__ import annotations

import json
import sqlite3
from hashlib import sha256
from os import fsync, link
from pathlib import Path
from tempfile import NamedTemporaryFile
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


def is_running_activity(activity_type: str | None) -> bool:
    return "run" in (activity_type or "").lower()


def cadence_units(activity_type: str | None) -> tuple[int, str | None]:
    """Scale one-foot running cadence to steps; keep cycling pedal revolutions as read."""
    if is_running_activity(activity_type):
        return 2, "steps/min"
    return 1, "rev/min" if "cycl" in (activity_type or "").lower() else None


def session_messages(payload: str | None) -> list[dict[str, Any]]:
    """Read the stored FIT session list, including a single-session object."""
    try:
        messages = json.loads(payload) if payload else []
    except (TypeError, ValueError):
        return []
    if isinstance(messages, dict):
        return [messages]
    if isinstance(messages, list) and all(isinstance(message, dict) for message in messages):
        return messages
    return []


def retain_file(directory: Path, activity_id: int, data: bytes) -> Path:
    """Keep received FIT bytes without replacing a different file."""
    original = directory / f"{activity_id}.fit"
    with NamedTemporaryFile(dir=directory) as temporary:
        temporary.write(data)
        temporary.flush()
        fsync(temporary.fileno())
        try:
            link(temporary.name, original)
        except FileExistsError:
            if original.read_bytes() != data:
                revision = directory / f"{activity_id}-{sha256(data).hexdigest()}.fit"
                try:
                    link(temporary.name, revision)
                except FileExistsError:
                    pass  # the same bytes are already stored under their hash
                return revision
    return original


def decode(data: bytes, *, merge_heart_rates: bool = True) -> dict[str, list[dict[str, Any]]]:
    # A session-only FIT may include HR messages but has no record stream to merge into.
    decoder = Decoder(Stream.from_byte_array(bytearray(data)))
    messages, errors = decoder.read(merge_heart_rates=merge_heart_rates)
    if (merge_heart_rates and len(errors) == 1 and isinstance(errors[0], KeyError)
            and errors[0].args == ("record_mesgs",) and "hr_mesgs" in messages):
        messages, errors = Decoder(Stream.from_byte_array(bytearray(data))).read(merge_heart_rates=False)
    if errors or not messages:
        raise FitDecodeError("FIT integrity check failed." if errors else "No FIT messages were decoded.")
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


def store(conn: sqlite3.Connection, activity_id: int, data: bytes,
          *, path: Path | None = None) -> dict[str, int]:
    """Decode and atomically replace this activity's FIT rows and optional file reference."""
    return store_decoded(conn, activity_id, decode(data), path=path)


def store_decoded(conn: sqlite3.Connection, activity_id: int,
                  messages: dict[str, list[dict[str, Any]]],
                  *, path: Path | None = None) -> dict[str, int]:
    kinds = {row.get("type") for row in messages.get("file_id_mesgs", ())} - {None}
    if kinds - {"activity"} or not any(messages.get(name) for name in (
        "record_mesgs", "session_mesgs", "lap_mesgs", "length_mesgs", "set_mesgs",
    )):
        raise FitDecodeError("No activity streams were decoded.")
    if not conn.in_transaction:
        conn.execute("BEGIN")
    conn.execute("SAVEPOINT store_fit")
    try:
        counts = _store_messages(conn, activity_id, messages)
        if path is not None:
            conn.execute("UPDATE activities SET fit_path=? WHERE activity_id=?", (str(path), activity_id))
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK TO store_fit")
            conn.execute("RELEASE store_fit")
        raise
    else:
        conn.execute("RELEASE store_fit")
        return counts


def _store_messages(conn, activity_id, messages):
    for table in ("fit_records", "fit_laps", "fit_hrv", "fit_sessions", "fit_lengths",
                  "fit_sets", "fit_zones", "fit_profile"):
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

    # Pool swims: one message per length (active or rest).
    lengths = [
        (activity_id, i, str(x.get("length_type")), str(x.get("swim_stroke")),
         x.get("total_timer_time"), x.get("total_strokes"), x.get("avg_swimming_cadence"))
        for i, x in enumerate(messages.get("length_mesgs", []))
    ]
    conn.executemany("INSERT INTO fit_lengths VALUES (?,?,?,?,?,?,?)", lengths)

    # Strength: one message per set. category is a list (main, sub, ...) in the SDK output.
    def _cat(value: Any) -> str | None:
        if isinstance(value, (list, tuple)):
            parts = [str(v) for v in value if v not in (None, "unknown")]
            return "/".join(parts) or None
        return None if value in (None, "unknown") else str(value)

    sets = [
        (activity_id, i, str(x.get("set_type")), _cat(x.get("category")),
         x.get("repetitions"), x.get("weight"), x.get("duration"))
        for i, x in enumerate(messages.get("set_mesgs", []))
    ]
    conn.executemany("INSERT INTO fit_sets VALUES (?,?,?,?,?,?,?)", sets)

    zone = next((z for z in messages.get("time_in_zone_mesgs", [])
                 if z.get("reference_mesg") == "session"), None)
    if zone:
        conn.execute(
            "INSERT INTO fit_zones VALUES (?,?,?,?,?,?,?,?)",
            (activity_id, dumps(zone.get("time_in_hr_zone")),
             dumps(zone.get("hr_zone_high_boundary")), dumps(zone.get("time_in_power_zone")),
             str(zone.get("hr_calc_type")), zone.get("max_heart_rate"),
             zone.get("resting_heart_rate"), zone.get("threshold_heart_rate")))
    prof = (messages.get("user_profile_mesgs") or [None])[0]
    if prof:
        conn.execute("INSERT INTO fit_profile VALUES (?,?,?,?,?)",
                     (activity_id, str(prof.get("gender")), prof.get("weight"),
                      prof.get("height"), prof.get("resting_heart_rate")))

    sessions = messages.get("session_mesgs", [])
    if sessions:
        s = sessions[0]
        conn.execute(
            "INSERT INTO fit_sessions(activity_id, sport, sub_sport, payload) VALUES (?,?,?,?)",
            (activity_id, str(s.get("sport")), str(s.get("sub_sport")), dumps(sessions)),
        )
    conn.execute("UPDATE activities SET fit_parsed=1 WHERE activity_id=?", (activity_id,))
    return {"records": len(records), "laps": len(laps), "rr_intervals": len(rr),
            "lengths": len(lengths), "sets": len(sets)}


def reparse_all(conn: sqlite3.Connection) -> dict[str, int]:
    """Re-read every stored FIT file (after parser improvements). Never re-downloads."""
    done = missing = errors = 0
    for activity_id, path in conn.execute(
        "SELECT activity_id, fit_path FROM activities WHERE fit_path IS NOT NULL"
    ).fetchall():
        if not path or not Path(path).exists():
            missing += 1
            continue
        try:
            store(conn, activity_id, Path(path).read_bytes())
            done += 1
        except Exception:  # noqa: BLE001 - keep going; counted
            errors += 1
    conn.commit()
    return {"reparsed": done, "missing_files": missing, "errors": errors}
