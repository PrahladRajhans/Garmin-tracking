"""Local planning, check-ins and observed follow-up."""

from datetime import date, timedelta
from statistics import fmean, median

from garmin_mcp import sleep_review

KINDS = {"run": ("running", "trail_running", "track_running", "treadmill_running",
                 "virtual_running", "ultra_run"), "walk": ("walking", "hiking"),
         "strength": ("strength_training",)}


def save_checkin(conn, day, rested=None, energy=None, soreness=None, knee=None):
    values = (rested, energy, soreness, knee)
    if all(value is None for value in values):
        raise ValueError("Provide at least one rating.")
    for value, low, high in zip(values, (1, 0, 0, 0), (5, 10, 10, 10), strict=True):
        if value is not None and (type(value) is not int or not low <= value <= high):
            raise ValueError(f"Ratings must be whole numbers from {low} to {high}.")
    with conn:
        conn.execute("""INSERT INTO coach_checkin VALUES (?,?,?,?,?)
                        ON CONFLICT(day) DO UPDATE SET
                        rested=coalesce(excluded.rested,rested), energy=coalesce(excluded.energy,energy),
                        soreness=coalesce(excluded.soreness,soreness), knee=coalesce(excluded.knee,knee)""",
                     (day, *values))
    return {"day": day, "saved": True}


def knee_pause(conn, day):
    previous = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    row = conn.execute("SELECT knee FROM coach_checkin WHERE day=?", (previous,)).fetchone()
    return bool(row and row[0] is not None and row[0] >= 4)


def save_session(conn, day, kind, minutes, status="planned", session_id=None):
    if kind not in KINDS or status not in {"planned", "skipped"}:
        raise ValueError("Choose run, walk or strength and planned or skipped.")
    if type(minutes) is not int or not 5 <= minutes <= 240:
        raise ValueError("Choose a duration from 5 to 240 minutes.")
    with conn:
        if session_id is None:
            if status != "planned":
                raise ValueError("Provide the ID of an existing session to skip it.")
            cur = conn.execute(
                "INSERT INTO coach_session(day,kind,minutes,status) VALUES (?,?,?,?)",
                (day, kind, minutes, status))
            session_id = cur.lastrowid
        else:
            cur = conn.execute(
                "UPDATE coach_session SET day=?,kind=?,minutes=?,status=? WHERE id=?",
                (day, kind, minutes, status, session_id))
            if cur.rowcount != 1:
                raise ValueError("No session found with that ID.")
    return {"id": session_id, "day": day, "kind": kind, "minutes": minutes, "status": status}


def _sessions(conn, first, last, recorded_through):
    rows = list(conn.execute("SELECT id,day,kind,minutes,status FROM coach_session "
                             "WHERE day BETWEEN ? AND ? ORDER BY day,id", (first, last)))
    activities = list(conn.execute("SELECT activity_id,substr(start_time_local,1,10),type,duration_s "
                                   "FROM activities WHERE substr(start_time_local,1,10) BETWEEN ? AND ? "
                                   "AND duration_s>=300 ORDER BY start_time_local,activity_id",
                                   (first, min(last, recorded_through))))
    candidates = sorted(
        (abs(activity[3] / 60 - minutes), sid, activity[0], activity[3])
        for sid, day, kind, minutes, status in rows if status == "planned"
        for activity in activities if activity[1] == day and activity[2] in KINDS[kind]
    )
    used = set()
    assignments = {}
    for _, sid, activity_id, seconds in candidates:
        if sid not in assignments and activity_id not in used:
            assignments[sid] = activity_id, seconds
            used.add(activity_id)
    output = []
    for sid, day, kind, minutes, status in rows:
        match = assignments.get(sid)
        if match:
            status = "done"
        elif status == "planned" and day < recorded_through:
            status = "not recorded"
        output.append({"id": sid, "day": day, "kind": kind, "minutes": minutes, "status": status,
                       "activity_id": match[0] if match else None,
                       "done_minutes": round(match[1] / 60) if match else None})
    return output


