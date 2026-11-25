"""Summarize complete nights and propose a small, week-stable timing adjustment."""

import json
from datetime import UTC, date, datetime, timedelta
from statistics import fmean, median, pstdev

from garmin_mcp import recovery, wellness_timeline


def _timestamp(value):
    if not isinstance(value, str) or not any(separator in value for separator in ("T", "t", " ")):
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _clock_minutes(value, zone):
    if moment := _timestamp(value):
        local = moment.astimezone(zone)
        return local.hour * 60 + local.minute
    return None


def _timeline(levels, start, end):
    if not start or not end or not timedelta(0) < end - start <= timedelta(hours=24):
        return []
    names = {0: "deep", 1: "light", 2: "rem", 3: "awake"}
    samples = []
    for level in levels:
        try:
            stage = level["activityLevel"]
            if type(stage) is not int:
                continue
            name = names[stage]
            low, high = _timestamp(level["startGMT"]), _timestamp(level["endGMT"])
        except (KeyError, TypeError):
            continue
        if low and high and start <= low < high <= end:
            samples.append((low, high, name))
    result = []
    for low, high, name in sorted(samples):
        if result and low < result[-1][1]:
            return []
        if result and low == result[-1][1] and name == result[-1][2]:
            result[-1] = (result[-1][0], high, name)
        else:
            result.append((low, high, name))
    return [((low - start) / (end - start), (high - low) / (end - start), name)
            for low, high, name in result]


def _unwrap(values):
    # Cut the clock at its largest unobserved interval so midnight is never a boundary.
    ordered = sorted(values)
    following = ordered[1:] + [ordered[0] + 1440]
    split = max(range(len(ordered)), key=lambda i: following[i] - ordered[i])
    return ordered[split + 1:] + [v + 1440 for v in ordered[:split + 1]]


def clock(minutes):
    h, m = divmod(round(minutes) % 1440, 60)
    return f"{h:02d}:{m:02d}"


