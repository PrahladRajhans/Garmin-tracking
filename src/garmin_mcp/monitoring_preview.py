"""Compare one Garmin monitoring FIT file with saved wellness data without importing it."""

import json
import math
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256
from os import fsync, link
from tempfile import NamedTemporaryFile

from garmin_mcp import engine, fit, wellness_timeline

FIT_EPOCH = datetime(1989, 12, 31, tzinfo=UTC).timestamp()
MONITORING_TYPES = {"monitoring_a", "monitoring_b", "monitoring_daily"}
LIMITS = {"pulse": (1, 300), "stress": (0, 100), "body_battery": (5, 100),
          "resting_pulse": (1, 300)}
FIT_SIGNALS = (
    ("stress_level_mesgs", "stress_level_time", "stress_level_value", "stress"),
    ("hsa_stress_data_mesgs", "timestamp", "stress_level", "stress"),
    ("hsa_body_battery_data_mesgs", "timestamp", "level", "body_battery"),
    ("monitoring_hr_data_mesgs", "timestamp", "current_day_resting_heart_rate", "resting_pulse"),
    ("monitoring_mesgs", "timestamp", "heart_rate", "pulse"),
)


def _add(points, metric, stamp, reading):
    low, high = LIMITS[metric]
    if stamp is not None and type(reading) in (int, float) and low <= reading <= high:
        points[metric][stamp].add(reading)


def _epoch(value):
    return value.timestamp() if isinstance(value, datetime) and value.tzinfo is not None else None


def _day(stamp, zone):
    return stamp if isinstance(stamp, str) else datetime.fromtimestamp(stamp, zone).date().isoformat()


def _watch_zone(messages, home):
    """The offset the watch was using, from its own local timestamp, else the configured zone."""
    for row in messages.get("monitoring_info_mesgs", ()):
        stamp, local = _epoch(row.get("timestamp")), row.get("local_timestamp")
        if stamp is not None and type(local) is int:
            offset = timedelta(seconds=round(local + FIT_EPOCH - stamp))
            if abs(offset) <= timedelta(hours=14):
                return timezone(offset)
    return home


def _fit_signals(messages, zone):
    points = {metric: defaultdict(set) for metric in LIMITS}
    latest_full = None
    for name, time_key, value_key, metric in FIT_SIGNALS:
        for row in messages.get(name, ()):
            stamp = _epoch(row.get(time_key))
            if stamp is not None:
                latest_full = max(latest_full if latest_full is not None else stamp, stamp)
            if metric == "resting_pulse" and stamp is not None:
                # Written at the watch's midnight for the day that is ending.
                stamp = _day(stamp - 1, zone)
            _add(points, metric, stamp, row.get(value_key))

    # The 16-bit field is relative to the FIT epoch. A preceding timestamp anchors
    # its rollover and a decoded full timestamp bounds the end of the stream.
    monitoring = messages.get("monitoring_mesgs", ())
    bounds = {}
    end = latest_full
    for index in range(len(monitoring) - 1, -1, -1):
        if (stamp := _epoch(monitoring[index].get("timestamp"))) is not None:
            end = stamp
        else:
            bounds[index] = end

    previous = None
    unanchored = 0
    for index, row in enumerate(monitoring):
        if (stamp := _epoch(row.get("timestamp"))) is not None:
            previous = stamp
        elif type(short := row.get("timestamp_16")) is int and 0 <= short < 65535:
            if previous is not None:
                stamp = previous + (short - int(previous - FIT_EPOCH)) % 65536
            if stamp is not None and bounds[index] is not None and stamp <= bounds[index]:
                previous = stamp
                _add(points, "pulse", stamp, row.get("heart_rate"))
            elif type(row.get("heart_rate")) in (int, float):
                unanchored += 1
    return points, unanchored


def _pulse_rows(payload):
    try:
        content = json.loads(payload) if payload else None
    except (TypeError, ValueError):
        content = None
    content = content if isinstance(content, dict) else {}
    rows = content.get("heartRateValues")
    rows = rows if isinstance(rows, list) else []
    return content, [(row[0], row[1]) for row in rows if isinstance(row, list) and len(row) >= 2]


