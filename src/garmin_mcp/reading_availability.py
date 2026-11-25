"""Dated availability for the signals behind dashboard guidance."""

import sqlite3
from datetime import UTC, datetime
from sys import float_info

from garmin_mcp import recovery


def _readings(table, column, *, minimum=0, maximum=float_info.max, include_min=False):
    comparison = ">=" if include_min else ">"
    return (f"SELECT day FROM {table} WHERE typeof({column}) IN ('integer','real') "
            f"AND {column} {comparison} {minimum} AND {column} <= {maximum}")


METRICS = (
    ("sleep", "Sleep duration", _readings("sleep", "sleep_s", minimum=recovery.MIN_VALID_NIGHT_H * 3600,
                                          include_min=True)),
    ("hrv", "Overnight HRV", f'{_readings("hrv", "last_night_avg")} UNION ALL {_readings("health_status", "hrv")}'),
    ("pulse", "Resting heart rate", _readings("daily", "resting_hr")),
    ("respiration", "Breathing rate", (f'{_readings("sleep", "avg_respiration")} UNION ALL '
                                      f'{_readings("health_status", "respiration")}')),
    ("garmin", "Garmin readiness", (_readings("readiness", "score", maximum=100, include_min=True)
                                    + " OR (typeof(level)='text' AND trim(level)!='')")),
)
COMPONENTS = (
    ("hrv", "HRV over the last 7 days"),
    ("pulse", "Resting pulse for this date"),
    ("sleep", "The night ending on this date"),
    ("respiration", "Breathing rate for this date"),
)


def complete_sync(conn: sqlite3.Connection, now: datetime) -> datetime | None:
    row = conn.execute("SELECT value FROM meta WHERE key='last_full_sync'").fetchone()
    try:
        stamp = datetime.fromisoformat(row[0]) if row else None
    except (TypeError, ValueError):
        return None
    return stamp if stamp and stamp.tzinfo is not None and stamp <= now else None


def collect(conn, day, zone, *, brief, retry=False, now=None):
    now = now or datetime.now(UTC)
    actual_day = now.astimezone(zone).date().isoformat()
    sync = complete_sync(conn, now)
    sync_day = sync.astimezone(zone).date().isoformat() if sync else None
    awaiting = day == actual_day and (retry or sync_day != day)
    rows = {}
    matching_brief = brief.get("day", day) == day
    incomplete = conn.execute(_readings("sleep", "sleep_s") + " AND day=? AND sleep_s<?",
                              (day, recovery.MIN_VALID_NIGHT_H * 3600)).fetchone() is not None
    for key, name, source in METRICS:
        latest = conn.execute(f"SELECT MAX(day) FROM ({source}) WHERE day<=?", (day,)).fetchone()[0]
        if latest == day:
            state = "recorded"
        elif key == "sleep" and incomplete:
            state = "incomplete"
        else:
            state = "awaiting_sync" if awaiting else "absent"
        rows[key] = {"label": name, "state": state, "latest": latest}
    ours = brief["readiness"]["ours"] if matching_brief else {}
    usable = [label for (_, label), component in zip(COMPONENTS, ours.get("components", ()))
              if component.get("contribution") is not None]
    return {"day": day, "rows": rows, "usable": usable,
            "minimum": ours.get("minimum_signals", recovery.MIN_READINESS_SIGNALS),
            "score_available": ours.get("composite_z") is not None,
            "published_guidance": actual_day == day and not retry and matching_brief,
            "sync_day": sync_day}
