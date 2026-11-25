"""Bounded, descriptive comparisons from dated original wellness readings."""

import json
import math
from datetime import date, timedelta
from statistics import median

from garmin_mcp import normalize, training_plan

MIN_GROUP = 4


def _number(value, lower=0, upper=math.inf):
    return (type(value) in (int, float) and math.isfinite(value) and lower <= value <= upper)


def nap_days(conn, first, end):
    rows = conn.execute("""SELECT dataset,source,fetched_at,payload FROM raw_daily
                           WHERE dataset IN ('pa_sleep','sleep','ex_sleep') AND day BETWEEN ? AND ?
                           UNION ALL SELECT dataset,source,fetched_at,payload FROM raw_range
                           WHERE dataset='pa_sleep_summaries' AND start_day<=? AND end_day>=?""",
                        (first, end, end, first))
    selected = {}
    for dataset, source, fetched, raw in rows:
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            continue
        rank = (normalize.PRIORITY.get(source, 9), dataset == "pa_sleep_summaries")
        for item in normalize._records(payload):
            night = item.get("dailySleepDTO", item)
            if not isinstance(night, dict):
                continue
            day = normalize._calendar_day(night.get("calendarDate"))
            seconds = night.get("napTimeSeconds")
            if not day or not first <= day <= end or not _number(seconds, 0, 86400):
                continue
            earlier = selected.get(day)
            if not earlier or rank < earlier[0] or (rank == earlier[0] and fetched > earlier[1]):
                selected[day] = (rank, fetched, seconds)
    return {day: row[2] for day, row in selected.items()}


def _comparison(low, high):
    if min(len(low), len(high)) < MIN_GROUP:
        return None
    return {"first": median(low), "second": median(high), "first_count": len(low), "second_count": len(high)}


def collect(conn, end):
    day = date.fromisoformat(end)
    first = (day - timedelta(days=28)).isoformat()
    charged = []
    drained = []
    charge = ([], [])
    drain = ([], [])
    nap_drain = ([], [])
    naps = nap_days(conn, first, end)
    running = training_plan.RUN_ACTIVITY_TYPES
    marks = ",".join("?" for _ in running)
    run_days = {row[0] for row in conn.execute(
        f"SELECT DISTINCT substr(start_time_local,1,10) FROM activities WHERE type IN ({marks}) "
        "AND substr(start_time_local,1,10)>=? AND substr(start_time_local,1,10)<?",
        (*running, first, end))}
    for stamp, added, spent, hours, need in conn.execute(
            "SELECT daily.day, body_battery_charged, body_battery_drained, sleep_s/3600.0,"
            "sleep_need_min/60.0 FROM daily LEFT JOIN sleep USING(day) WHERE daily.day>=? AND daily.day<?",
            (first, end)):
        # Totals are across the recorded calendar day. They are not changes during sleep or a run.
        if _number(added):
            charged.append(added)
            if _number(hours, 3, 24) and _number(need, 3, 15):
                charge[int(hours >= need)].append(added)
        if _number(spent):
            drained.append(spent)
            drain[int(stamp in run_days)].append(spent)
            if stamp in naps:
                nap_drain[int(naps[stamp] > 0)].append(spent)
    return {"first": first, "end": end,
            "charge": (median(charged), len(charged)) if charged else None,
            "drain": (median(drained), len(drained)) if drained else None,
            "sleep_compare": _comparison(*charge), "run_compare": _comparison(*drain),
            "nap_compare": _comparison(*nap_drain),
            "nap_days": len(naps), "nap_positive_days": sum(value > 0 for value in naps.values()),
            "latest_nap_s": naps.get(end)}