def week(conn, end):
    day = date.fromisoformat(end)
    monday = day - timedelta(days=day.weekday())
    storage = conn.execute("SELECT 1 FROM sqlite_master WHERE name='daily' AND type='table'").fetchone()
    last_day = conn.execute("SELECT max(day) FROM daily WHERE day<=?", (end,)).fetchone()[0] if storage else None
    if conn.execute("SELECT 1 FROM meta WHERE key='sync_retry_required'").fetchone():
        last_day = None
    through = last_day or ""
    current = _sessions(conn, monday.isoformat(), (monday + timedelta(days=6)).isoformat(), through)
    last_week_end = (monday - timedelta(days=1)).isoformat()
    previous = _sessions(conn, (monday - timedelta(days=7)).isoformat(), last_week_end, through)
    planned = [row for row in previous if row["kind"] == "run"]
    adaptive = None
    if planned and through >= last_week_end:
        done = [row for row in planned if row["status"] == "done"]
        total = sum(row["done_minutes"] for row in done)
        if len(done) * 2 < len(planned):
            adaptive = "Repeat last week’s plan before adding sessions."
        else:
            cap = min(sum(row["minutes"] for row in planned), int(total * 1.1))
            adaptive = f"Use up to {cap} running minutes as a starting point."
        adaptive += f" Last week you logged {len(done)} of {len(planned)} scheduled runs."
    return {"sessions": current, "previous": previous, "adaptive": adaptive}


def movement(conn, end):
    day = date.fromisoformat(end)
    first = (day - timedelta(days=28)).isoformat()
    readings = dict(conn.execute("SELECT day,steps FROM daily WHERE day BETWEEN ? AND ? AND steps>=0",
                                 (first, end)))
    baseline = [steps for stamp, steps in readings.items() if stamp < end]
    if len(baseline) < 14:
        return None
    floor = int(median(baseline))
    if not floor:
        return None
    cursor = day if readings.get(end, 0) >= floor else day - timedelta(days=1)
    through = cursor.isoformat()
    streak = 0
    while readings.get(cursor.isoformat(), -1) >= floor:
        streak += 1
        cursor -= timedelta(days=1)
    return {"floor": floor, "steps": readings.get(end), "streak": streak, "through": through}


def wake_followup(nights, end):
    day = date.fromisoformat(end)
    monday = day - timedelta(days=day.weekday())
    reviewed = monday - timedelta(days=7)

    def block(first, last):
        return [(stamp, night) for stamp, night in nights.items()
                if first.isoformat() <= stamp < last.isoformat() and night["wake"] is not None]

    baseline = block(reviewed - timedelta(days=14), reviewed)
    prior = block(reviewed - timedelta(days=7), reviewed)
    recent = block(reviewed, monday)
    if len(baseline) < 5 or min(len(prior), len(recent)) < 4:
        return None
    anchor = median(sleep_review._unwrap([n["wake"] for _, n in baseline])) % 1440

    def on_target(block):
        return sum(abs((n["wake"] - anchor + 720) % 1440 - 720) <= 30 for _, n in block)

    sleep_change = round(60 * (fmean(n["hours"] for _, n in recent)
                              - fmean(n["hours"] for _, n in prior)))
    return {"anchor": sleep_review.clock(anchor), "hits": on_target(recent),
            "nights": len(recent), "prior_hits": on_target(prior), "prior_nights": len(prior),
            "sleep_change": sleep_change, "dates": [stamp for stamp, _ in recent]}


def rested_review(conn, end):
    scores = list(conn.execute("SELECT c.rested,s.score FROM coach_checkin c "
                               "JOIN sleep s USING(day) WHERE c.day<=? AND c.rested IS NOT NULL "
                               "AND s.score IS NOT NULL AND s.sleep_s>=10800", (end,)))
    if len(scores) < 14:
        return None
    low = [score for rested, score in scores if rested <= 2]
    high = [score for rested, score in scores if rested >= 4]
    if min(len(low), len(high)) < 3:
        return None
    return {"low": round(fmean(low)), "high": round(fmean(high)),
            "low_n": len(low), "high_n": len(high)}
