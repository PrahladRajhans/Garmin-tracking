"""Dated archive coverage and descriptive references for dashboard readings."""

import json
import math
import statistics
from datetime import date
from itertools import pairwise

from garmin_mcp.recovery import MIN_VALID_NIGHT_H, nightly_hrv

METRICS = {
    "resting_hr": ("Garmin resting pulse", " bpm"),
    "steps": ("Steps", " steps"),
    "stress_avg": ("Garmin daytime stress", "/100"),
    "body_battery_max": ("Daily Body Battery high", "/100"),
    "spo2_avg": ("Daily Pulse Ox", "%"),
    "sleep_h": ("Sleep duration", " h"),
    "score": ("Garmin sleep score", "/100"),
    "avg_respiration": ("Overnight breathing rate", " breaths/min"),
    "hrv": ("Overnight HRV", " ms"),
}
MIN_READINGS = 14


def _within(value, low, high):
    return isinstance(value, (int, float)) and math.isfinite(value) and low <= value <= high


def _window(values, first, last):
    bounds = [(day, value) for day, value in values if first <= day <= last]
    missing = [(a + 1, b - 1) for a, b in pairwise(
        [first - 1, *(day for day, _ in bounds), last + 1]) if b - a > 1]
    longest = max(missing, key=lambda span: span[1] - span[0], default=None)
    observations = sorted(value for _, value in bounds)
    count = len(observations)
    typical = None
    if count >= MIN_READINGS:
        typical = (statistics.median(observations), observations[count // 4],
                   observations[(count - 1) * 3 // 4])
    return {"first": date.fromordinal(first).isoformat(), "last": date.fromordinal(last).isoformat(),
            "count": count, "missing": last - first + 1 - count, "gap_count": len(missing),
            "longest": tuple(date.fromordinal(d).isoformat() for d in longest) if longest else (),
            "sparse_gaps": [tuple(date.fromordinal(d).isoformat() for d in span) for span in missing]
            if count < MIN_READINGS else [],
            "typical": typical}


def windows(values, day, archive_start):
    cutoff = date.fromisoformat(day).toordinal() - 1
    earlier = sorted((date.fromisoformat(d).toordinal(), v) for d, v in values.items() if d < day)
    spans = [("28 days", cutoff - 27), ("90 days", cutoff - 89)]
    if archive_start and archive_start < day:
        spans.append(("Full archive", date.fromisoformat(archive_start).toordinal()))
    return {name: _window(earlier, start, cutoff) for name, start in spans}


def collect(conn, end):
    """Read every retained dated record once, without modifying the archive."""
    archive_start = None
    series = {key: {} for key in METRICS}
    for row in conn.execute(
            "SELECT day, resting_hr, steps, stress_avg, body_battery_max, spo2_avg "
            "FROM daily WHERE day <= ?", (end,)):
        archive_start = min(archive_start or row["day"], row["day"])
        for key, low, high in (("resting_hr", 1, 300), ("steps", 0, math.inf),
                               ("stress_avg", 0, 100), ("body_battery_max", 0, 100), ("spo2_avg", 1, 100)):
            value = row[key]
            if _within(value, low, high):
                series[key][row["day"]] = value
    for day, seconds, score, breaths in conn.execute(
            "SELECT day, sleep_s, score, avg_respiration FROM sleep WHERE day <= ?", (end,)):
        archive_start = min(archive_start or day, day)
        if not _within(seconds, MIN_VALID_NIGHT_H * 3600, 24 * 3600):
            continue
        series["sleep_h"][day] = seconds / 3600
        if _within(score, 0, 100):
            series["score"][day] = score
        if _within(breaths, 0, math.inf) and breaths > 0:
            series["avg_respiration"][day] = breaths
    hrv_start = conn.execute(
        "SELECT MIN(day) FROM (SELECT MIN(day) AS day FROM hrv WHERE day <= ? "
        "UNION ALL SELECT MIN(day) FROM health_status WHERE day <= ?)", (end, end)).fetchone()[0]
    if hrv_start:
        archive_start = min(archive_start or hrv_start, hrv_start)
        series["hrv"] = nightly_hrv(conn, hrv_start, end)
    return archive_start, series


def resting_pulse_sources(conn, first, end):
    """Collect independently dated Garmin resting estimates and preserve source conflicts."""
    from garmin_mcp.normalize import daily_from_summary

    datasets = ("pa_daily_summary", "user_summary", "ex_daily_summary")
    rows = conn.execute(
        "SELECT day,day,dataset,payload FROM raw_daily WHERE day BETWEEN ? AND ? "
        "AND dataset IN (?,?,?) UNION ALL "
        "SELECT start_day,end_day,dataset,payload FROM raw_range WHERE start_day<=? AND end_day>=? "
        "AND dataset IN (?,?,?)", (first, end, *datasets, end, first, *datasets))
    result = {}
    for start, stop, dataset, payload in rows:
        try:
            records = daily_from_summary(json.loads(payload), exported=dataset == "ex_daily_summary")
            for day, readings in records:
                if max(first, start) <= day <= min(end, stop):
                    value = readings.get("resting_hr")
                    if _within(value, 1, 300):
                        result.setdefault(day, {}).setdefault(dataset, set()).add(value)
        except (TypeError, ValueError):
            continue
    return result