def trend_context(chart, nights, *, monthly=False, metric="hours"):
    """Trailing average and a separately qualified comparison range for sleep charts."""
    trend = {}
    if monthly:
        for i in range(2, len(chart)):
            values = [v for _, v in chart[i - 2:i + 1] if v is not None]
            if len(values) == 3:
                trend[chart[i][0]] = fmean(values)
        prior = [value for _, value in chart if value is not None]
        label, minimum = "Middle half of displayed months", 8
    else:
        for day, _ in chart:
            end = date.fromisoformat(day)
            dates = [(end - timedelta(days=i)).isoformat() for i in range(7)]
            values = [value for d in dates if (value := nights.get(d, {}).get(metric)) is not None]
            if len(values) >= 4:
                trend[day] = fmean(values)
        first = date.fromisoformat(chart[0][0]) if chart else None
        prior = [value for i in range(1, 29) if first
                 and (value := nights.get((first - timedelta(days=i)).isoformat(), {}).get(metric)) is not None]
        label, minimum = "Middle half of nights in the prior 28 days", 14
    band = None
    if len(prior) >= minimum:
        ordered = sorted(prior)
        band = (ordered[len(ordered) // 4], ordered[(len(ordered) - 1) * 3 // 4])
    return {"trend": trend, "band": band, "band_label": label,
            "trend_label": "3-month average" if monthly else "7-day average"}


def _monthly(chart):
    buckets = {}
    for day, value in chart:
        bucket = buckets.setdefault(day[:7], [])
        if value is not None:
            bucket.append(value)
    return [(month, fmean(values) if values else None) for month, values in buckets.items()]


def collect(conn, end, zone, need_h):
    end_date = date.fromisoformat(end)
    start = (end_date - timedelta(days=364)).isoformat()
    nights = {}
    zones = wellness_timeline.day_zones(conn, zone, start, end)
    for day, seconds, score, start_at, wake_at, deep, light, rem, awake in conn.execute(
            "SELECT day,sleep_s,score,sleep_start,sleep_end,deep_s,light_s,rem_s,awake_s "
            "FROM sleep WHERE day BETWEEN ? AND ? AND sleep_s>=10800 ORDER BY day", (start, end)):
        if not recovery._positive(seconds):
            continue
        nights[day] = {"hours": seconds / 3600, "score": recovery.garmin_score(score),
                       "bed": _clock_minutes(start_at, zones.get(day, zone)),
                       "wake": _clock_minutes(wake_at, zones.get(day, zone)),
                       "window": (start_at, wake_at),
                       "stages": {"Deep": deep, "Light": light, "REM": rem, "Awake": awake}}
    # Detail is useful on recent nights only. Older periods show aggregates.
    recent_first = (end_date - timedelta(days=29)).isoformat()
    newest = max(nights, default=end)
    for day, payload in conn.execute(
            "SELECT day,payload FROM raw_daily WHERE dataset='sleep' AND "
            "((day BETWEEN ? AND ?) OR day=?)", (recent_first, end, newest)):
        if day in nights:
            try:
                raw = json.loads(payload)
            except (TypeError, ValueError):
                continue  # A missing source timeline should not hide a usable normalized night.
            levels = raw.get("sleepLevels") if isinstance(raw, dict) else None
            if isinstance(levels, list):
                start_at, wake_at = nights[day]["window"]
                nights[day]["timeline"] = _timeline(levels, _timestamp(start_at), _timestamp(wake_at))
    windows = {}
    for size in (7, 30, 365):
        first = end_date - timedelta(days=size - 1)
        rows = [(day, n) for day, n in nights.items() if day >= first.isoformat()]
        if not rows:
            continue
        chart = [(day.isoformat(), nights.get(day.isoformat(), {}).get("hours"))
                 for day in (first + timedelta(days=i) for i in range(size))]
        score_chart = [(day, nights.get(day, {}).get("score")) for day, _ in chart]
        if size == 365:
            chart, score_chart = _monthly(chart), _monthly(score_chart)
        scored = [n["score"] for _, n in rows if n["score"] is not None]
        windows[size] = {"nights": len(rows), "hours": fmean(n["hours"] for _, n in rows),
                         "score": fmean(scored) if scored else None,
                         "scored": len(scored), "chart": chart, "score_chart": score_chart}
    wakes = [n["wake"] for day, n in nights.items()
             if day >= (end_date - timedelta(days=13)).isoformat() and n["wake"] is not None]
    anchor = {}
    if len(wakes) >= 5:
        timings = _unwrap(wakes)
        wake = median(timings) % 1440
        anchor = {"wake": clock(wake), "spread": round(pstdev(timings)), "nights": len(wakes)}
        monday = end_date - timedelta(days=end_date.weekday())

        def beds(weeks_back):
            low = monday - timedelta(weeks=weeks_back)
            high = low + timedelta(days=7)
            return [(night["bed"] - 720) % 1440 for day, night in nights.items()
                    if low.isoformat() <= day < high.isoformat() and night["bed"] is not None]

        last, earlier = beds(1), beds(2)
        fixed_wakes = [n["wake"] for day, n in nights.items()
                       if (monday - timedelta(days=14)).isoformat() <= day < monday.isoformat()
                       and n["wake"] is not None]
        if len(last) >= 4 and len(fixed_wakes) >= 5:
            fixed_timings = _unwrap(fixed_wakes)
            fixed_wake = median(fixed_timings) % 1440
            anchor.update(wake=clock(fixed_wake), spread=round(pstdev(fixed_timings)), nights=len(fixed_timings))
            baseline = median(last)
            desired = (fixed_wake - need_h * 60 - 720) % 1440
            if 0 <= desired < baseline < 1320:
                previous = max(desired, median(earlier) - 15) if len(earlier) >= 4 else None
                missed = previous is not None and sum(b > previous for b in last) > len(last) / 2
                anchor["bedtime"] = clock(720 + (baseline if missed else max(desired, baseline - 15)))
                anchor["held"] = missed
    recent = [n["hours"] for day, n in nights.items()
              if day >= (end_date - timedelta(days=6)).isoformat()]
    prior = [n["hours"] for day, n in nights.items()
             if (end_date - timedelta(days=13)).isoformat() <= day
             < (end_date - timedelta(days=6)).isoformat()]
    change = round((fmean(recent) - fmean(prior)) * 60) if min(len(recent), len(prior)) >= 4 else None
    return {"nights": nights, "windows": windows, "anchor": anchor, "week_change_min": change}
