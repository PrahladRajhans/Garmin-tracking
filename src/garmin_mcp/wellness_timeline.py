"""Read the timestamped stress and Body Battery series already stored from Garmin Connect."""

import json
import math
import statistics
from datetime import datetime
from itertools import groupby

METRICS = {"stress": ("stressValuesArray", 1, 0), "battery": ("bodyBatteryValuesArray", 2, 5)}
WINDOW_MINUTES = 15


def archived_days(conn, start=None, end=None):
    sql = "SELECT day, payload FROM raw_daily WHERE dataset='stress'"
    params = ()
    if start is not None and end is not None:
        sql += " AND day BETWEEN ? AND ?"
        params = (start, end)
    for day, raw in conn.execute(sql + " ORDER BY day", params):
        try:
            payload = json.loads(raw) if raw else None
        except (TypeError, ValueError):
            payload = None
        yield day, payload if isinstance(payload, dict) else {}


def samples(payload, day, zone):
    """Decode the known Connect arrays. Missing, activity and unrecognized data stay absent."""
    output = {}
    for key, (field, value_index, minimum) in METRICS.items():
        rows = payload.get(field)
        if not isinstance(rows, list):
            continue
        points = {}
        for row in rows:
            if not isinstance(row, list) or len(row) <= value_index:
                continue
            stamp, value = row[0], row[value_index]
            if (type(stamp) not in (int, float) or type(value) not in (int, float)
                    or not minimum <= value <= 100):
                continue
            try:
                local = datetime.fromtimestamp(stamp / 1000, zone)
            except (ValueError, OverflowError, OSError):
                continue
            if math.isfinite(stamp) and local.date().isoformat() == day:
                points.setdefault(stamp, (local, value))
        if points:
            output[key] = [points[t] for t in sorted(points)]
    return output


def _bucket(local):
    return local.replace(minute=local.minute // WINDOW_MINUTES * WINDOW_MINUTES,
                         second=0, microsecond=0).timestamp()


def _clock_label(local):
    label = local.strftime("%H:%M")
    if local.replace(fold=0).utcoffset() != local.replace(fold=1).utcoffset():
        label += local.strftime(" %z")
    return label


def _series(points, key):
    slots = []
    for stamp, chunk in groupby(points, key=lambda point: _bucket(point[0])):
        values = [value for _, value in chunk]
        local = datetime.fromtimestamp(stamp, points[0][0].tzinfo)
        slots.append({"time": _clock_label(local), "minute": stamp / 60,
                      "value": statistics.median(values) if key == "stress" else values[-1],
                      "span": (min(values), max(values)), "count": len(values)})
    return {"slots": slots, "count": len(points),
            "first": (_clock_label(points[0][0]), points[0][1]),
            "last": (_clock_label(points[-1][0]), points[-1][1])}


def collect(conn, start, end, zone):
    for day, payload in archived_days(conn, start, end):
        if readings := samples(payload, day, zone):
            yield day, {key: _series(points, key) for key, points in readings.items()}