def _archive_signals(conn, start, end, zone):
    points = {metric: defaultdict(set) for metric in LIMITS}
    for day, raw in conn.execute(
        "SELECT day, payload FROM raw_daily WHERE day BETWEEN ? AND ? "
        "AND dataset IN ('heart_rate','pa_heart_rate')", (start, end)
    ):
        content, rows = _pulse_rows(raw)
        local_zone = wellness_timeline.device_zone(content, zone)
        for ms, bpm in rows:
            if type(ms) not in (int, float) or not math.isfinite(ms) or ms <= 0:
                continue
            stamp = ms / 1000
            try:
                local_day = _day(stamp, local_zone)
            except (ValueError, OSError, OverflowError):
                continue
            if day == local_day:
                _add(points, "pulse", stamp, bpm)
    for day, payload in wellness_timeline.archived_days(conn, start, end):
        for name, entries in wellness_timeline.samples(payload, day, zone, preserve_conflicts=True).items():
            metric = "body_battery" if name == "battery" else name
            for stamp, value in entries:
                _add(points, metric, stamp.timestamp(), value)
    if conn.execute("SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'daily'").fetchone():
        for day, bpm in conn.execute("SELECT day, resting_hr FROM daily WHERE day BETWEEN ? AND ?", (start, end)):
            _add(points, "resting_pulse", day, bpm)
    return points


def _counts():
    return dict.fromkeys(("fit_keys", "candidate_gaps", "overlaps", "agreements",
                          "disagreements", "archive_conflicts", "fit_conflicts"), 0)


def _compare(incoming, archived, zone, include_dates):
    totals = _counts()
    by_day = defaultdict(_counts)
    for stamp, readings in incoming.items():
        if len(readings) > 1:
            decision = "fit_conflicts"
        elif not (old := archived.get(stamp)):
            decision = "candidate_gaps"
        elif len(old) > 1:
            decision = "archive_conflicts"
        else:
            decision = "agreements" if old == readings else "disagreements"
        entries = (totals, by_day[_day(stamp, zone)]) if include_dates else (totals,)
        for counts in entries:
            counts["fit_keys"] += 1
            counts[decision] += 1
            counts["overlaps"] += decision in {"agreements", "disagreements"}
    if include_dates:
        totals["by_local_date"] = dict(sorted(by_day.items()))
    return totals


def _retain(data, directory):
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = directory / f"{sha256(data).hexdigest()}.fit"
    with NamedTemporaryFile(dir=directory) as temporary:
        temporary.write(data)
        temporary.flush()
        fsync(temporary.fileno())
        try:
            link(temporary.name, destination)
        except FileExistsError:
            if destination.read_bytes() != data:
                raise ValueError("A retained monitoring FIT conflicts with its content hash.")
            return "already_present"
    return "created"


def preview(database_path, fit_path, *, include_dates=False, retain_directory=None):
    """Report counts, with an optional byte-for-byte raw copy outside SQLite."""
    data = fit_path.expanduser().read_bytes()
    messages = fit.decode(data, merge_heart_rates=False)
    kinds = {row.get("type") for row in messages.get("file_id_mesgs", ())}
    if not kinds or not kinds <= MONITORING_TYPES:
        raise ValueError("Choose a Garmin monitoring FIT file, not an activity or workout FIT.")

    with closing(sqlite3.connect(database_path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        if not conn.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name='raw_daily'").fetchone():
            raise ValueError("This database has no Garmin wellness archive schema.")
        zone = _watch_zone(messages, engine._tz(conn))
        incoming, unanchored = _fit_signals(messages, zone)
        days = {_day(stamp, zone) for values in incoming.values() for stamp in values}
        if days:
            archived = _archive_signals(conn, min(days), max(days), zone)
        else:
            archived = {metric: {} for metric in LIMITS}

    compared = {signal[0] for signal in FIT_SIGNALS} | {"file_id_mesgs"}
    result = {
        "candidate_local_days": len(days), "unanchored_pulse_messages": unanchored,
        "uncompared_message_types": {name: len(rows) for name, rows in sorted(messages.items())
                                     if name not in compared},
        "signals": {metric: _compare(incoming[metric], archived[metric], zone, include_dates)
                    for metric in LIMITS},
    }
    if retain_directory is not None:
        result["retained"] = _retain(data, retain_directory)
    return result
