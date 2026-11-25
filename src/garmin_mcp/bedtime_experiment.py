"""Save an accepted sleep target for a week and compare the dated results."""

import re
from datetime import date, timedelta
from statistics import fmean

from garmin_mcp import recovery, sleep_review


def _week(end):
    day = date.fromisoformat(end)
    return day - timedelta(days=day.weekday())


def _minutes(value):
    # time.fromisoformat is too lenient here: Python 3.14+ accepts "24:00" and "T1234".
    match = isinstance(value, str) and re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", value)
    if not match:
        raise ValueError("Use HH:MM for the bedtime target.")
    return 60 * int(match[1]) + int(match[2])


def _overnight(value):
    return (value - 720) % 1440


def _review(conn, nights, monday, target, end):
    first, last = monday.isoformat(), min(end, (monday + timedelta(days=6)).isoformat())
    timed = [(day, night) for day, night in nights.items()
             if first <= day <= last and night["bed"] is not None]
    hrv = recovery.nightly_hrv(conn, first, last) if timed else {}
    readiness = {day: recovery.garmin_score(score) for day, score in conn.execute(
        "SELECT day, score FROM readiness WHERE day BETWEEN ? AND ?", (first, last))} if timed else {}
    on_time, later = [], []
    for day, night in timed:
        met = _overnight(night["bed"]) <= _overnight(target)
        group = on_time if met else later
        group.append({"day": day, "on_time": met, "hours": night["hours"], "sleep_score": night["score"],
                      "hrv_ms": hrv.get(day), "readiness": readiness.get(day)})
    comparisons = {}
    for key in ("hours", "sleep_score", "hrv_ms", "readiness"):
        a, b = ([row[key] for row in group if row[key] is not None] for group in (on_time, later))
        if min(len(a), len(b)) >= 3:
            comparisons[key] = {"on_time": round(fmean(a), 1), "later": round(fmean(b), 1),
                                "on_time_n": len(a), "later_n": len(b)}
    return {"week_start": first, "target": sleep_review.clock(target),
            "on_time": len(on_time), "recorded": len(timed),
            "nights": sorted(on_time + later, key=lambda row: row["day"]), "comparisons": comparisons}


def status(conn, end, review, need_h):
    monday = _week(end)
    prior = monday - timedelta(days=7)
    records = dict(conn.execute("SELECT week_start, target_min FROM bedtime_targets WHERE week_start IN (?,?)",
                                (monday.isoformat(), prior.isoformat())))
    anchor = review["anchor"]
    suggestion = anchor.get("bedtime")
    current = previous = None
    if monday.isoformat() in records:
        current = _review(conn, review["nights"], monday, records[monday.isoformat()], end)
    if prior.isoformat() in records:
        target = records[prior.isoformat()]
        previous = _review(conn, review["nights"], prior, target, end)
        slot = _overnight(target)
        if previous["recorded"] >= 4:
            if previous["on_time"] * 2 < previous["recorded"]:
                slot = min(1439, slot + 15)
            elif anchor.get("wake"):
                limit = _overnight(_minutes(anchor["wake"]) - round(need_h * 60))
                if limit < slot:
                    slot = max(limit, slot - 15)
        suggestion = sleep_review.clock(720 + slot)
    return {"current": current, "previous": previous, "suggestion": suggestion}


def accept(conn, end, bedtime):
    target = _minutes(bedtime)
    week_start = _week(end).isoformat()
    with conn:
        conn.execute("INSERT OR IGNORE INTO bedtime_targets VALUES (?,?)", (week_start, target))
        existing = conn.execute("SELECT target_min FROM bedtime_targets WHERE week_start=?", (week_start,)).fetchone()[0]
        if target != existing:
            raise ValueError("This week's target is already saved. Start a new target next week.")
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('dashboard_rebuild_pending','1')")
    return {"week_start": week_start, "target": sleep_review.clock(target)}
