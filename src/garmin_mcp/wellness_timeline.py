"""Read the timestamped stress and Body Battery series already stored from Garmin Connect."""

import json
import math
import statistics
from datetime import UTC, datetime, timedelta, timezone
from itertools import groupby

METRICS = {"stress": ("stressValuesArray", 1, 0), "battery": ("bodyBatteryValuesArray", 2, 5)}
WINDOW_MINUTES = 15
BATTERY_DESCRIPTORS = "bodyBatteryValueDescriptorDTOList"


def _battery_layout(descriptors):
    if not isinstance(descriptors, list):
        return None
    named = {"timestamp": set(), "level": set()}
    for item in descriptors:
        if not isinstance(item, dict):
            continue
        key = item.get("bodyBatteryValueDescriptorKey", item.get("key"))
        index = item.get("bodyBatteryValueDescriptorIndex", item.get("index"))
        if not isinstance(key, str) or type(index) is not int or index < 0:
            continue
        key = key.lower().replace("_", "")
        if key in {"timestamp", "timestampgmt", "bodybatterytimestamp"}:
            named["timestamp"].add(index)
        elif key in {"level", "bodybatterylevel"}:
            named["level"].add(index)
    if any(len(indices) != 1 for indices in named.values()):
        return None
    stamp, level = (next(iter(indices)) for indices in named.values())
    return (stamp, level) if stamp != level else None


def device_zone(payload, home):
    """The watch's clock for one stored day, which differs from `home` while travelling.

    Garmin files readings under the watch's local date. Keep `home` (with its DST rules) when
    the day's recorded offset agrees with it, or when the payload carries no offset.
    """
    try:
        gmt = datetime.fromisoformat(payload["startTimestampGMT"]).replace(tzinfo=UTC)
        offset = datetime.fromisoformat(payload["startTimestampLocal"]) - gmt.replace(tzinfo=None)
        if gmt.astimezone(home).utcoffset() == offset or abs(offset) > timedelta(hours=14):
            return home
        return timezone(offset)
    except (KeyError, TypeError, ValueError, OverflowError):
        return home


def day_zones(conn, home, first="0000-00-00", last="9999-12-31"):
    """The watch's clock for each stored day that records one. Other days use `home`."""
    zones = {}
    # The pulse payload is read second so that it wins over the older export summary.
    for dataset, gmt, local in (("ex_daily_summary", "wellnessStartTimeGmt", "wellnessStartTimeLocal"),
                                ("pa_heart_rate", "startTimestampGMT", "startTimestampLocal")):
        for day, raw in conn.execute(
                "SELECT day, payload FROM raw_daily WHERE dataset=? AND day BETWEEN ? AND ?", (dataset, first, last)):
            try:
                payload = json.loads(raw)
                recorded = {"startTimestampGMT": payload[gmt], "startTimestampLocal": payload[local]}
            except (KeyError, TypeError, ValueError):
                continue
            zones[day] = device_zone(recorded, home)
    return zones


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


def samples(payload, day, zone, *, preserve_conflicts=False):
    """Decode Connect arrays. Keep conflicting values only for source comparisons."""
    output = {}
    zone = device_zone(payload, zone)
    for key, (field, value_index, minimum) in METRICS.items():
        rows = payload.get(field)
        if not isinstance(rows, list):
            continue
        described_battery = key == "battery" and BATTERY_DESCRIPTORS in payload
        layout = _battery_layout(payload[BATTERY_DESCRIPTORS]) if described_battery else None
        if described_battery and layout is None:
            continue
        points = {}
        for row in rows:
            if not isinstance(row, list):
                continue
            stamp_index, reading_index = layout or (0, 1 if key == "battery" and len(row) == 2 else value_index)
            if max(stamp_index, reading_index) >= len(row):
                continue
            stamp, value = row[stamp_index], row[reading_index]
            if (type(stamp) not in (int, float) or type(value) not in (int, float)
                    or not minimum <= value <= 100):
                continue
            try:
                local = datetime.fromtimestamp(stamp / 1000, zone)
            except (ValueError, OverflowError, OSError):
                continue
            if math.isfinite(stamp) and local.date().isoformat() == day:
                sample_key = (stamp, value) if preserve_conflicts else stamp
                points.setdefault(sample_key, (local, value))
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
