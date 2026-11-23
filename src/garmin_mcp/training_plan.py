"""A conservative seven-day starting point based on recorded training and today's recovery."""

from __future__ import annotations

import math
import sqlite3
import statistics
from datetime import date, timedelta
from typing import Any

from garmin_mcp.health import status_days
from garmin_mcp.loads import RUN_TYPES

RUN_ACTIVITY_TYPES = (*RUN_TYPES, "treadmill_running")


def week(conn: sqlite3.Connection, day: str, readiness: dict[str, Any]) -> dict[str, Any]:
    """Hold week-ahead running to the recent routine. Treat thin history as a fresh start."""
    status = readiness.get("activity_status")
    garmin = (readiness["garmin"] or {}).get("level")
    state = readiness["ours"]["state"]
    if status:
        return {"plan": "Pause the weekly plan.",
                "basis": f"Your day is tagged {status}. Resume when you feel ready."}
    if readiness["illness_flag"]["raised"] or state == "well below usual" or garmin == "POOR":
        return {"plan": "Take a rest day and reassess tomorrow.",
                "basis": "Today’s recovery signals support starting the week gently."}

    end = date.fromisoformat(day)
    first = end - timedelta(days=28)
    weeks: list[dict[str, float]] = [{}, {}, {}, {}]
    excluded = status_days(conn)
    placeholders = ",".join("?" for _ in RUN_ACTIVITY_TYPES)
    for stamped, duration_s in conn.execute(
            "SELECT substr(start_time_local,1,10), duration_s FROM activities "
            f"WHERE type IN ({placeholders}) AND substr(start_time_local,1,10)>=? "
            "AND substr(start_time_local,1,10)<? AND duration_s >= 300",
            (*RUN_ACTIVITY_TYPES, first.isoformat(), day)):
        if stamped in excluded or not math.isfinite(duration_s):
            continue
        try:
            block = (date.fromisoformat(stamped) - first).days // 7
        except ValueError:
            continue
        minutes = duration_s / 60
        # Use the shorter session on a double day to avoid planning a long consolidated effort.
        previous = weeks[block].get(stamped, minutes)
        weeks[block][stamped] = min(previous, minutes)

    run_days = [len(block) for block in weeks]
    session_count = min(3, int(statistics.median(run_days)))
    if not session_count or not any(run_days[-2:]):
        return {"plan": "Start with one easy 10-minute walk if you feel well.",
                "basis": "Recent running is sparse. See how you feel later that day and the next "
                         "morning before deciding what to repeat."}
    minutes = min(45, int(statistics.median(m for block in weeks for m in block.values())))
    # Never plan more minutes than the median block, including weeks with no recorded runs.
    weekly_minutes = statistics.median(sum(block.values()) for block in weeks)
    minutes = min(minutes, int(weekly_minutes / session_count))
    if state in {"calibrating", "below usual"} or garmin == "LOW":
        minutes = min(minutes, 20)
        return {"plan": f"Start with one easy {minutes}-minute outing if you feel well.",
                "basis": "Keep the first session conversational. Reassess how you feel "
                         "before planning the rest of the week.",
                "minutes": minutes, "sessions": 1, "history_run_days_by_week": run_days}
    sessions = "one easy run" if session_count == 1 else f"{session_count} easy runs"
    return {"plan": f"Plan {sessions} of about {minutes} minutes.",
            "basis": "Based on your last four weeks of runs. Keep the effort conversational "
                     "and take an easy or rest day between runs.",
            "minutes": minutes, "sessions": session_count, "history_run_days_by_week": run_days}
