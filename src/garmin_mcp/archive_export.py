"""Read-only CSV summaries for the owner to use outside Garmin Tracking."""

import csv
import math
import re
import sqlite3
from contextlib import closing
from datetime import date
from os import link
from pathlib import Path
from tempfile import NamedTemporaryFile

from garmin_mcp.recovery import nightly_hrv

ACTIVITY_COLUMNS = (
    "activity_id", "local_date", "activity_type", "duration_s", "distance_m",
    "avg_hr_bpm", "max_hr_bpm", "energy_kcal", "elevation_gain_m",
)
WELLNESS_COLUMNS = (
    "local_date", "steps", "distance_m", "resting_hr_bpm", "stress_avg_0_100",
    "body_battery_min_0_100", "body_battery_max_0_100", "sleep_s", "sleep_score_0_100",
    "night_hrv_ms",
)
ACTIVITY_SQL = """
    SELECT activity_id, substr(start_time_local, 1, 10), type, duration_s, distance_m,
           avg_hr, max_hr, calories, elevation_gain_m
    FROM activities
    WHERE start_time_local >= ? AND substr(start_time_local, 1, 10) <= ?
    ORDER BY start_time_local, activity_id
"""
WELLNESS_SQL = """
    WITH coverage AS (
        SELECT day FROM daily WHERE day BETWEEN :start AND :end
        UNION SELECT day FROM sleep WHERE day BETWEEN :start AND :end
        UNION SELECT day FROM hrv WHERE day BETWEEN :start AND :end
        UNION SELECT day FROM health_status WHERE day BETWEEN :start AND :end
    )
    SELECT coverage.day, daily.steps, daily.distance_m, daily.resting_hr, daily.stress_avg,
           daily.body_battery_min, daily.body_battery_max, sleep.sleep_s, sleep.score
    FROM coverage
    LEFT JOIN daily USING (day)
    LEFT JOIN sleep USING (day)
    ORDER BY coverage.day
"""


def _iso_day(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return value if parsed.isoformat() == value else None


def _number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def write_csv(path, dataset, start, end, output):
    """Write selected summaries. Missing and invalid values remain blank."""
    if start > end:
        raise ValueError("The start date must be on or before the end date.")
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        if dataset == "activities":
            columns = ACTIVITY_COLUMNS
            rows = conn.execute(ACTIVITY_SQL, (start.isoformat(), end.isoformat()))
        elif dataset == "wellness":
            columns = WELLNESS_COLUMNS
            rows = conn.execute(WELLNESS_SQL, {"start": start.isoformat(), "end": end.isoformat()})
            hrv = nightly_hrv(conn, start.isoformat(), end.isoformat())
        else:
            raise ValueError("Choose activities or wellness.")
        writer = csv.writer(output)
        writer.writerow(columns)
        for row in rows:
            if dataset == "activities":
                activity_id, day, category, *readings = row
                if _iso_day(day) is None:
                    continue
                # A provider category begins with a letter. Blank unexpected values
                # rather than emitting free text that a spreadsheet could run.
                if not isinstance(category, str) or not re.fullmatch(r"[a-z][a-z0-9_-]*", category):
                    category = None
                writer.writerow((activity_id, day, category, *map(_number, readings)))
            else:
                day, *readings = row
                values = (*map(_number, readings), hrv.get(day))
                if _iso_day(day) is not None and any(value is not None for value in values):
                    writer.writerow((day, *values))


def export_file(path, dataset, start, end, destination):
    """Publish a new owner-only file. Preserve any existing destination."""
    destination = destination.expanduser()
    # NamedTemporaryFile creates a mode-0600 file. Linking within the same directory
    # publishes the complete file without replacing an existing name.
    temporary_path = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                dir=destination.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            write_csv(path, dataset, start, end, temporary)
        link(temporary_path, destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
