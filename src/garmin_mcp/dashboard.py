"""Personal dashboard: multi-page, one self-contained HTML file with offline controls.

Pages are sections addressed by links (#today, #sleep, #run-<id>, ...). CSS `:target` shows one
at a time, including in readers that do not run scripts. Charts are inline SVG. A bundled
script handles point selection, theme and active navigation. Built from the same functions as the MCP
tools, so the dashboard and Claude always agree. Design rules: DASHBOARD_PLAN.md sections 6-8.
Output: $GARMIN_DATA_DIR/dashboard/index.html (+ a copy in iCloud Drive/Garmin if it exists).
"""

from __future__ import annotations

import html
import json
import math
import os
import re
import sqlite3
import stat
import tempfile
import warnings
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from statistics import median
from typing import Any

from garmin_mcp import (
    __version__,
    baseline,
    bedtime_experiment,
    coach_loop,
    coach_review,
    coaching,
    conditions,
    dashboard_history,
    deep_insight,
    engine,
    environment_review,
    health,
    insights,
    loads,
    narrator,
    norms,
    readiness_benchmark,
    reading_availability,
    recovery,
    route_review,
    run_evidence,
    running,
    running_block,
    scores,
    signal_context,
    sleep_review,
    trials,
    wellness_review,
    wellness_timeline,
)
from garmin_mcp.dashboard_interaction import CONTENT_POLICY, SCRIPT

SNAPSHOT_PREFIX = f"{__version__}/coach-sleep-2/"

W = 340  # SVG viewBox width: phone-first, text stays ~11-16 px from phone to desktop


def _e(v: Any) -> str:
    return html.escape("" if v is None else str(v))


def _f(v: Any, nd: int = 0, unit: str = "") -> str:
    if not isinstance(v, (int, float)) or not math.isfinite(v):
        return "–"
    return f"{v:,.{nd}f}{unit}"


# =============================================================================== data
def _last_full_night(conn: sqlite3.Connection, end: str) -> str | None:
    row = conn.execute("SELECT MAX(day) FROM sleep WHERE day <= ? AND sleep_s BETWEEN 3*3600 AND 24*3600",
                       (end,)).fetchone()
    return row[0] if row else None


TRACE_RUNS = 3        # second-by-second timelines are kept for the latest runs only
TRACE_POINTS = 200    # about one every 9 s on a 30-minute run
SCATTER_POINTS = 120  # most recent days drawn per pattern; statistics use every day


def _latest_observation(conn: sqlite3.Connection, through: str) -> str | None:
    days = [conn.execute(f"SELECT MAX(day) FROM {table} WHERE day<=?", (through,)).fetchone()[0]
            for table in ("daily", "sleep", "hrv", "health_status", "readiness") if _has(conn, table)]
    days.append(conn.execute("SELECT MAX(substr(start_time_local,1,10)) FROM activities "
                             "WHERE substr(start_time_local,1,10)<=?", (through,)).fetchone()[0])
    return max((day for day in days if day), default=None)


def collect(conn: sqlite3.Connection, end: str | None = None) -> dict[str, Any]:
    zone = engine._tz(conn)
    today = datetime.now(zone).date()
    explicit_date = end is not None
    latest = _latest_observation(conn, end or today.isoformat()) if _has(conn, "daily") else None
    if not latest:
        return {"available": False, "reason": "No Garmin data is available yet. Sync or import "
                "your history on the Mac to build your dashboard."}
    end = end or latest
    e = date.fromisoformat(end)

    def lo(n: int) -> str:
        return (e - timedelta(days=n - 1)).isoformat()

    night = _last_full_night(conn, end)
    night_summary = conn.execute("SELECT sleep_s/3600.0, score FROM sleep WHERE day=?",
                                 (night,)).fetchone() if night else None
    ds = scores.daily_scores(conn, end)
    signals = signal_context.collect(conn, end)
    explore = engine.explore(conn, end, 365, 8)
    hrv = recovery.load_series(conn, end, 67)["hrv"]
    previous_week = (e - timedelta(days=7)).isoformat()
    hrv_info = recovery.hrv_status(hrv, end)
    hrv_info["previous_average"] = recovery.hrv_status(hrv, previous_week).get("rolling_7d_ms")
    runs = []
    read_run = lru_cache(maxsize=160)(coaching.run_metrics)
    for aid, start, dist in conn.execute(
            "SELECT activity_id, start_time_local, distance_m FROM activities WHERE type LIKE "
            "'%run%' AND fit_parsed=1 AND substr(start_time_local,1,10)<=? "
            "ORDER BY julianday(start_time_local) DESC LIMIT 8", (end,)):
        b = running.running_breakdown(conn, aid, _weight(conn, start[:10]), read_metrics=read_run, end=end)
        if b.get("available"):
            interval = max(5, math.ceil((b["pacing"].get("recorded_elapsed_s") or 0)
                                         / TRACE_POINTS))
            trace = (coaching.activity_stream(conn, aid, interval)
                     if len(runs) < TRACE_RUNS else {})  # older runs: summary page only
            row = conn.execute("SELECT hr_zone_bounds FROM fit_zones WHERE activity_id=?",
                               (aid,)).fetchone()
            if row:
                b["hr_zone_bounds"] = _hr_zone_bounds(row[0])
            b.update(date=start[:10], start_local=start, km=round((dist or 0) / 1000, 2),
                     trace=trace)
            runs.append(b)
    calendar = dashboard_history.collect(conn, end, zone)
    run_ids = {run["activity_id"] for run in runs}
    workouts = [workout for day in sorted(calendar["detail_days"], reverse=True)
                for workout in calendar["days"][day].get("activities", [])
                if workout["id"] not in run_ids][:8]
    need_h = ds["sleep"]["need_h"] or recovery.DEFAULT_SLEEP_NEED_H
    sleep_data = sleep_review.collect(conn, end, zone, need_h)
    if runs:
        runs[0]["route_review"] = route_review.compare(conn, runs[0])
    brief = insights.daily_brief(conn, end, signals=signals, patterns=explore["pairs"])
    retry = conn.execute("SELECT 1 FROM meta WHERE key='sync_retry_required'").fetchone() is not None
    availability_day = end if explicit_date else today.isoformat()
    availability = reading_availability.collect(conn, availability_day, zone, brief=brief, retry=retry)
    return {
        "day_zones": wellness_timeline.day_zones(conn, zone),
        "_conn": conn, "end": end, "zone": zone, "scores": ds,
        "sleep_review": sleep_data,
        "sleep_shortfall": recovery.sleep_shortfall_review(conn, end),
        "wellness_review": wellness_review.collect(conn, end),
        "bedtime_experiment": bedtime_experiment.status(conn, end, sleep_data, need_h),
        "wake_followup": coach_loop.wake_followup(sleep_data["nights"], end),
        "rested_review": coach_loop.rested_review(conn, end),
        "tag_review": engine.tag_impact(conn, end)["tags"],
        "planned_week": coach_loop.week(conn, end),
        "movement": coach_loop.movement(conn, end),
        "older_snapshot": e != today,
        "history": scores.history(conn, end, 14),
        "brief": brief,
        "reading_availability": availability,
        "guidance_evidence": coach_review.decision_evidence(end, brief, signals),
        "night": health.sleep_breakdown(conn, night) if night else None,
        "night_summary": night_summary,
        "bedroom_conditions": environment_review.bedroom(conn, end),
        "outdoor_patterns": environment_review.outdoor_patterns(conn, end, read_metrics=read_run),
        "hrv": recovery.recovery_trend(conn, end, 60)["days"],
        "signals": signals,
        "hrv_context": hrv_info,
        "fitness": conn.execute("SELECT day, ctl, atl FROM fitness WHERE day BETWEEN ? AND ? "
                                "ORDER BY day", (lo(120), end)).fetchall()
        if _has(conn, "fitness") else [],
        "weekly_review": insights.weekly_review(conn, end)
        if _has(conn, "fitness") and _has(conn, "activity_load") else None,
        "weekly_load": _weekly_load(conn, end),
        "readiness_benchmark": readiness_benchmark.benchmark(conn, end, read_metrics=read_run),
        "shifts": health.shifts(conn, end),
        "ageing": health.pace_of_ageing(conn, end),
        "marathon": health.marathon_shape(conn, end),
        "fitness_age": coaching.fitness_age(conn, end),
        "predictions": loads.race_predictions(conn, end, 180),
        "month": health.monthly_report(conn, _prev_month(end)),
        "calendar": calendar, "workouts": workouts,
        "last_full_sync": _last_full_sync(conn, zone),
        "trial": trials.status(conn, through=(e, zone) if e != today else None),
        "runs": runs, "form": running.form_trends(conn, 40, read_metrics=read_run, end=end),
        "running_block": running_block.collect(conn, end, read_metrics=read_run, latest=runs[0] if runs else None),
        "explore": explore,
        "tests": running.test_runs(conn, read_metrics=read_run, end=end),
        "vo2_reference": norms.comparison(conn, end),
        "sync_retry_required": retry,
    }


def _last_full_sync(conn: sqlite3.Connection, zone) -> str | None:
    timestamp = reading_availability.complete_sync(conn, datetime.now(UTC))
    return timestamp.astimezone(zone).strftime("%-d %b %Y, %H:%M %Z") if timestamp else None


def _has(conn: sqlite3.Connection, t: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone() is not None


def _weight(conn: sqlite3.Connection, end: str) -> float | None:
    if not _has(conn, "fit_profile"):
        return None
    row = conn.execute("SELECT p.weight_kg FROM fit_profile p JOIN activities a USING(activity_id) "
                       "WHERE p.weight_kg > 0 AND substr(a.start_time_local,1,10)<=? "
                       "ORDER BY julianday(a.start_time_local) DESC, a.activity_id DESC LIMIT 1",
                       (end,)).fetchone()
    return row[0] if row else None


def _prev_month(end: str) -> str:
    y, m = int(end[:4]), int(end[5:7])
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def _weekly_load(conn: sqlite3.Connection, end: str, weeks: int = 12) -> list[tuple[str, float | None]]:
    if not _has(conn, "fitness"):
        return []
    e = date.fromisoformat(end)
    monday = e - timedelta(days=e.weekday())
    out = []
    for i in range(weeks - 1, -1, -1):
        a = monday - timedelta(weeks=i)
        v = loads.total_daily_load(conn, a.isoformat(), min(e, a + timedelta(days=6)).isoformat())
        out.append((a.isoformat(), round(v) if v is not None else None))
    return out


# =============================================================================== svg kit
ICONS = {
    "home": "M2.5 7.2 8 2.5l5.5 4.7v6.3h-4v-4h-3v4h-4z",
    "run": "M8.2 4.8a1.65 1.65 0 1 0 0-3.3 1.65 1.65 0 0 0 0 3.3M5 7.5l3-1.3 2 2.3h3M8 6.2 6.5 10l3 1.5V15M6.5 10l-2 3H1.5",
    "trend": "M2.5 2.5v11h11M5 10l3-3 2 1.5 3.5-4",
    "heart": "M8 13.5s-5-3.1-5-6.6A2.9 2.9 0 0 1 8 5a2.9 2.9 0 0 1 5 1.9c0 3.5-5 6.6-5 6.6z",
    "moon": "M12.5 9.5A5 5 0 0 1 6.5 3.5a5 5 0 1 0 6 6z",
    "bolt": "M9 1.5 3.5 9H8l-1 5.5L12.5 7H8z",
    "up": "M8 12.5v-9M4.5 7 8 3.5 11.5 7",
    "down": "M8 3.5v9M4.5 9 8 12.5 11.5 9",
    "ok": "M3.5 8.5 6.5 11.5 12.5 4.5",
    "back": "M10 3.5 5.5 8l4.5 4.5",
    "chev": "M6 3.5 10.5 8 6 12.5",
}


def icon(name: str, cls: str = "") -> str:
    return (f'<svg class="ic {cls}" viewBox="0 0 16 16" aria-hidden="true"><path d="'
            f'{ICONS[name]}"/></svg>')


def _scale(vals: list[float], pad: float = 0.08) -> tuple[float, float]:
    lo, hi = min(vals), max(vals)
    if hi == lo:
        hi, lo = hi + 1, lo - 1
    p = (hi - lo) * pad
    return lo - p, hi + p


def _ticks(lo: float, hi: float) -> list[float]:
    interval = (hi - lo) / 3
    power = 10 ** math.floor(math.log10(interval))
    step = next(n * power for n in (1, 2, 2.5, 5, 10) if n * power >= interval)
    return [round(i * step, 9) for i in range(math.floor(lo / step), math.ceil(hi / step) + 1)]


def _tick_number(value: float, signed: bool = False) -> str:
    return f"{value:+,g}" if signed and value else f"{value:,g}"


def _point(x: float, y: float, label: str, value: str, cls: str = "hit",
           *, condition_index: int | None = None) -> str:
    context = f' data-condition-index="{condition_index}"' if condition_index is not None else ""
    return (f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.4" class="{cls}" data-point '
            f'data-title="{_e(label)}" data-value="{_e(value)}"{context}>'
            f'<title data-native>{_e(label)} · {_e(value)}</title></circle>')


def _chart(kind: str, parts: list[str], w: int, h: int, limits: tuple,
           x_label: str, y_label: str, controls: str = "",
           *, condition_labels: list[str] | None = None,
           compact: bool = False, dense: bool = False, static_readings: bool = False) -> str:
    left, right, top, bottom = limits
    overlay = (f'<g class="chart-cursor" aria-hidden="true">'
               f'<line class="cursor-x" y1="{top}" y2="{bottom}"/>'
               f'<line class="cursor-y" x1="{left}" x2="{right}"/>'
               '<circle r="3.3"/></g>')
    caption = '<figcaption class="chart-readout"><strong></strong><span></span></figcaption>'
    lookup = f' data-conditions="{_e(json.dumps(condition_labels, ensure_ascii=False))}"' if condition_labels else ""
    layout = (" chart-compact" if compact else "") + (" chart-dense" if dense else "")
    readings = " data-static-readings" if static_readings else ""
    return (f'<figure class="chart-interaction{layout}" data-chart="{kind}"{lookup}{readings}>'
            f'{controls}<span class="sr-only" role="status" aria-atomic="true"></span>'
            f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" '
            f'aria-label="{_e(y_label)} by {_e(x_label)}" aria-describedby="chart-help">'
            f'{"".join(parts)}{overlay}</svg>{caption}</figure>')


def _horizontal_scale(ticks: list[float], left: int, right: int, y, fmt) -> list[str]:
    return [f'<line x1="{left}" x2="{right}" y1="{y(v):.2f}" y2="{y(v):.2f}" class="grid"/>'
            f'<text x="{left - 7}" y="{y(v) + 4:.2f}" class="tick" text-anchor="end">'
            f'{_e(fmt(v))}</text>' for v in ticks]


def _axes(left: int, right: int, top: int, bottom: int, h: int,
          x_label: str, y_label: str) -> list[str]:
    return [
        f'<path class="axis" d="M{left},{top}V{bottom}H{right}"/>',
        f'<text x="{left}" y="{top - 9}" class="axis-label">{_e(y_label)}</text>',
        (f'<text x="{(left + right) / 2}" y="{h - 6}" text-anchor="middle" class="axis-label">'
         f'{_e(x_label)}</text>'),
    ]


def _x_ticks(labels: list[str], x, bottom: int, wide: bool, *, weekdays: bool = False) -> list[str]:
    if weekdays:
        return [f'<text x="{x(i):.2f}" y="{bottom + 13}" text-anchor="middle" class="tick day-tick">'
                f'<tspan x="{x(i):.2f}">{day:%a}</tspan>'
                f'<tspan x="{x(i):.2f}" dy="12">{day:%d %b}</tspan></text>'
                for i, label in enumerate(labels) if (day := date.fromisoformat(label))]
    if len(labels) <= 3:
        indices = range(len(labels))
    else:
        divisions = 4 if wide and len(labels) >= 6 else 2
        indices = sorted({round(i * (len(labels) - 1) / divisions) for i in range(divisions + 1)})
    return [f'<text x="{x(i):.2f}" y="{bottom + 17}" text-anchor="middle" class="tick">'
            f'{_e(_short(labels[i]))}</text>' for i in indices]


def _smooth_line(labels: list[str], values: dict[str, float], x, y, gap_at=None) -> str:
    path = []
    for i, label in enumerate(labels):
        if label in values:
            join = i and labels[i - 1] in values and not (gap_at and gap_at(i))
            path.append(f'{"L" if join else "M"}'
                        f'{x(i):.2f},{y(values[label]):.2f}')
    return f'<path class="moving-average" d="{" ".join(path)}"/>' if path else ""


def line_chart(points: list[tuple[str, float]], unit: str = "", band: tuple | None = None,
               band_series: list[tuple[float, float] | None] | None = None, h: int = 190,
               nd: int = 0, cls: str = "s1", w: int = W, fmt: Any = None,
               x_label: str = "Date", y_label: str = "Value",
               averages: dict[str, float] | None = None, break_gaps: bool = False,
               elapsed: dict[str, float] | None = None, *, connect_points: bool = True,
               reference: float | None = None, band_label: str = "Your usual range",
               rate_range: bool = False, zone_metric: str | None = None,
               details: dict[str, str] | None = None, max_gap: float | None = None,
               whiskers: bool = False, weekdays: bool = False, average_label: str = "7-day average",
               guides: dict[float, str] | None = None,
               time_ticks: list[tuple[str, float]] | None = None,
               value_ticks: tuple[int, ...] = ()) -> str:
    """Date spacing reflects elapsed days. Missing observations stay out of the cursor."""
    bounds = band_series if band_series and len(band_series) == len(points) else [band] * len(points)
    rows = [(label, value, interval) for (label, value), interval in
            zip(points, bounds, strict=True) if isinstance(value, (int, float)) and math.isfinite(value)]
    if not rows:
        return '<p class="empty">No measurements recorded for this chart.</p>'
    days = None
    if elapsed is not None:
        rows.sort(key=lambda row: elapsed[row[0]])
    else:
        try:
            rows.sort(key=lambda row: date.fromisoformat(row[0][:10]))
            days = [date.fromisoformat(row[0][:10]).toordinal() for row in rows]
        except ValueError:
            pass
    values = [v for _, v, _ in rows]
    values.extend(v for _, _, interval in rows if interval for v in interval)
    averages = averages or {}
    labels = [label for label, _, _ in rows]
    values.extend(averages[d] for d in labels if d in averages)
    if reference is not None:
        values.append(reference)
    ticks = value_ticks or _ticks(*_scale(values))
    h = max(h, 184)
    left, right, top, bottom = 51, w - 31, 29, h - 49
    positions = [elapsed[label] for label in labels] if elapsed is not None else days
    gap_limit = max_gap if max_gap is not None else 1 if break_gaps and days else None

    def gap_at(i):
        return positions is not None and gap_limit is not None and positions[i] - positions[i - 1] > gap_limit

    calendar_ticks = sorted(label for label, _ in points) if weekdays else []
    if calendar_ticks:
        first, last = (date.fromisoformat(label).toordinal() for label in
                       (calendar_ticks[0], calendar_ticks[-1]))

        def calendar_x(label):
            return left + (right - left) * ((date.fromisoformat(label).toordinal() - first)
                                           / (last - first) if last > first else .5)

    def elapsed_x(minute):
        first, last = time_ticks[0][1], time_ticks[-1][1]
        return left + (right - left) * (minute - first) / (last - first)

    def x(i: int) -> float:
        if time_ticks:
            return elapsed_x(positions[i])
        if calendar_ticks:
            return calendar_x(labels[i])
        if len(rows) == 1:
            return (left + right) / 2
        if positions and positions[-1] > positions[0]:
            return left + (right - left) * (positions[i] - positions[0]) / (positions[-1] - positions[0])
        return left + (right - left) * i / (len(rows) - 1)

    def y(v: float) -> float:
        return bottom - (bottom - top) * (v - ticks[0]) / (ticks[-1] - ticks[0])

    g = _horizontal_scale(ticks, left, right, y, fmt or _tick_number)
    if guides and elapsed and positions[0] < positions[-1]:
        start, end = positions[0], positions[-1]
        for minute, label in guides.items():
            if start <= minute <= end:
                gx = elapsed_x(minute) if time_ticks else left + (right - left) * (minute - start) / (end - start)
                g.append(f'<line class="timeline-guide" x1="{gx:.2f}" x2="{gx:.2f}" '
                         f'y1="{top}" y2="{bottom}"><title>{_e(label)}</title></line>')
    if band:
        g.append(f'<rect class="band" x="{left}" y="{y(band[1]):.2f}" width="{right - left}" '
                 f'height="{max(0, y(band[0]) - y(band[1])):.2f}"><title>{_e(band_label)}</title></rect>')
    elif band_series and whiskers:
        for i, (_, _, interval) in enumerate(rows):
            if interval:
                g.append(f'<line class="observed-span" x1="{x(i):.2f}" x2="{x(i):.2f}" '
                         f'y1="{y(interval[0]):.2f}" y2="{y(interval[1]):.2f}"/>')
    elif band_series:
        # Draw the envelope only across adjacent valid bounds.
        for i, (a, b) in enumerate(pairwise(rows)):
            if a[2] and b[2] and not gap_at(i + 1):
                g.append(f'<polygon class="band" points="{x(i):.2f},{y(a[2][1]):.2f} '
                         f'{x(i + 1):.2f},{y(b[2][1]):.2f} {x(i + 1):.2f},{y(b[2][0]):.2f} '
                         f'{x(i):.2f},{y(a[2][0]):.2f}"/>')
    g += _axes(left, right, top, bottom, h, x_label, y_label)
    locations = []
    for i, (_, value, _) in enumerate(rows):
        gap = i and gap_at(i)
        locations.append(f'{"M" if i == 0 or gap else "L"}{x(i):.2f},{y(value):.2f}')
    if connect_points:
        g.append(f'<path d="{" ".join(locations)}" class="ln {cls}{" context" if break_gaps else ""}"/>')
    if reference is not None:
        yr = y(reference)
        g.append(f'<line x1="{left}" x2="{right}" y1="{yr:.2f}" y2="{yr:.2f}" class="ref"/>')
    g.append(_smooth_line(labels, averages, x, y, gap_at))
    for i, (label, value, interval) in enumerate(rows):
        display = fmt(value) if fmt else _f(value, nd, unit)
        if label in averages:
            display += f" · {average_label.lower()} {_f(averages[label], nd, unit)}"
        if interval:
            display += f" · {band_label.lower()} {_f(interval[0], nd)}–{_f(interval[1], nd, unit)}"
        if details and label in details:
            display += f" · {details[label]}"
        marker = ("dot s1" if i == len(rows) - 1 else
                  "context-dot" if break_gaps or not connect_points else "hit")
        if rate_range and interval:
            if value < interval[0]:
                colour, status = "orange", "below usual"
            elif value > interval[1]:
                colour, status = "blue", "above usual"
            else:
                colour, status = "green", "within usual range"
            marker = f"zone-dot zone-{colour}"
            display += f" · {status}"
        if zone_metric and (zone := _trace_rating(zone_metric, value, ())):
            marker = f"zone-dot zone-{zone[0]}"
            display += f" · {zone[1]}"
        g.append(_point(x(i), y(value), label, display, marker))
    if time_ticks:
        g += [f'<text x="{elapsed_x(minute):.2f}" y="{bottom + 17}" text-anchor="middle" class="tick">'
              f'{_e(label)}</text>' for label, minute in time_ticks]
    elif calendar_ticks:
        g += _x_ticks(calendar_ticks, lambda i: calendar_x(calendar_ticks[i]), bottom, w > W, weekdays=True)
    else:
        g += _x_ticks(labels, x, bottom, w > W)
    return _chart("line", g, w, h, (left, right, top, bottom), x_label, y_label)


def bar_chart(items: list[tuple[str, float]], unit: str = "", ref: float | None = None,
              ref_label: str = "", h: int = 190, nd: int = 0,
              tones: list[str] | None = None, w: int = W, x_label: str = "Date",
              y_label: str = "Value", averages: dict[str, float] | None = None,
              rate_goal: bool = False, weekdays: bool = False) -> str:
    if not any(isinstance(v, (int, float)) and math.isfinite(v) for _, v in items):
        return '<p class="empty">No measurements recorded for this chart.</p>'
    values = [v for _, v in items if isinstance(v, (int, float)) and math.isfinite(v)]
    averages = averages or {}
    ticks = _ticks(0, max(max(values), ref or 0, max(averages.values(), default=0)) or 1)
    h = max(h, 184)
    left, right, top, bottom = 51, w - 20, 29, h - 49
    spacing = (right - left) / len(items)
    width = min(28, spacing * 0.74)

    def x(i: int) -> float:
        return left + (i + 0.5) * spacing

    def y(v: float) -> float:
        return bottom - (bottom - top) * v / ticks[-1]

    g = _horizontal_scale(ticks, left, right, y, _tick_number)
    g += _axes(left, right, top, bottom, h, x_label, y_label)
    if ref is not None:
        yr = y(ref)
        g.append(f'<line x1="{left}" x2="{right}" y1="{yr:.2f}" y2="{yr:.2f}" class="ref"/>')
        if ref_label:
            g.append(f'<text x="{right}" y="{yr - 5:.2f}" class="tick" text-anchor="end">'
                     f'{_e(ref_label)}</text>')
    for i, (label, value) in enumerate(items):
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            continue
        tone = tones[i] if tones and i < len(tones) else "s1"
        display = _f(value, nd, unit)
        if rate_goal and ref is not None:
            tone, status = ("good", "met goal") if value >= ref else ("warn", "below goal")
            display += f" · {status}"
        g.append(f'<rect x="{x(i) - width / 2:.2f}" y="{y(value):.2f}" width="{width:.2f}" '
                 f'height="{max(0, bottom - y(value)):.2f}" rx="2" class="bar {_e(tone)}">'
                 f'<title data-native>{_e(label)} · {_e(display)}</title></rect>')
        g.append(_point(x(i), y(value), label, display))
    labels = [label for label, _ in items]
    g.append(_smooth_line(labels, averages, x, y))
    g += _x_ticks(labels, x, bottom, w > W, weekdays=weekdays)
    return _chart("bar", g, w, h, (left, right, top, bottom), x_label, y_label)


def scatter(points: list[tuple[str, float, float]], xl: str, yl: str, slope: float | None,
            w: int = W, h: int = 238, x_unit: str = "", y_unit: str = "", lag: int = 0,
            *, absolute_x: bool = False, absolute_y: bool = False, x_format=None, dense: bool = False,
            fit_center: tuple[float, float] | None = None) -> str:
    """Signed axes show how each measurement differs from its own recent average."""
    points = [(d, a, b) for d, a, b in points if math.isfinite(a) and math.isfinite(b)]
    if not points or (len(points) < 3 and not (absolute_x and absolute_y and slope is None)):
        return '<p class="empty">Not enough paired observations yet.</p>'
    xs, ys = [p[1] for p in points], [p[2] for p in points]
    x_ticks = _ticks(*_scale(xs if absolute_x else xs + [0], 0.05))
    x0, x1 = x_ticks[0], x_ticks[-1]
    y_values = ys if absolute_y else ys + [0]
    fit_values = None
    if slope is not None:
        mx, my = fit_center or (sum(xs) / len(xs), sum(ys) / len(ys))
        fit_values = [my + slope * (edge - mx) for edge in (min(xs), max(xs))]
        y_values.extend(fit_values)
    y_ticks = _ticks(*_scale(y_values, 0.05))
    y0, y1 = y_ticks[0], y_ticks[-1]
    left, right, top, bottom = 56, w - 25, 29, h - 49

    def x(v: float) -> float:
        return left + (right - left) * (v - x0) / (x1 - x0)

    def y(v: float) -> float:
        return bottom - (bottom - top) * (v - y0) / (y1 - y0)

    x_label = f"{xl} ({x_unit})" if x_unit else xl
    y_label = f"{yl} ({y_unit})" if y_unit else yl
    signed = lambda v: _tick_number(v, signed=True)
    g = _horizontal_scale(y_ticks, left, right, y, _tick_number if absolute_y else signed)
    for v in x_ticks:
        g.append(f'<line x1="{x(v):.2f}" x2="{x(v):.2f}" y1="{top}" y2="{bottom}" '
                 f'class="{"zero" if v == 0 else "grid"}"/>'
                 f'<text x="{x(v):.2f}" y="{bottom + 17}" class="tick" text-anchor="middle">'
                 f'{_e(x_format(v) if x_format else _tick_number(v) if absolute_x else signed(v))}</text>')
    if not absolute_y:
        g.append(f'<line x1="{left}" x2="{right}" y1="{y(0):.2f}" y2="{y(0):.2f}" class="zero"/>')
    g += _axes(left, right, top, bottom, h, x_label, y_label)
    if fit_values is not None:
        g.append(f'<line x1="{x(min(xs)):.2f}" y1="{y(fit_values[0]):.2f}" '
                 f'x2="{x(max(xs)):.2f}" y2="{y(fit_values[1]):.2f}" class="fit"/>')
    for d, a, b in points:
        second = (date.fromisoformat(d) + timedelta(days=lag)).isoformat() if lag else d
        when = f"{d} → {second}" if lag else d
        x_value = f"{a:g}/{x_unit.split('–')[-1]}" if absolute_x else f"{a:+.2f} {x_unit}"
        if x_format:
            x_value = f"{x_format(a)} {x_unit}".strip()
        y_value = f"{b:g}" if absolute_y else f"{b:+.2f}"
        value = f"{xl}: {x_value} · {yl}: {y_value} {y_unit}"
        g.append(_point(x(a), y(b), when, value, "pt pt-sparse" if len(points) <= 12 else "pt"))
    return _chart("scatter", g, w, h, (left, right, top, bottom), x_label, y_label, dense=dense)


def gauge(value: float | None, bands: list[tuple[float | None, str, str]], lo: float,
          hi: float, marker2: float | None = None, unit: str = "") -> str:
    """Five-colour bullet bar (Garmin gauge), HTML so it stays crisp at any width: a filled
    marker for this run and a hollow one for 'your usual at this pace'."""
    if value is None:
        return ""

    def pos(v: float) -> float:
        return 100 * (max(lo, min(hi, v)) - lo) / (hi - lo)

    segs, start = [], lo
    for upper, colour, label in bands:
        end = hi if upper is None else upper
        segs.append(f'<i class="g-{colour}" style="flex:{end - start:.3f}" title="{_e(label)}">'
                    f'</i>')
        start = end
    m2 = (f'<b class="mk2" style="left:{pos(marker2):.1f}%" title="Your usual at this pace: '
          f'{marker2:.1f}{unit}"></b>') if marker2 is not None else ""
    return (f'<div class="gauge"><div class="gbar">{"".join(segs)}</div>{m2}<b class="mk" '
            f'style="left:{pos(value):.1f}%" title="This run: {value:.1f}{unit}"></b></div>')


def both(fn: Any, *a: Any, **k: Any) -> str:
    """Phone and desktop drawings of the same chart so text stays readable on both."""
    return (f'<div class="chart-layout"><div class="sm">{fn(*a, w=W, **k)}</div>'
            f'<div class="lg">{fn(*a, w=720, **k)}</div></div>')


def _clock(h: float) -> str:
    m = round(h * 60) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def _short(d: str) -> str:
    try:
        if len(d) == 7:
            return date.fromisoformat(d + "-01").strftime("%b %y")
        return date.fromisoformat(d[:10]).strftime("%-d %b")
    except ValueError:
        return d


# =============================================================================== pages
TONE = {"green": "good", "yellow": "warn", "red": "bad"}
GAUGE_RANGE = {"cadence_spm": (145, 192), "ground_contact_ms": (200, 330),
               "vertical_oscillation_cm": (5, 13), "vertical_ratio_pct": (5, 11.5)}


def _card(title: str, body: str, sub: str = "", wide: bool = False, href: str = "") -> str:
    head = f'<h3>{_e(title)}</h3>' + (f'<p class="sub">{sub}</p>' if sub else "")
    if href:
        head = f'<a class="card-link" href="{href}">{head}{icon("chev", "chev")}</a>'
    return f'<section class="card{" wide" if wide else ""}">{head}{body}</section>'


def _page(pid: str, title: str, lede: str, body: str, back: str = "#today") -> str:
    parent = {"#today": "Today", "#trends": "Trends", "#running": "Runs",
              "#month-detail": "Year", "#history": "History", "#training": "Training"}.get(back)
    parent = parent or ("Run overview" if back.startswith("#run-") else "Month")
    nav = ("" if pid == "today" else f'<a class="back" href="{back}">{icon("back")}'
           f'<span>{parent}</span></a>')
    intro = f'<p class="lede">{lede}</p>' if lede else ""
    return (f'<article class="page" id="{pid}" aria-labelledby="heading-{pid}">{nav}'
            f'<header class="ph"><h2 id="heading-{pid}" tabindex="-1">{_e(title)}</h2>'
            f'{intro}</header><div class="grid">{body}</div></article>')


def _row(label: str, value: str, note: str = "", state: str = "") -> str:
    ic = {"good": icon("ok", "good"), "up": icon("up", "warn"), "down": icon("down", "warn")}
    return (f'<li><span class="k">{_e(label)}</span><span class="v">{value}</span>'
            f'<span class="n">{ic.get(state, "")}{_e(note)}</span></li>')


_PATTERN_LABELS = {
    "sleep_h": "Sleep duration", "hrv": "Overnight HRV", "rhr": "Resting heart rate",
    "garmin_readiness": "Garmin readiness", "bedtime_h": "Bedtime",
    "trimp": "Training load", "sleep_score": "Sleep score", "last_training_end_h": "Workout end time",
    "stress": "Daytime stress", "steps": "Daily steps", "intensity_min": "Intensity minutes",
}
def _insight(item: dict[str, Any], prioritized: bool = False) -> str:
    action = f'<span class="finding-action">{_e(item["action"])}</span>' if item.get("action") else ""
    basis = (f'<details><summary>Why this?</summary><p class="sub">{_e(item["basis"])}</p></details>'
             if item.get("basis") else "")
    label = '<span class="insight-label">AI-prioritized follow-up</span>' if prioritized else ""
    return (f'<li><a class="finding" href="#{item["target"]}"><span>{label}'
            f'<strong>{_e(item["title"])}</strong>'
            f'<span class="finding-detail">{_e(item["detail"])}</span>{action}</span>{icon("chev")}</a>'
            f'{basis}</li>')


def _narration(summary: dict | None) -> str:
    if not summary:
        return ""
    facts = "".join(f'<li>{_e(label.capitalize())}: {_e(value)}</li>'
                    for label, value in summary["facts"].items())
    return (f'<div class="local-insight"><p class="insight-label">AI summary · facts checked</p>'
            f'<p>{_e(summary["text"])}</p>'
            f'<details><summary>Show the facts</summary><ul>{facts}</ul></details></div>')


def _trial_card(trial: dict[str, Any], summary: dict | None = None, *,
                last_target: str | None = None, next_step: str | None = None) -> str:
    """Today: the experiment you're running, how the last attempt went, and what's next."""
    t = trial["trial"]
    attempts = trial.get("attempts") or []
    last = attempts[-1] if attempts else None
    body = f'<p class="say">{_e(t["title"])}</p>'
    if last:
        caption = f'Last attempt · {_e(_short(last["date"] or ""))}'
        link = (f'<a class="flow-link" href="{last_target}">{caption}{icon("chev")}</a>'
                if last_target else f'<p class="sub">{caption}</p>')
        body += f'<p>{_e(last["summary"])}</p>{link}'
    body += (f'<p class="sub"><b>Next:</b> {_e(next_step or trial["next"])}</p>'
             f'<details><summary>So far</summary><p class="sub">{_e(trial["verdict"])} '
             'Compared with your own steady runs at a similar pace and duration from before '
             'the experiment. Changes smaller than normal day-to-day variation count as '
             '"about the same".</p></details>')
    return _card("Your experiment", body + _narration(summary), wide=True)


def _trial_run_card(trial: dict[str, Any], aid: int) -> str:
    """Run page: what this run showed for the experiment."""
    for a in (trial or {}).get("attempts") or []:
        if a["activity_id"] != aid:
            continue
        rows = "".join(_row(trials.LABELS[c["metric"]].capitalize(),
                            _e(f'{c["this_run"]:g}') + (f' <small>{_e(c["unit"])}</small>'
                                                         if c.get("unit") else ""),
                            f'usual {c["usual"]:g} · {c["verdict"]}')
                       for c in a.get("changes", []))
        note = a.get("comparison_note")
        extra = f'<p class="sub">{_e(note)}</p>' if note else ""
        return _card("Your experiment on this run",
                     f'<p>{_e(a["summary"])}</p>{extra}<ul class="rows">{rows}</ul>',
                     _e(trial["trial"]["title"]), wide=True)
    return ""


def _overview_tile(label: str, value: str, note: str, target: str, symbol: str) -> str:
    return (f'<a class="overview-tile" href="#{target}"><span>{icon(symbol)}'
            f'{_e(label)}{icon("chev", "chev")}</span><strong>{_e(value)}</strong>'
            f'<small>{_e(note)}</small></a>')


def _nap_note(review):
    if not review or not review["nap_days"]:
        return ""
    today = review["latest_nap_s"]
    current = f'{_sleep_time(today / 3600)} of naps recorded for {_date_label(review["end"])}. ' if today else (
        "Garmin reported zero nap minutes for the snapshot date. " if today == 0 else "")
    return (f'<p>{_e(current)}'
            f'{review["nap_positive_days"]} of {review["nap_days"]} dates with an explicit nap total had naps. '
            f'These {review["nap_days"]} dates come from the last 29 calendar days. '
            'Nightly sleep and nap totals are shown separately.</p>')


def _sleep_time(hours: float) -> str:
    minutes = round(hours * 60)
    h, m = divmod(minutes, 60)
    return f"{h}h {m:02d}m" if m else f"{h}h"


def _sunday_story(d: dict) -> str:
    if not (facts := deep_insight.sunday_review(d)):
        return ""
    intro = f'<p>{_e(" ".join(row.text for row in facts))}</p>'
    if result := d.get("narration", {}).get("sunday-insight"):
        sources = "".join(f'<li><a class="source-link" href="#{_e(row["page"])}">{_e(row["text"])}</a></li>'
                          for row in result["readings"])
        label = "Readings selected by local AI" if result.get("mode") == "selected_comparison" else "Local AI review"
        intro = (f'<p class="insight-label">{label}</p><p>{_e(result["observation"])}</p>'
                 f'<p>{_e(result["question"])}</p><details><summary>Recorded evidence</summary>'
                 f'<ul>{sources}</ul></details>')
    plan = d["brief"]["week_ahead"]
    basis = f'<p class="sub">{_e(plan["basis"])}</p>' if plan.get("basis") else ""
    return _card("Sunday review", intro + f'<p><strong>Next focus</strong> · {_e(plan["plan"])}</p>'
                 f'{basis}{_weekly_cue_review(d)}'
                 f'<a class="flow-link" href="#training">Review the week{icon("chev")}</a>', wide=True)


def _pause_running(brief: dict) -> bool:
    return bool(brief.get("knee_pause") or brief["focus"]["title"] in {
        "Skip running today.", "Pause training today.", "Rest today or choose very easy movement.",
    })


def _weekly_cue_review(d):
    trial = d.get("trial") or {}
    if (d.get("older_snapshot") or d.get("sync_retry_required") or not trial.get("active")
            or trial.get("trial", {}).get("kind") != "cadence"):
        return ""
    attempts = trial.get("attempts", ())
    measured = sum(any(change["metric"] == "efficiency_factor" for change in a.get("changes", ()))
                   for a in attempts)
    next_step = trial["next"]
    if _pause_running(d["brief"]):
        next_step = "Pause the experiment. See today’s guidance before planning another attempt."
    return (f'<p><strong>Cadence experiment</strong> · {len(attempts)} recorded '
            f'attempt{"s" if len(attempts) != 1 else ""} · {measured} with a comparable effort reading.</p>'
            f'<p>{_e(next_step)}</p>')


def _reading_availability_card(d, *, compact=False):
    info = d.get("reading_availability")
    if not info:
        return ""
    states = {"recorded": "Recorded for this date", "awaiting_sync": "Awaiting a complete sync",
              "incomplete": "Incomplete night", "absent": "No usable reading for this date"}
    rows = []
    for metric in info["rows"].values():
        note = (f'Latest usable reading {_date_label(metric["latest"])}.'
                if metric["latest"] else "No earlier usable reading in this archive.")
        rows.append(_row(metric["label"], _e(states[metric["state"]]), note))
    if not info["published_guidance"]:
        headline = "Guidance for today is waiting for a current, completed sync."
    elif info["score_available"]:
        headline = f'Recovery calculation uses {len(info["usable"])} measures.'
    else:
        headline = (f'{len(info["usable"])} recovery measures have enough coverage. '
                    f'The score needs at least {info["minimum"]}.')
    used = (f'<p class="sub">{_e(", ".join(info["usable"]))}.</p>' if info["usable"] else "")
    details = used + f'<ul class="rows">{"".join(rows)}</ul>'
    if compact:
        missing = sum(row["state"] != "recorded" for row in info["rows"].values())
        details = (f'<details><summary>{missing} reading{"s" if missing != 1 else ""} '
                   f'missing or incomplete</summary>{details}</details>')
    return _card("Which readings are available?", f'<p>{_e(headline)}</p>{details}',
                 f'For {_date_label(info["day"])}', wide=True)


def _decision_sources(d):
    evidence = d.get("guidance_evidence", ())
    if not evidence:
        return ""
    rows = "".join(_row(row["label"], "", row["detail"]) for row in evidence)
    previous = (d.get("guidance_change") or {}).get("previous", {})
    earlier = "".join(_row(row["label"], "", row["detail"]) for row in previous.get("evidence", ()))
    return ('<details><summary>Readings behind this recommendation</summary>'
            f'<ul class="rows">{rows}</ul>'
            + (f'<p>Behind the previous recommendation</p><ul class="rows">{earlier}</ul>' if earlier else "")
            + '</details>')


def _reviewed_insight(insight: dict, *, title: str, selection_title: str,
                      lens: str | None = None) -> str:
    links = "".join(f'<li>{_e(row["text"])}</li>' if row.get("previous") else
                    f'<li><a class="source-link" href="#{_e(row["page"])}">{_e(row["text"])}</a></li>'
                    for row in insight["readings"])
    if insight.get("mode") == "selected_comparison":
        title = selection_title
    mode_note = ('<p class="sub">Used a direct draft after extended reasoning could not finish.</p>'
                 if insight.get("mode") == "direct_retry" else "")
    label = f'<p class="insight-label">{_e(lens)}</p>' if lens else ""
    return (f'<section class="daily-interpretation wide"><h3>{_e(title)}</h3>{label}'
            f'<p class="say">{_e(insight["observation"])}</p>'
            f'<p><b>What to check next</b> · {_e(insight["question"])}</p>'
            f'<details><summary>Recorded evidence · {len(insight["readings"])} readings</summary>'
            f'{mode_note}<ul>{links}</ul></details></section>')


def page_today(d: dict[str, Any]) -> str:
    rec, sleep = d["scores"]["recovery"], d["scores"]["sleep"]
    day = d["end"]
    snapshot = d["calendar"]["days"].get(day, {})
    training_n = len(snapshot.get("activities", []))
    focus = d["brief"]["focus"]
    current = not (d.get("older_snapshot") or d.get("sync_retry_required"))
    has_activity = current and bool(training_n)
    runs = {r["activity_id"] for r in d["runs"]}
    ready = rec["pct"] is not None
    tiles = (
        _overview_tile("Recovery", _f(rec["pct"], unit="%") if ready else "—",
                       (rec["label"] or "").capitalize() if ready else "Still learning",
                       "recovery", "heart")
        + _overview_tile("Sleep", _sleep_time(sleep["hours"]) if sleep["hours"] else "—",
                         f'Goal {_sleep_time(sleep["need_h"])}' if sleep["hours"]
                         else "No night recorded", "sleep", "moon")
        + _overview_tile("Training", str(training_n), "Workout logged" if training_n == 1
                         else "Workouts logged", "training", "bolt"))
    body = ""
    if not current:
        status = ("Sync to get today’s guidance." if d.get("older_snapshot")
                  else "Finish syncing to get today’s guidance.")
        body += f'<section class="card today-focus wide"><h3>{_e(status)}</h3></section>'
    else:
        target = focus["target"]
        link = {"recovery": "See recovery", "sleep": "See sleep", "training": "See training"}
        more = (f'<a class="flow-link" href="#{target}">{link[target]}{icon("chev")}</a>'
                if target else "")
        detail = f'<p>{_e(focus["detail"])}</p>' if focus["detail"] else ""
        change = d.get("guidance_change")
        previous = ""
        if change:
            prior = change["previous"]
            when = "Earlier today" if prior["day"] == day else _short(prior["day"])
            previous = f'<p class="sub">{_e(when)} · {_e(prior["title"])}</p>'
        label = "What changed?" if change else "Daily guidance"
        width = "" if has_activity else " wide"
        body += (f'<section class="card today-focus{width}"><p class="focus-label">{label}</p>{previous}'
                 f'<h3>{_e(focus["title"])}</h3>'
                 f'{detail}{more}{_decision_sources(d)}</section>')
        body += _resting_pulse_card(snapshot.get("resting_pulse_check"), flagged_only=True)
    if training_n:
        rows = [_record_link(_workout_name(a),
                             " · ".join(filter(None, [a["duration"],
                                         _f(a["distance_km"], 1, " km") if a["distance_km"] else ""])),
                             _workout_link(d, a["id"], runs))
                for a in snapshot.get("activities", [])]
        body += _card("Today’s workouts" if current else "Workouts on this date",
                      f'<ul class="record-list">{"".join(rows)}</ul>', wide=not has_activity)
    overview_label = "Readings on this date" if d.get("older_snapshot") else "Today’s readings"
    body += (f'<section class="overview wide" aria-label="{overview_label}">'
             f'<h3>Health &amp; activity</h3><div class="overview-tiles">{tiles}</div></section>')
    availability = d.get("reading_availability", {})
    if any(metric["state"] != "recorded" for metric in availability.get("rows", {}).values()):
        body += _reading_availability_card(d, compact=True)

    anchor = d.get("sleep_review", {}).get("anchor", {})
    bedtime_plan = d.get("bedtime_experiment", {})
    saved_target = (bedtime_plan.get("current") or {}).get("target")
    if current and anchor:
        target = saved_target or bedtime_plan.get("suggestion") or anchor.get("bedtime")
        bedtime = f' · In bed by {_e(target)} this week' if target else ""
        body += (f'<a class="sleep-brief wide" href="#sleep">'
                 f'<span><strong>Sleep schedule</strong> · Wake around {anchor["wake"]}'
                 f' · {anchor["spread"]} min variation{bedtime}</span>'
                 f'{icon("chev")}</a>')

    if current and (insight := d.get("narration", {}).get("deep-insight")):
        lens = {"sleep": "Sleep & recovery", "running": "Running & recovery"}.get(
            insight.get("lens"), "Daily review")
        body += _reviewed_insight(insight, title="AI interpretation",
                                  selection_title="Readings selected by local AI", lens=lens)
    if current:
        week = d["brief"]["week_ahead"]
        body += _card("Next seven days", f'<p class="sub week-cue">{_e(week["plan"])}</p>'
                      f'<details><summary>How this was chosen</summary>'
                      f'<p class="sub">{_e(week["basis"])}</p></details>', wide=True)
    if current:
        body += _sunday_story(d)
    if current and (followup := d.get("wake_followup")):
        body += _card("Wake-time follow-up", _wake_followup(followup, d["calendar"]) +
                      f'<a class="flow-link" href="#sleep">Sleep history{icon("chev")}</a>', wide=True)
    if current and (movement := d.get("movement")):
        steps = (f'{_f(movement["steps"])} steps recorded' if movement["steps"] is not None
                 else "No steps recorded today")
        body += (f'<p class="sleep-brief wide">{steps} · Usual floor {_f(movement["floor"])} steps'
                 f' · {movement["streak"]} consecutive days through '
                 f'{_e(_short(movement["through"]))}</p>')
    findings = list(focus["findings"]) if current else []
    narration = d.get("narration", {})
    choice = narration.get("focus", {}).get("choice")
    prioritized = None
    if type(choice) is int and 1 <= choice <= len(findings):
        prioritized = findings.pop(choice - 1)
        findings.insert(0, prioritized)
    trial = d.get("trial") or {}
    if current and d["runs"] and not trial.get("active"):
        latest_run = d["runs"][0]
        cue = latest_run.get("cadence_experiment")
        if cue and not _pause_running(d["brief"]):
            findings.insert(1, {"title": "Try shorter steps on an easy run",
                                "detail": cue["suggestion"], "basis": cue["check"],
                                "target": f'run-{latest_run["activity_id"]}'})
    if findings:
        rows = "".join(_insight(item, item is prioritized) for item in findings)
        body += _card("What to work on", f'<ul class="findings">{rows}</ul>', wide=True)
    if trial.get("active"):  # About past runs, so useful even on an older snapshot.
        last_attempt = trial["attempts"][-1] if trial["attempts"] else None
        target = _workout_link(d, last_attempt["activity_id"], runs) if last_attempt else None
        next_step = None
        if not current:
            next_step = "Finish syncing before planning another attempt."
        elif _pause_running(d["brief"]):
            next_step = "Pause the experiment. See today’s guidance before planning another attempt."
        body += _trial_card(trial, narration.get("trial") if current else None,
                            last_target=target, next_step=next_step)
    if current and narration.get("today"):
        body += _card("Recovery summary", _narration(narration["today"]), wide=True)
    body += (f'<a class="flow-link history-entry wide" href="#trends">'
             f'Browse trends and history{icon("chev")}</a>')
    label = f"Readings for {_date_label(day)}" if d.get("older_snapshot") else _date_label(day)
    return _page("today", "Today", label, body)


def _bedroom_card(review: dict) -> str:
    groups = []
    for group in review["groups"][:3]:
        rows = []
        for band, title in (("lower", "Lower readings"), ("higher", "Higher readings")):
            data = group[band]
            energy = data["morning_energy"]
            note = f'{len(data["nights"])} nights'
            if energy is not None and all(group[k]["morning_energy"] is not None
                                          for k in ("lower", "higher")):
                note += f' · Morning energy {energy:g}/5 ({data["energy_samples"]} check-ins)'
            rows.append(_row(title,
                             f'{_f(data["conditions"], 1, " " + group["unit"])} · '
                             f'{_sleep_time(data["sleep_h"])} asleep', note))
        dates = "; ".join(f'{title}: {", ".join(row["date"] for row in group[band]["nights"])}'
                          for band, title in (("lower", "Lower group"), ("higher", "Higher group")))
        groups.append(f'<section><h4>{_e(group["label"])}</h4><ul class="rows">{"".join(rows)}</ul>'
                      f'<details><summary>Which nights?</summary><p class="sub">'
                      f'{_e(group["source"])} · {_e(dates)}</p></details></section>')
    if not groups:
        return ""
    return _card("Room conditions and sleep", "".join(groups),
                 "Typical sleep time on nights with different measured room conditions.",
                 wide=True)


def _night_record(night: dict) -> str:
    stats = [("Asleep", _sleep_time(night["hours"]))]
    if night["score"] is not None:
        stats.append(("Garmin score", f'{_f(night["score"])}/100'))
    for field, title in (("bed", "Fell asleep"), ("wake", "Woke up")):
        if night[field] is not None:
            stats.append((title, sleep_review.clock(night[field])))
    metrics = "".join(f'<div><dt>{label}</dt><dd>{value}</dd></div>' for label, value in stats)
    stages = [(label, seconds) for label, seconds in night["stages"].items() if seconds is not None and seconds >= 0]
    total = sum(seconds for _, seconds in stages)
    composition = ""
    if total > 0:
        bar = "".join(f'<span class="{label.lower()}" style="flex:{seconds:g}"></span>'
                      for label, seconds in stages)
        legend = "".join(f'<li class="{label.lower()}">{label} <b>{_sleep_time(seconds / 3600)}</b></li>'
                         for label, seconds in stages)
        composition = (f'<h4>Time in each stage</h4><div class="stage-strip" aria-hidden="true">{bar}</div>'
                       f'<ul class="stage-key">{legend}</ul>')
    timeline = ""
    if intervals := night.get("timeline"):
        bars = "".join(f'<span class="{stage}" style="left:{100 * start:.3f}%;'
                       f'width:{100 * length:.3f}%"></span>' for start, length, stage in intervals)
        timeline = ('<h4>Sleep stages through the night</h4>'
                    '<div class="sleep-timeline" role="img" '
                    'aria-label="Recorded stage timeline from sleep start to wake">'
                    f'{bars}</div>')
    return f'<dl class="sleep-measures">{metrics}</dl>{timeline}{composition}'


def _wake_followup(review: dict, calendar: dict) -> str:
    change = review["sleep_change"]
    duration = ("Average sleep stayed the same to the nearest minute." if not change else
                f'Average sleep was {abs(change)} min {"longer" if change > 0 else "shorter"}.')
    days = set(calendar["detail_days"])
    records = "".join(f'<li><a class="source-link" href="#day-{day}">{_e(_short(day))}</a></li>'
                      for day in review["dates"] if day in days)
    evidence = f'<details><summary>Reviewed nights</summary><ul>{records}</ul></details>' if records else ""
    return (f'<p>Within 30 min of {review["anchor"]} on {review["hits"]} of {review["nights"]} nights, '
            f'compared with {review["prior_hits"]} of {review["prior_nights"]} the week before.</p>'
            f'<p>{duration}</p>{evidence}')


def _sleep_journal(d: dict) -> str:
    rows = []
    names = {"sleep_score": ("Garmin sleep score", " pts"), "hrv": ("HRV", " ms"),
             "rhr": ("Resting heart rate", " bpm")}
    for tag, record in sorted(d.get("tag_review", {}).items()):
        if tag not in {"late_caffeine", "late caffeine", "caffeine late", "late_meal", "late meal",
                       "screens_late", "late_workout", "late workout", "alcohol"}:
            continue
        values = [f'{label} {record[key]["next_day_diff"]:+g}{unit}'
                  for key, (label, unit) in names.items() if key in record]
        rows.append(_record_link(tag.replace("_", " ").capitalize(),
                                 " · ".join(values) or "Collecting comparable nights"))
    if rated := d.get("rested_review"):
        rows.append(_record_link("How rested you felt",
                                 f'Garmin score averaged {rated["low"]} across {rated["low_n"]} low ratings '
                                 f'and {rated["high"]} across {rated["high_n"]} high ratings.'))
    return (_card("Sleep journal", f'<ul class="record-list">{"".join(rows)}</ul>',
                  "Following-night readings vs your baseline.", wide=True) if rows else "")


def _sleep_trend_key(context):
    items = []
    if context["trend"]:
        items.append("Dashed: " + context["trend_label"])
    if context["band"]:
        items.append("Shaded: " + context["band_label"].lower())
    return f'<p class="chart-note">{_e(" · ".join(items))}</p>' if items else ""


def _sleep_trend_chart(chart, nights, *, monthly=False, metric="hours"):
    context = sleep_review.trend_context(chart, nights, monthly=monthly, metric=metric)
    aligned = [((stamp + "-01" if monthly else stamp), value) for stamp, value in chart]
    averages = {stamp + "-01" if monthly else stamp: value for stamp, value in context["trend"].items()}
    is_score = metric == "score"
    visual = both(line_chart, aligned, " points" if is_score else " h", nd=0 if is_score else 1,
                  x_label="Month" if monthly else "Wake date",
                  y_label="Garmin sleep score (0–100)" if is_score else "Sleep duration (h)",
                  band=context["band"], band_label=context["band_label"],
                  averages=averages, average_label=context["trend_label"], break_gaps=True,
                  max_gap=32 if monthly else 1, weekdays=not monthly and len(chart) <= 7)
    return visual + _sleep_trend_key(context)


def _sleep_shortfall_card(review, detail_days):
    if not review or not review["current"]["debt_inputs"]:
        return ""
    current = review["current"]
    nights = current["debt_inputs"]
    coverage = f'{len(nights)} of 7 nights usable · {review["target_met"]} met their target'
    previous = review["previous_min"]
    per_night = review["per_night_min"]
    comparison = ""
    if previous is not None:
        delta = per_night - previous
        comparison = (f' · {abs(delta)} min {"more" if delta > 0 else "less"} per night than the prior week'
                      if delta else " · same average gap as the prior week")
    rows = "".join(_record_link(_date_label(n["day"]),
                                f'{_sleep_time(n["sleep_h"])} of {_sleep_time(n["need_h"])} target '
                                f'· {_sleep_time(n["shortfall_h"])} short · {n["source"]}',
                                f'#day-{n["day"]}' if n["day"] in detail_days else None)
                   for n in reversed(nights))
    return (f'<section class="sleep-band wide"><h3>Sleep shortfall · '
            f'{_sleep_time(review["total_min"] / 60)}</h3>'
            f'<p><b>{coverage}</b> · {per_night} min short per usable night{comparison}.</p>'
            f'<p class="sub">Garmin supplied the target on {len(nights) - review["fallback"]} nights. '
            'The other targets use 8 hours. Missing and incomplete nights are excluded. '
            'This shows time below target. It cannot tell you how much recovery sleep you need.</p>'
            f'<details><summary>Nightly targets and gaps</summary><ul class="record-list">{rows}</ul>'
            "</details></section>")


def page_sleep(d: dict[str, Any]) -> str:
    review = d.get("sleep_review", {})
    nights = review.get("nights", {})
    last = max(nights, default=None)
    plan = d.get("bedtime_experiment", {})
    if not last and not (plan.get("current") or plan.get("previous")):
        return _page("sleep", "Sleep", "No complete night recorded yet.", "")
    detail_days = set(d["calendar"]["detail_days"])
    body = _sleep_shortfall_card(d.get("sleep_shortfall"), detail_days)
    narration = d.get("narration", {})
    if last:
        night_link = (f'<a class="flow-link" href="#day-{last}">Full day record{icon("chev")}</a>'
                      if last in detail_days else "")
        body += (f'<section class="sleep-hero wide"><h3>Night ending {_e(_date_label(last))}</h3>'
                f'{_night_record(nights[last])}{night_link}'
                + _narration(narration.get("sleep") if not narration.get("sleep-insight") else None)
                + '</section>')
    if (last == d["end"] and not (d.get("older_snapshot") or d.get("sync_retry_required"))
            and (insight := narration.get("sleep-insight"))):
        body += _reviewed_insight(insight, title="AI sleep review",
                                  selection_title="Sleep readings selected by local AI")
    anchor = review["anchor"]
    if anchor:
        suggested = plan.get("suggestion") or anchor.get("bedtime")
        target = (f'<p>Suggested bedtime <b>{_e(suggested)}</b></p>'
                  if suggested and not plan.get("current") else "")
        body += (f'<section class="sleep-band wide"><h3>Keep wake time steady</h3>'
                 f'<p>Wake around <b>{anchor["wake"]}</b>. Wake times varied by '
                 f'<b>{anchor["spread"]} min</b> across {anchor["nights"]} nights.</p>'
                 f'{target}</section>')
    elif plan.get("suggestion") and not plan.get("current"):
        body += _card("Suggested bedtime", f'<p>{_e(plan["suggestion"])}</p>', wide=True)
    for label, tracked in (("This week’s target", plan.get("current")),
                           ("Previous bedtime target", plan.get("previous"))):
        if not tracked:
            continue
        comparisons = "".join(
            _row(name, f'{v["on_time"]:g} vs {v["later"]:g}',
                 f'On time {v["on_time_n"]} nights · later {v["later_n"]} nights')
            for key, name in (("hours", "Sleep hours"), ("sleep_score", "Sleep score"),
                              ("hrv_ms", "Overnight HRV (ms)"), ("readiness", "Garmin readiness"))
            if (v := tracked["comparisons"].get(key)) is not None
        )
        evidence = (f'<ul class="rows">{comparisons}</ul>' if comparisons else
                    '<p class="sub">Collecting enough nights for a comparison.</p>')
        if tracked_nights := tracked["nights"]:
            dates = "".join(_record_link(_date_label(row["day"]),
                                         "On time" if row["on_time"] else "Later",
                                         f'#day-{row["day"]}' if row["day"] in detail_days else None)
                            for row in reversed(tracked_nights))
            evidence += f'<details><summary>Recorded nights</summary><ul class="record-list">{dates}</ul></details>'
        body += _card(label, f'<p>Sleep start by <b>{_e(tracked["target"])}</b> · '
                      f'{tracked["on_time"]} of {tracked["recorded"]} timed nights</p>{evidence}',
                      f'Week of {_date_label(tracked["week_start"])}', wide=True)
    for period, label in ((7, "Past week"), (30, "Past month"), (365, "Past year")):
        window = review["windows"].get(period)
        if not window:
            continue
        score = (f' · Garmin score {_f(window["score"])} average across {window["scored"]} nights'
                 if window["score"] is not None else "")
        average = f'{_sleep_time(window["hours"])} average · {window["nights"]} nights{score}'
        if period == 7 and (delta := review["week_change_min"]):
            direction = "more" if delta > 0 else "less"
            average += f" · {abs(delta)} min {direction} per night than the week before"
        chart = _sleep_trend_chart(window["chart"], nights, monthly=period == 365)
        if period != 365 and window["scored"] >= 3:
            sleep_rows = [{"t_s": date.fromisoformat(day).toordinal(), "hours": hours,
                           "sleep_score": nights.get(day, {}).get("score")}
                          for day, hours in window["chart"]]
            context = sleep_review.trend_context(window["chart"], nights)
            chart = (both(_paired_chart, sleep_rows,
                          ("hours", "Sleep duration", "Sleep duration (h)", _sleep_time),
                          (("sleep_score", "Garmin sleep score", "Sleep score (0–100)",
                            lambda value: _f(value, unit="/100")),), 1, date_axis=True, context=context)
                     + _sleep_trend_key(context))
        if period != 7 and window["scored"] >= 3:
            score_chart = _sleep_trend_chart(window["score_chart"], nights, monthly=period == 365, metric="score")
            chart += f'<details><summary>Sleep score trend</summary>{score_chart}</details>'
        records = ""
        if period == 7:
            rows = []
            for day, night in list(nights.items())[-7:][::-1]:
                if (date.fromisoformat(d["end"]) - date.fromisoformat(day)).days >= 7:
                    continue
                note = [_sleep_time(night["hours"])]
                if night["bed"] is not None and night["wake"] is not None:
                    note.append(f'{sleep_review.clock(night["bed"])}–{sleep_review.clock(night["wake"])}')
                if night["score"] is not None:
                    note.append(f'Garmin score {_f(night["score"])}')
                rows.append(_record_link(_date_label(day), " · ".join(note),
                                         f"#day-{day}" if day in detail_days else None))
            records = f'<ul class="record-list">{"".join(rows)}</ul>'
        elif period == 30:
            records = f'<a class="flow-link" href="#history">Open daily history{icon("chev")}</a>'
        body += (f'<details class="sleep-band wide"{" open" if period == 7 else ""}>'
                 f'<summary><strong>{label}</strong><span>{average}</span></summary>'
                 f'{chart}{records}</details>')
    dip = (d["night"] or {}).get("heart_rate_dip")
    if dip:
        body += _card("Day and sleep heart rate",
                      f'<p>{_f(dip["awake_mean_hr"])} bpm during the day · '
                      f'{_f(dip["sleep_mean_hr"])} bpm asleep.</p>', wide=True)
    body += _sleep_journal(d)
    body += _bedroom_card(d["bedroom_conditions"])
    if note := _nap_note(d.get("wellness_review")):
        body += _card("Recorded naps", note, wide=True)
    return _page("sleep", "Sleep", "", body)


def _signal_summary(key: str, stat: dict[str, Any]) -> str:
    if stat["latest"] is None:
        return ""
    unit = stat["unit"]
    if stat["recent"] is None:
        return (f'<p class="sub">Latest {_f(stat["latest"], 1)} {unit} on '
                f'{_short(stat["latest_day"])} · {stat["recent_count"]}/7 readings this week.</p>')
    state = stat["state"]
    badge = f"{state.capitalize()} your usual range" if state else "Building your usual range"
    delta = stat["delta"]
    change_unit = "percentage points" if key == "sleep_spo2" else unit
    evidence = f'{_f(stat["recent"], 1)} {unit} average · {stat["recent_count"]}/7 readings'
    if delta is not None:
        evidence += (f" · {delta:+.1f} {change_unit} vs prior week" if round(delta, 1) else
                     " · little change vs prior week")
    if stat["baseline"]:
        lo, hi = stat["baseline"]
        evidence += f" · usual {lo:.1f}–{hi:.1f} {unit}"
    note = signal_context.describe(key, state)
    if key == "sleep_spo2" and state == "below":
        note += " If it stays unusual or you feel unwell, get it checked."
    reference = (
        ' <a class="source-link" href="https://medlineplus.gov/ency/article/003399.htm" '
        'rel="noreferrer">Adult reference: 60–100 bpm</a>. Athletes may be lower.' if key == "resting_hr" else
        ' <a class="source-link" href="https://www.fda.gov/medical-devices/products-and-medical-procedures/pulse-oximeters" '
        'rel="noreferrer">FDA sensor guidance</a>.' if key == "sleep_spo2" else "")
    return (f'<p class="signal-status"><strong>{_e(badge)}</strong></p>'
            f'<p class="sub">{_e(evidence)}</p><p class="sub">{_e(note)}{reference}</p>')


def _vital_chart(key: str, stat: dict[str, Any]) -> str:
    days = stat["days"]
    averages = {d["day"]: d["average"] for d in days if d["average"] is not None}
    chart = both(line_chart, [(d["day"], d["value"]) for d in days], " " + stat["unit"],
                 band_series=[d["range"] for d in days], averages=averages, break_gaps=True,
                 y_label=f'{stat["label"]} ({stat["unit"]})', nd=1, rate_range=True)
    bands = any(d["range"] and d["value"] is not None for d in days)
    legend = "Daily reading" + (" · dashed: 7-day average" if averages else "")
    legend += " · green: within usual · amber: below · blue: above" if bands else ""
    return _card(stat["label"], _signal_summary(key, stat) + chart,
                 legend if stat["latest"] is not None else "", wide=True)


def _hrv_summary(context: dict[str, Any]) -> str:
    state = context["state"]
    if state == "calibrating":
        return f'<p class="sub">{_e(context["meaning"])}</p>'
    status, note = {
        "below normal": ("Below your usual range",
                         "Recent load, poor sleep or illness could contribute. Check your other recovery signals."),
        "above normal": ("Above your usual range",
                         "Check how you feel and your recent load before adding intensity."),
        "within normal": ("Within your usual range",
                          "Use sleep, resting pulse and how you feel alongside HRV."),
    }[state]
    lo, hi = context["normal_band_ms"]
    average = context["rolling_7d_ms"]
    previous = context["previous_average"]
    delta = f" · {average - previous:+.1f} ms vs prior week" if previous is not None else ""
    return (f'<p class="signal-status"><strong>{status}</strong></p><p class="sub">'
            f'{_f(average, 1)} ms average · usual {lo:.1f}–{hi:.1f} ms · '
            f'{context["nights_in_7d"]}/7 nights{delta}</p><p class="sub">{note}</p>')


def _wellness_recovery_card(review):
    if not review:
        return ""
    rows = []
    for key, label in (("charge", "Charge"), ("drain", "Drain")):
        if total := review[key]:
            rows.append(_row(label, _e(f"{total[0]:g} points"), f"Daily median · {total[1]} recorded days"))
    if match := review["sleep_compare"]:
        rows.append(_row("Charge and overnight sleep", _e(f'{match["first"]:g} vs {match["second"]:g} points'),
                         f'Below Garmin sleep target ({match["first_count"]} days) vs '
                         f'met target ({match["second_count"]} days).'))
    if match := review["run_compare"]:
        rows.append(_row("Drain on days with a recorded run", _e(f'{match["second"]:g} vs {match["first"]:g} points'),
                         f'{match["second_count"]} dates with a run vs '
                         f'{match["first_count"]} dates without a recorded run.'))
    if match := review.get("nap_compare"):
        rows.append(_row("Drain on dates with recorded naps", _e(f'{match["second"]:g} vs {match["first"]:g} points'),
                         f'{match["second_count"]} dates with naps vs '
                         f'{match["first_count"]} dates with an explicit zero nap total.'))
    if not rows:
        return ""
    return _card("Body Battery over 28 days", f'<ul class="rows">{"".join(rows)}</ul>',
                 "Garmin’s daily point totals before the snapshot date. The comparisons describe "
                 "recorded days. Other activity and conditions can affect the totals.", wide=True)


def page_recovery(d: dict[str, Any]) -> str:
    hv = [(x["day"], x.get("hrv_7d_ms")) for x in d["hrv"]]
    bands = [tuple(x["hrv_band_ms"]) if x.get("hrv_band_ms") else None for x in d["hrv"]]
    hv_ok = [(p, b) for p, b in zip(hv, bands, strict=True) if p[1] is not None]
    hrv_chart = both(line_chart, [p for p, _ in hv_ok], " ms",
                     band_series=[b for _, b in hv_ok], y_label="Average HRV (ms)", rate_range=True)
    sh = d["shifts"]["shifts"]
    coverage = d["shifts"]["coverage"]
    names = {"resting_hr": ("Resting HR", "bpm"), "hrv": ("HRV", "ms"),
             "sleep_h": ("Sleep", "h")}
    shift_rows = "".join(_row(names[k][0], f'{v["change"]:+.1f} <small>{names[k][1]}</small>',
                              f'since {_short(v["date"])} ({v["before_mean"]:.1f} → '
                              f'{v["after_mean"]:.1f})') for k, v in sh.items())
    rec = d["scores"]["recovery"]
    garmin = (f'Garmin readiness {_f(rec["garmin_readiness"])}'
              if rec["garmin_readiness"] is not None else "")
    hist = d["history"]
    chart = both(bar_chart, [(h["day"], h["recovery"]) for h in hist], "%",
                 y_label="Recovery (%)", tones=[TONE.get(h["band"] or "", "muted") for h in hist])
    score = (f'<div class="big">{_e(rec["pct"])}<small>%</small></div>'
             f'<p class="sub">{_e(rec["label"].capitalize())}</p>'
             if rec["pct"] is not None else '<p class="empty">Still learning your usual readings.</p>')
    score += f'<p class="sub">{_e(garmin)}</p>' if garmin else ""
    score += _narration(d.get("narration", {}).get("today"))
    if any(h["recovery"] is not None for h in hist):
        score += f'<details class="recovery-history"><summary>Last 14 days</summary>{chart}</details>'
    body = (_resting_pulse_card(d["calendar"]["days"].get(d["end"], {}).get("resting_pulse_check"),
                                flagged_only=True) + _card("Recovery score", score, wide=True)
            + _reading_availability_card(d)
            + _wellness_recovery_card(d.get("wellness_review"))
            + _card("Heart rate variability", _hrv_summary(d["hrv_context"]) + hrv_chart,
                  "HRV measures variation in time between heartbeats. Compare the seven-day average "
                  "with your usual range.", wide=True)
            + "".join(_vital_chart(metric, d["signals"][metric])
                      for metric in ("resting_hr", "sleep_spo2", "sleep_resp"))
            + _card("Lasting changes", f'<ul class="rows">{shift_rows}</ul>' if shift_rows
                    else ('<p class="empty">No clear shift among the readings that could be assessed.</p>'
                          if any(n >= 28 for n in coverage.values()) else
                          '<p class="empty">Too few readings to assess a lasting change yet.</p>'),
                    "Step changes found in the last 180 days"))
    return _page("recovery", "Recovery", "Your recent readings compared with your usual range.",
                 body)


def _status_label(st: Any) -> str:
    """Readable Garmin training status; unknown codes show as a dash, never crash the page."""
    if not isinstance(st, str) or not st or st.isdigit():
        return "–"
    return st.replace("_", " ").title()


def _readiness_benchmark(b: dict, run_ids: set[int]) -> str:
    if not b["available"]:
        return ""
    rho = b["spearman_rho"]
    points = [(p["date"], p["readiness_score"], p["hr_vs_matches_bpm"]) for p in b["pairs"]]
    chart = both(scatter, points, "Garmin readiness", "Heart rate vs matched runs", None,
                 x_unit="0–100", y_unit="bpm", absolute_x=True)
    note = (f'{b["paired_days"]} paired days · rank correlation {rho:+.2f}. '
            "Below zero means higher scores tended to accompany lower heart rates on similar runs."
            if rho else f'{b["paired_days"]} paired days · no rank association in these records.')
    rows = []
    for p in reversed(b["pairs"]):
        aid = p["activity_id"]
        rows.append(_record_link(p["date"], f'{p["readiness_score"]:g}/100 · '
                                 f'{p["hr_vs_matches_bpm"]:+g} bpm · {p["matched_runs"]} matches',
                                 f"#run-{aid}" if aid in run_ids else None))
    return _card("Do readiness scores line up with your runs?",
                 f'<details><summary>See paired runs</summary>{chart}'
                 f'<ul class="record-list">{"".join(rows)}</ul></details>'
                 f'<p class="sub">{_e(b["interpretation"])}</p>', _e(note), wide=True)


def _outdoor_patterns_card(review: dict) -> str:
    if not review.get("sampled_runs"):
        return ""
    patterns = review["patterns"]
    if not patterns:
        return _card("Weather, air quality and training",
                     "<p>There aren’t enough comparable outdoor runs for a personal pattern yet.</p>",
                     f'{review["sampled_runs"]} single-workout days with saved conditions.'
                     f' At least {review["minimum_pairs"]} separate pairs are needed.', wide=True)
    sections = []
    for item in patterns:
        standard = conditions.AQI_STANDARDS.get(item["standard"], "")
        name = item["label"] + (f" ({standard})" if standard else "")
        kind = "Model estimates" if item["kind"] == "model" else "Observations"
        rows = "".join(
            _row(stat["label"], f'{stat["median_delta"]:+g} {_e(stat["unit"])}',
                 f'{stat["pairs"]} separate pairs') for stat in item["outcomes"])
        pairs = []
        visible_outcomes = {outcome["key"] for outcome in item["outcomes"]}
        for pair in item["pairs"]:
            lo, hi = pair["lower"], pair["higher"]
            evidence = " · ".join(f'{label} {hi["outcomes"][key] - lo["outcomes"][key]:+g} {unit}'
                                  for key, (label, unit) in environment_review.OUTCOMES.items()
                                  if key in visible_outcomes and key in hi["outcomes"]
                                  and key in lo["outcomes"])
            pairs.append(_record_link(f'{hi["day"]} vs {lo["day"]}',
                                      f'{hi["exposure"]:g} vs {lo["exposure"]:g} {item["unit"]}'
                                      + (f" · {evidence}" if evidence else "")))
        sections.append(f'<h4>{_e(name)}</h4><p class="sub">{kind}</p><ul class="rows">{rows}</ul>'
                        f'<details><summary>See the pairs</summary><p class="sub">'
                        f'{_e(item["source"])}</p><ul class="record-list">{"".join(pairs)}</ul>'
                        '</details>')
    return _card("Weather, air quality and training", "".join(sections)
                 + '<p class="sub">Other conditions can vary too. Outdoor readings describe '
                 'the run area.</p>',
                 "Median differences on days with higher readings, paired by similar runs.",
                 wide=True)


def _workout_link(d: dict, aid: int, run_ids: set[int]) -> str | None:
    if aid in run_ids:
        return f"#run-{aid}"
    if any(a["id"] == aid for a in d.get("workouts", [])):
        return f"#workout-{aid}"
    return None


def _workout_name(workout: dict) -> str:
    return workout["name"] or (workout["type"] or "Workout").replace("_", " ").capitalize()


def _workout_page(workout: dict, summary: dict | None) -> str:
    rows = (_row("Duration", _e(workout["duration"] or "—"))
            + _row("Distance", _f(workout["distance_km"], 2, " km"))
            + _row("Average heart rate", _f(workout["avg_hr"], unit=" bpm")))
    return _page(f'workout-{workout["id"]}', _workout_name(workout),
                 _date_label(workout["start"][:10]),
                 _card("Recorded workout", _narration(summary) + f'<ul class="rows">{rows}</ul>',
                       "Garmin activity summary", wide=True), back="#training")


def page_training(d: dict[str, Any]) -> str:
    load_rows = [{"t_s": date.fromisoformat(day).toordinal(), "long_load": ctl, "short_load": atl}
                 for day, ctl, atl in d["fitness"]]
    points = lambda value: _f(value, 1, " points")
    if sum(row["long_load"] is not None for row in load_rows) >= 2:
        fit = both(_paired_chart, load_rows, ("long_load", "Longer-term load", "Training load (points)", points),
                   (("short_load", "Recent load", "Recent load (points)", points),), 1,
                   date_axis=True, shared_scale=True)
    else:
        fit = both(line_chart, [(r[0], r[1]) for r in d["fitness"]], " points", nd=1,
                   y_label="Smoothed training load (points)")
    completed = [v for _, v in d["weekly_load"][-5:-1] if v is not None]
    four_week_avg = sum(completed) / 4 if len(completed) == 4 else None
    wl = both(bar_chart, d["weekly_load"], " points", y_label="Weekly training load (points)",
              x_label="Week beginning", ref=four_week_avg)
    week_card = ""
    review = d["weekly_review"]
    if review:
        week, usual, rest = review["week"], review["previous_4wk_weekly_avg"], review["recovery"]
        prior_text = (f'{week["sessions_with_load"]} of {week["sessions"]} workouts have usable load'
                      if week["trimp"] is None else
                      f'Previous four-week average: {_f(usual["trimp"])} points/week'
                      if usual["sessions"] and usual["trimp"] is not None else
                      "No complete comparison load for the previous four weeks")
        rows = (_row("Recorded workouts", _f(week["sessions"]),
                     f'{_f(week["hours"], 1)} h · {_f(week["run_km"], 1)} km running')
                + _row("Training load", _f(week["trimp"]), prior_text)
                + _row("Average sleep", _f(rest["avg_sleep_h"], 1, " h"),
                       f'{rest["sleep_nights"]} of 7 nights used'))
        summary = _narration(d.get("narration", {}).get("training"))
        week_card = _card("Training and recovery this week", f'<ul class="rows">{rows}</ul>{summary}',
                          f'{_short(week["from"])}–{_short(week["to"])} · recorded data', wide=True)
    saved = d.get("planned_week", {})
    sessions = saved.get("sessions", [])
    plan = ""
    if sessions or (saved.get("adaptive") and not d["brief"].get("knee_pause")):
        runs = {run["activity_id"] for run in d["runs"]}
        rows = "".join(_record_link(f'{_date_label(row["day"])} · {row["kind"].title()}',
                                    f'{row["minutes"]} min planned · ' +
                                    (f'{row["done_minutes"]} min done' if row["status"] == "done"
                                     else row["status"].capitalize()),
                                    _workout_link(d, row["activity_id"], runs) if row["activity_id"] else None)
                       for row in sessions)
        guidance = (f'<p>{_e(saved["adaptive"])}</p>' if saved.get("adaptive")
                    and not d["brief"].get("knee_pause") else "")
        plan = _card("Planned and done", guidance + (f'<ul class="record-list">{rows}</ul>' if rows else ""),
                     wide=True)
    body = plan + week_card
    if cue_review := _weekly_cue_review(d):
        body += _card("Coaching follow-up", cue_review, wide=True)
    run_ids = {r["activity_id"] for r in d["runs"]}
    calendar = d["calendar"]
    entries = []
    for day in sorted(calendar["detail_days"], reverse=True):
        for workout in calendar["days"][day].get("activities", []):
            if target := _workout_link(d, workout["id"], run_ids):
                entries.append(_record_link(_workout_name(workout), _date_label(day), target))
    if entries:
        recent = f'<ul class="record-list">{"".join(entries[:4])}</ul>'
        if len(entries) > 4:
            recent += ('<details><summary>More recent workouts</summary>'
                       f'<ul class="record-list">{"".join(entries[4:])}</ul></details>')
        body += _card("Recent workouts", recent, wide=True)
    body += (_card("Training load trend", fit, "Workout effort smoothed over time using workouts with usable load. "
                    "Recent load responds more quickly to workouts and rest.", wide=True)
             + _card("Load per week", wl, "Points combine duration and intensity. Weeks with unmeasured workouts have "
                     "no total. The latest week may still be in progress."
                     + (f" · Dashed: {_f(four_week_avg)} average of the previous four bars"
                        if four_week_avg is not None else ""), wide=True)
             + _outdoor_patterns_card(d.get("outdoor_patterns", {}))
             + _readiness_benchmark(d["readiness_benchmark"], run_ids))
    status = _status_label(d["brief"].get("garmin_training_status"))
    lede = (f"Garmin training status <b>{_e(status)}</b>" if status != "–" else
            "Your recorded workouts, load and recovery.")
    return _page("training", "Training", lede, body)


def _run_label(r: dict[str, Any]) -> str:
    return f'{_short(r["date"])} · {r["km"]:.1f} km · {r["pace"]}/km'


def _run_pace(seconds: float) -> str:
    minutes, seconds = divmod(round(seconds), 60)
    return f"{minutes}:{seconds:02d}"


def _running_block(d: dict[str, Any]) -> str:
    block = d.get("running_block")
    if not block or not block["has_runs"]:
        return _card("Training rhythm", '<p class="empty">No runs recorded in this block.</p>', wide=True)
    recent, previous = block["recent"], block["previous"]
    km = f'{recent["km"]:g} km' if recent["distance_count"] or not recent["runs"] else "—"
    prior_km = f'{previous["km"]:g} km' if previous["distance_count"] or not previous["runs"] else "—"
    longest = f'{recent["longest_km"]:g} km' if recent["distance_count"] else "—"
    stats = (
        ("Recorded distance", km, f"{prior_km} in prior block"),
        ("Running days", recent["days"], f'{previous["days"]} in prior block'),
        ("Longest run", longest, f'{recent["runs"]} runs in this block'),
    )
    measures = "".join(f'<div><dt>{_e(label)}</dt><dd>{_e(value)}</dd><small>{_e(note)}</small></div>'
                       for label, value, note in stats)
    tip = block["next"]
    pause = not (d.get("older_snapshot") or d.get("sync_retry_required")) and _pause_running(d["brief"])
    if pause:
        focus = d["brief"]["focus"]
        tip = {"title": focus["title"], "action": focus["detail"],
               "basis": "See today’s guidance", "target": "today"}
    body = (f'<section class="running-lead wide"><div class="running-next">'
            f'<p class="insight-label">{icon("run")} {"Today" if pause else "Next run"}</p>'
            f'<h3>{_e(tip["title"])}</h3>'
            f'<p>{_e(tip["action"])}</p><a class="flow-link" href="#{_e(tip["target"])}">'
            f'{_e(tip["basis"])}{icon("chev")}</a></div><div class="running-block-summary">'
            '<h3>Last four completed weeks</h3>'
            f'<dl class="running-measures">{measures}</dl></div></section>')
    if insight := d.get("narration", {}).get("running-insight"):
        body += _reviewed_insight(insight, title="AI running review",
                                  selection_title="Running readings selected by local AI")
    weeks = block["weeks"]
    weekly_rows = "".join(_row(_date_label(w["start"]) + ("" if w["complete"] else " · In progress"),
                               f'{w["km"]:g} km' if w["distance_count"] or not w["runs"] else "—",
                               f'{w["days"]} days · {w["runs"]} runs'
                               + (f' · {w["runs"] - w["distance_count"]} without distance'
                                  if w["runs"] > w["distance_count"] else "")) for w in reversed(weeks))
    distances = [(f'{w["start"]}{" · in progress" if not w["complete"] else ""}',
                  w["km"] if w["distance_count"] or not w["runs"] else None) for w in weeks]
    bars = both(bar_chart, distances, " km", nd=1, tones=["s1"] * (len(weeks) - 1) + ["muted"],
                x_label="Week starting Monday", y_label="Recorded distance (km)")
    body += (f'<section class="card wide running-anchor" id="running-block"><h3>Training rhythm</h3>{bars}'
             f'<p class="sub">Grey shows this week so far. Distances use available Garmin records.</p>'
             f'<details><summary>Weekly totals</summary><ul class="rows">{weekly_rows}</ul></details></section>')
    efforts = block["efforts"]
    points = [(row["day"], row["pace_s_per_km"], row["pulse"]) for row in efforts]
    chart = both(scatter, points, "Pace", "Moving heart rate", None, x_unit="min/km", y_unit="bpm",
                 absolute_x=True, absolute_y=True, x_format=_run_pace, dense=True)
    run_ids = {r["activity_id"] for r in d["runs"]}
    evidence = []
    for row in efforts:
        href = _workout_link(d, row["id"], run_ids)
        label = _e(_date_label(row["day"]))
        if href:
            label = f'<a class="source-link" href="{href}">{label}</a>'
        efficiency = row["decoupling_pct"]
        note = (row["kind"].replace("_", " ").capitalize()
                + (f' · {row["km"]:.1f} km' if row["km"] else "")
                + (f" · efficiency change {-efficiency:+g}%" if efficiency is not None else ""))
        evidence.append(f'<li><div>{label}<p class="sub">{_e(note)}</p></div>'
                        f'<b>{_run_pace(row["pace_s_per_km"])}/km · {row["pulse"]:g} bpm</b></li>')
    drift = ""
    if (decoupling := block["median_decoupling"]) is not None:
        change = (f"{abs(decoupling):g}% {'less' if decoupling > 0 else 'more'}" if decoupling
                  else "the same")
        drift = (f'<p class="sub"><b>Second-half efficiency</b> · {change} hill-adjusted speed per heartbeat '
                 f'at the median across {block["decoupling_count"]} runs.</p>')
    detail = (f'<details{" open" if len(efforts) <= 6 else ""}><summary>{len(efforts)} recorded efforts</summary>'
              f'<ul class="running-effort-list">{"".join(evidence)}</ul></details>' if evidence else "")
    body += (f'<section class="card wide running-anchor" id="running-efforts"><h3>Pace and effort</h3>'
             f'<p class="sub">{len(efforts)} qualifying steady outdoor runs from '
             f'{block["sampled"]} reviewed FIT recordings. Each dot is one run. '
             'Faster paces are on the left. Compare similar terrain and conditions.</p>'
             f'{chart}{detail}{drift}</section>')
    return body


def page_running(d: dict[str, Any]) -> str:
    runs = d["runs"]
    lst = "".join(f'<a class="tile" href="#run-{r["activity_id"]}"><b>{_e(_run_label(r))}</b>'
                  f'<span>Avg HR {_f(r.get("avg_hr"), unit=" bpm")} · cadence '
                  f'{_f((r["form"].get("cadence_spm") or {}).get("value"), unit=" steps/min")}</span>'
                  f'{icon("chev")}</a>' for r in runs)
    pr = d["predictions"].get("predictions") or {}
    estimates = []
    for k, values in pr.items():
        numbers = "".join(f'<span><small>{name}</small><b>{_e(values[key])}</b></span>'
                          for key, name in (("effective_vo2max", "Estimated fitness"),
                                            ("best_effort_vdot", "Best recorded effort"),
                                            ("garmin", "Garmin")) if values.get(key))
        if numbers:
            distance = {"half": "Half marathon", "marathon": "Marathon"}.get(k, k.upper())
            estimates.append(f'<li><strong>{distance}</strong><div>{numbers}</div></li>')
    races = ('<ul class="race-estimates">' + "".join(estimates) + '</ul>' if estimates else
             '<p class="empty">No race estimates from the available data.</p>')
    ms = d["marathon"]
    mshape = f'<p class="empty">{_e(ms.get("reason") or "More running history is needed.")}</p>'
    if ms.get("available"):
        f = ms["marathon_shape_pct"] / 100
        need = ms["needed_for"]
        marks = "".join(f'<span style="left:{min(100, v)}%">{_e(k)}</span>'
                        for k, v in need.items())
        mshape = (f'<div class="big">{ms["marathon_shape_pct"]}<small>%</small></div>'
                  f'<div class="track"><i style="width:{f * 100:.0f}%"></i></div>'
                  f'<div class="track-marks">{marks}</div>'
                  f'<p class="sub">You average {ms["weekly_km_avg"]} km per week. The model '
                  f'compares that with a reference of about {ms["weekly_km_target"]:.0f} km '
                  f'per week and long runs of {ms["long_run_target_km"]:.0f} km.</p>')
    fs = d["form"]["series"]
    cad = both(line_chart, [(s["date"], s["cadence_spm"]) for s in fs], " spm",
               y_label="Cadence (steps/min)")
    dynamics = []
    for key, title, unit, decimals in (
        ("step_length_m", "Stride length", "m", 2),
        ("ground_contact_ms", "Ground contact time", "ms", 0),
        ("vertical_oscillation_cm", "Vertical oscillation", "cm", 1),
        ("vertical_ratio_pct", "Vertical ratio", "%", 1),
    ):
        points = [(s["date"], s.get(key)) for s in fs if s.get(key) is not None]
        if points:
            chart = both(line_chart, points, f" {unit}", nd=decimals, y_label=f"{title} ({unit})")
            dynamics.append(_card(title, chart, running.FORM_GUIDE[key][0], wide=True))
    extra_form = ('<details class="wide secondary-metrics"><summary>Stride and contact trends</summary>'
                  f'<div class="grid">{"".join(dynamics)}</div></details>' if dynamics else "")
    body = (_running_block(d)
            + f'<nav class="card tiles wide" aria-label="Recent runs"><h3>Recent runs</h3>'
            f'{lst or "<p class=empty>No runs with detail yet.</p>"}</nav>'
            + _card("Steady run efficiency over time", _tests(d["tests"]),
                    "Similar-distance outdoor runs · grade-adjusted speed per heartbeat", wide=True)
            + _card("Running dynamics", cad + _form_reference() + extra_form, running.FORM_GUIDE["cadence_spm"][0],
                    wide=True)
            + '<details class="card wide secondary-metrics"><summary>Race planning estimates</summary>'
            + '<div class="grid">'
            + _card("Marathon shape", mshape, "Endurance readiness (Runalyze method)")
            + _card("Race time estimates", races, "Recorded efforts, endurance and max HR affect accuracy.")
            + '</div></details>')
    return _page("running", "Running", "", body)


def _tests(t: dict[str, Any]) -> str:
    if not t.get("runs"):
        return f'<p class="empty">{_e(t.get("reason"))}</p>'
    chart = both(line_chart, [(r["date"], r["ef"]) for r in t["runs"]], nd=2,
                 y_label="Speed per heartbeat", x_label="Run date")
    head = ""
    if t.get("available"):
        ch = t["ef_change_per_90d_pct"]
        head = (f'<div class="big">{ch:+.1f}<small>% per 90 days</small></div><p class="sub">'
                f'{len(t["runs"])} runs of about {t["reference_km"]} km. {_e(t["meaning"])}</p>')
    else:
        head = f'<p class="sub">{_e(t.get("reason"))}</p>'
    return head + chart


def _form_reference():
    notes = []
    spans = []
    for key, name in running.LABELS.items():
        meaning = running.FORM_GUIDE[key][0]
        notes.append(f'<dt>{_e(name)}</dt><dd>{_e(meaning)} {_e(running.FORM_CONTEXT[key])}</dd>')
        if ranges := running.reference_ranges(key):
            labels = " · ".join(f"{colour.title()} {span}" for colour, span in ranges)
            spans.append(_row(name, _e(running.FORM_UNITS[key]), labels))
    return (f'<details class="form-reference"><summary>Metric guide and colour bounds</summary>'
            f'<dl>{"".join(notes)}</dl><p>{_e(running.FORM_BANDS_NOTE)} {_e(running.FORM_SENSOR_NOTE)}</p>'
            f'<p>{_e(running.HEART_RATE_BOUNDS_NOTE)} The matched range spans the earlier comparable runs.</p>'
            f'<ul class="rows">{"".join(spans)}</ul>'
            f'<a class="source-link" href="{_e(running.GARMIN_FORM_SOURCE)}">Garmin’s running dynamics reference</a>'
            '</details>')


def page_run(r: dict[str, Any], d_trial: dict[str, Any] | None = None,
             summary: dict | None = None, *, run_ids: set[int] | None = None,
             run_check: int | None = None, post_run: dict | None = None) -> str:
    rows = ""
    units = {"cadence_spm": " steps/min", "step_length_m": " m", "ground_contact_ms": " ms",
             "vertical_oscillation_cm": " cm", "vertical_ratio_pct": "%"}
    for key, fm in r["form"].items():
        rng = GAUGE_RANGE.get(key)
        g = gauge(fm["value"], running.GAUGES[key], *rng,
                  marker2=fm.get("your_usual_at_this_pace"),
                  unit="") if rng else ""
        vs = fm.get("vs_usual_pct")
        baseline = (f'{vs:+.1f}% vs your usual at this pace' if vs is not None
                    else "Personal comparison needs more runs at this pace.")
        if "matched_range" in fm:
            low, high = fm["matched_range"]
            baseline += f' · Earlier matched range {low:g}–{high:g}{units[key]} ({fm["reference_runs"]} runs)'
        elif vs is not None and fm.get("reference_runs"):
            baseline += f' · Pace reference from {fm["reference_runs"]} earlier runs'
        meaning, check = running.FORM_GUIDE[key]
        rows += (f'<div class="form-row"><div class="fr-head"><span>{_e(fm["label"])}</span>'
                 f'<b>{fm["value"]:g}{units[key]}</b></div>{g}<p class="sub">{_e(baseline)}</p>'
                 f'<p class="metric-meaning">{_e(meaning)} {_e(running.FORM_CONTEXT[key])}</p>'
                 '<details><summary>What to try</summary>'
                 f'<p>{_e(check)}</p></details></div>')
    p = r["pacing"]
    first, *other = r["work_on"]
    work = f'<p class="run-first">{_e(first)}</p>'
    if other:
        rest = "".join(f'<li>{_e(w)}</li>' for w in other)
        work += f'<details><summary>More notes</summary><ul class="work">{rest}</ul></details>'
    facts = (_row("Pace", f'{_e(r["pace"])}<small>/km</small>')
             + _row("Average heart rate", f'{_f(r.get("avg_hr"))}<small> bpm</small>')
             + _row("Heart-rate change", f'{_f(p.get("hr_drift_bpm"), 1)}<small> bpm</small>',
                    "Second half of recorded moving time versus the first")
             + _row("Power (wrist)", f'{_f(r.get("power_w"))}<small> W</small>')
             + _row("Running effectiveness", _f(r.get("running_effectiveness"), 2),
                    "Speed per watt per kg. Compare your own runs with the same power source and conditions."))
    cue = r.get("cadence_experiment")
    followup = ""
    if cue:
        followup = (f'<p class="sub">{_e(cue["check"])} '
                    f'<a href="{_e(cue["source"])}" class="source-link">Cadence study</a></p>')
    body = (_trial_run_card(d_trial, r["activity_id"])
            + _card("What to try next", work + followup, wide=True)
            + _card("Run numbers", _narration(summary) + f'<ul class="rows">{facts}</ul>', wide=True)
            + f'<section class="card wide running-anchor" id="run-{r["activity_id"]}-form">'
              f'<h3>Running form</h3><p class="sub">{_e(running.FORM_BANDS_NOTE)} '
              f'{_e(running.FORM_SENSOR_NOTE)}</p>{rows}'
              '<p class="legend"><i class="mk"></i>This run <i class="mk2"></i>Your usual at this pace</p>'
              f'{_form_reference()}</section>')
    comparison = r["comparable_effort"]
    if post_run:
        source_rows = "".join(f'<li><a class="source-link" href="#{_e(row["page"])}">{_e(row["text"])}</a></li>'
                              for row in post_run["readings"])
        label = "Selected by local AI" if post_run["mode"] == "selected_post_run" else "Recorded comparison"
        body = (f'<section class="coach-change wide"><h3>Post-run review</h3>'
                f'<p class="insight-label">{label}</p><p class="say">{_e(post_run["observation"])}</p>'
                f'<p><b>Another explanation</b> · {_e(post_run["alternative"])}</p>'
                f'<p><b>Next comparable run</b> · {_e(post_run["question"])}</p>'
                f'<details><summary>Recorded evidence</summary><ul>{source_rows}</ul></details>'
                f'</section>') + body
    elif next_step := coach_review.after_run(comparison):
        options = coach_review.run_questions(r)
        selected = ""
        if type(run_check) is int and 1 <= run_check <= len(options):
            option = options[run_check - 1]
            selected = (f'<p class="insight-label">AI evidence check</p>'
                        f'<p><b>{_e(option["title"])}</b> · {_e(option["basis"])}</p>')
        body = (f'<section class="coach-change wide"><h3>Post-run review</h3>'
                f'<p class="say">{_e(run_evidence.headline(comparison))}</p>'
                f'{selected or f"<p>{_e(next_step)}</p>"}'
                f'<nav class="run-jumps" aria-label="Post-run links"><a class="flow-link" href="#run-{r["activity_id"]}-compare">'
                f'See matched runs{icon("chev")}</a>'
                f'<a class="flow-link" href="#today">Today’s guidance{icon("chev")}</a>'
                '</nav></section>') + body
    if replay := r.get("route_review"):
        rows = "".join(_row(f'{row["from_m"] / 1000:g}–{row["to_m"] / 1000:g} km',
                            f'{row["difference"]:+d} seconds',
                            f'{loads._hms(row["elapsed"])} this run · {loads._hms(row["prior_elapsed"])} earlier')
                       for row in replay["rows"])
        chart = both(line_chart, [(f'{row["to_m"] / 1000:g} km', row["difference"])
                                  for row in replay["rows"]], " s", reference=0,
                     x_label="Kilometre endpoint", y_label="Elapsed time difference (s)")
        previous = (f'<a class="flow-link" href="#run-{replay["activity_id"]}">'
                    f'Open earlier run{icon("chev")}</a>'
                    if replay["activity_id"] in (run_ids or set()) else "")
        body += _card("Same-route replay", chart + f'<ul class="rows">{rows}</ul>' + previous,
                      f'Elapsed time against {_e(_date_label(replay["date"]))}, including stops. '
                      'Above zero is slower.', wide=True)
    aid = r["activity_id"]
    sections = []
    jumps = []

    def add_section(key: str, title: str, content: str, *, opened: bool = False) -> None:
        jumps.append(f'<a class="flow-link" href="#run-{aid}-{key}">{_e(title)}{icon("chev")}</a>')
        sections.append(_run_section(aid, key, title, content, initially_open=opened))

    if r["trace"].get("stream"):
        add_section("trace", "Run timeline", _run_trace(r), opened=True)
    add_section("pacing", "Splits and timing", _run_pacing(r))
    if rows:
        jumps.append(f'<a class="flow-link" href="#run-{aid}-form">Running form{icon("chev")}</a>')
    if r["comparable_effort"]["available"]:
        add_section("compare", "Similar runs", _run_compare(r, run_ids or set()))
    jump_links = f'<nav class="run-jumps wide" aria-label="On this run">{"".join(jumps)}</nav>'
    return _page(f'run-{aid}', _run_label(r), _date_label(r["date"]),
                 jump_links + body + "".join(sections), back="#running")


def _run_section(aid: int, key: str, title: str, body: str, *, initially_open: bool = False) -> str:
    opened = " open" if initially_open else ""
    return (f'<details class="card wide run-section" id="run-{aid}-{key}"{opened}>'
            f'<summary>{_e(title)}</summary><div class="grid">{body}</div></details>')


def _run_compare(r: dict[str, Any], run_ids: set[int]) -> str:
    c = r["comparable_effort"]
    aid = r["activity_id"]
    current = {**c["this_run"], "start_local": r["start_local"], "days_before": 0}
    records = [*reversed(c["matches"]), current]
    labels = [row["start_local"].replace("T", " ")[:19] for row in records]
    labels = [f'{label} · #{row["activity_id"]}' if labels.count(label) > 1 else label
              for label, row in zip(labels, records, strict=True)]
    elapsed = {label: -row["days_before"] for label, row in zip(labels, records, strict=True)}
    rows = []
    for row, label in zip(reversed(records), reversed(labels), strict=True):
        k = row["activity_id"]
        pace = loads._hms(row["pace_s_per_km"])
        subtitle = (f"{row['avg_hr_bpm']:g} bpm · {pace}/km · "
                    f"{loads._hms(row['moving_s'])} moving · {row['climb_m_per_km']:g} m climb/km")
        rows.append(_record_link("This run" if k == aid else label[:16], subtitle,
                                 f"#run-{k}" if k != aid and k in run_ids else None))
    chart = ""
    if c["available"]:
        chart = both(line_chart, [(label, row["avg_hr_bpm"])
                                  for label, row in zip(labels, records, strict=True)], " bpm",
                     nd=1, band=c["observed_hr_range_bpm"], band_label="Earlier observed span",
                     reference=c["median_hr_bpm"], connect_points=False, elapsed=elapsed,
                     x_label="Run date", y_label="Moving heart rate (bpm)",
                     details={labels[-1]: "This run"})
        chart += (f'<p class="sub">Dashed line · median {c["median_hr_bpm"]:g} bpm. '
                  "Shading · observed span of earlier matches.</p>")
    method = (f'Up to {c["maximum_matches"]} earlier runs in {c["lookback_days"]} days. '
              f'Same outdoor run type, pace within {c["pace_window_s_per_km"]} s/km, '
              f'moving time within {c["duration_window_pct"]}% and climb within '
              f'{c["climb_window_m_per_km"]} m/km. Route and conditions can still differ.')
    body = (_card("Matched efforts", chart + f'<ul class="record-list">{"".join(rows)}</ul>',
                  _e(method), wide=True))
    check = run_evidence.next_check(c)
    body = (f'<p class="wide sub">{_e(run_evidence.headline(c))} {_e(check)}</p>'
            + body + _run_conditions_comparison(r["conditions_comparison"]))
    return body


def _run_conditions_comparison(records: list[dict]) -> str:
    if not records:
        return ""
    rows = []
    for item in records:
        current = item["recorded"]
        unit = (" " + item["unit"]) if item["unit"] else ""
        left = f'{_f(current["value"], 1, unit)} · {_f(current["hr_bpm"], 1)} bpm'
        right = f'{_f(item["earlier_value"], 1, unit)} · {_f(item["earlier_hr_bpm"], 1)} bpm'
        standard = conditions.AQI_STANDARDS.get(current["standard"], "")
        label = item["label"] + (f" ({standard})" if standard else "")
        kind = "Model estimate" if current.get("kind") == "model" else "Observation"
        change = current["hr_bpm"] - item["earlier_hr_bpm"]
        note = (f'Earlier median {right} across {len(item["earlier_runs"])} runs. '
                f'Heart-rate difference {change:+.1f} bpm. {kind} · {current["source"]}')
        rows.append(_row(label, _e(left), note))
    return _card("Conditions on similar runs", f'<ul class="rows">{"".join(rows)}</ul>',
                 "This run and earlier efforts, with weather readings covering most of each run.",
                 wide=True)


def _split_elapsed(seconds: float) -> str:
    whole, tenths = divmod(round(seconds * 10), 10)
    return f"{loads._hms(whole)}.{tenths}"


def _split_bars(splits: list[tuple[str, float]], reference: float, w: int = W) -> str:
    extent = max(1.0, *(abs(seconds - reference) for _, seconds in splits))
    limit = _ticks(0, extent)[-1]
    left, right, top, bottom, h = 57, w - 18, 32, 161, 207
    gap = (right - left) / len(splits)
    width = min(46, gap * .58)

    def x(i):
        return left + gap * (i + .5)

    def y(delta):
        return (top + bottom) / 2 - (bottom - top) / 2 * delta / limit

    center = y(0)
    title = "Seconds vs median split"
    g = _horizontal_scale([-limit, -limit / 2, 0, limit / 2, limit], left, right, y,
                          lambda n: f"{n:+g}" if n else "0")
    g += _axes(left, right, top, bottom, h, "Kilometre", title)
    g.append(f'<line x1="{left}" x2="{right}" y1="{center}" y2="{center}" class="zero"/>')
    for i, (label, seconds) in enumerate(splits):
        delta = seconds - reference
        endpoint = y(delta)
        display = (f'{_split_elapsed(seconds)} · {delta:+.1f} s vs median' if delta else
                   f'{_split_elapsed(seconds)} · median')
        tone = "split-slower" if delta > 0 else "split-faster" if delta < 0 else "split-even"
        g.append(f'<rect x="{x(i) - width / 2:.2f}" y="{min(endpoint, center) - (.8 if not delta else 0):.2f}" '
                 f'width="{width:.2f}" height="{max(1.6, abs(endpoint - center)):.2f}" class="{tone}"/>')
        g.append(_point(x(i), endpoint, label, display, "hit"))
        if len(splits) <= (12 if w > W else 6):
            y_text = min(endpoint, center) - 5
            g.append(f'<text x="{x(i):.2f}" y="{y_text:.2f}" text-anchor="middle" class="tick split-value">'
                     f'{loads._hms(seconds)}</text>')
    labels = [label.removeprefix("km ") for label, _ in splits]
    if len(labels) <= (16 if w > W else 10):
        g += [f'<text x="{x(i):.2f}" y="{bottom + 17}" text-anchor="middle" class="tick">{label}</text>'
              for i, label in enumerate(labels)]
    else:
        g += _x_ticks(labels, x, bottom, w > W)
    return _chart("bar", g, w, h, (left, right, top, bottom), "Kilometre", title,
                  static_readings=True)


def _split_chart(splits):
    if not splits:
        return '<p class="empty">No full kilometre recorded.</p>'
    reference = median(seconds for _, seconds in splits)
    rows = "".join(_row(label, _e(_split_elapsed(seconds))) for label, seconds in splits)
    return (f'<p class="chart-note">Median {_split_elapsed(reference)} · above is slower · below is faster.</p>'
            + both(_split_bars, splits, reference)
            + f'<details><summary>All {len(splits)} split times</summary><ul class="rows">{rows}</ul></details>')


def _run_pacing(r: dict[str, Any]) -> str:
    p = r["pacing"]
    splits = [(f"km {i}", seconds) for i, seconds in enumerate(p["km_split_s"], 1)]
    chart = _split_chart(splits)
    delta = p["half_split_delta_s"]
    half_note = "Needs at least 4 km of usable distance data"
    if delta is not None:
        half_note = ("About the same time in both halves" if abs(delta) <= 1 else
                     f"Second half {_f(abs(delta), 1)} seconds "
                     f'{"faster" if delta < 0 else "slower"} over equal recorded distance')
    moving, elapsed = p["recorded_moving_s"], p["recorded_elapsed_s"]
    timing = (_row("Recorded moving time", _e(loads._hms(moving)),
                   "Between nearby FIT samples with running speed")
              + _row("Recorded elapsed time", _e(loads._hms(elapsed)),
                     "From the first to the last FIT sample, including pauses and gaps")
              + _row("Garmin timer time", _e(loads._hms(p["garmin_timer_s"]) or "—"),
                     "Watch session timer, excluding pauses")
              + _row("Garmin elapsed time", _e(loads._hms(p["garmin_elapsed_s"]) or "—"),
                     "Watch session start to finish"))
    dc = p["decoupling_pct"]
    halves = ""
    if measured := p.get("effort_halves"):
        entries = "".join(f'<div><dt>{label}</dt><dd>{_run_pace(half["pace_s_per_km"])}/km</dd>'
                          f'<small>{half["hr"]:g} bpm</small></div>'
                          for label, half in zip(("First half", "Second half"), measured, strict=True))
        halves = f'<dl class="running-measures split-measures">{entries}</dl>'
    effort = (_row("Heart-rate change", f'{_f(p["hr_drift_bpm"], 1)}<small> bpm</small>')
              + _row("Efficiency change", f'{_f(-dc if dc is not None else None, 1)}<small> %</small>',
                     "Lower means less grade-adjusted speed per heartbeat in the second half"))
    body = (_card("Kilometre splits", chart + f'<p class="sub">{_e(half_note)}</p>',
                  "Elapsed time for each full recorded kilometre. "
                  "Pauses count toward these splits.", wide=True)
            + _card("Timing", f'<ul class="rows">{timing}</ul>')
            + _card("Pace and heart rate", halves + f'<ul class="rows">{effort}</ul>',
                    "Equal moving-time halves. Needs a steady run with enough heart-rate data."))
    if late_form := r.get("late_form"):
        units = {"cadence_spm": " steps/min", "step_length_m": " m",
                 "ground_contact_ms": " ms", "vertical_oscillation_cm": " cm"}
        rows = "".join(_row(running.LABELS[key], _e(f'{v["early"]:g} → {v["late"]:g}{units[key]}'),
                            f'{loads._hms(v["matched_s"])} comparable moving time in each half')
                       for key, v in late_form.items())
        body += _card("Running form at similar pace and grade", f'<ul class="rows">{rows}</ul>',
                      "First half → second half. Read this as a measured change and check whether it repeats.", wide=True)
    return body


def _condition_readout(window: dict | None) -> str:
    if not window:
        return ""
    items = []
    if "aqi" in window:
        items.append(f'AQI {window["aqi"]:g} ({conditions.AQI_STANDARDS[window["aqi_standard"]]})')
    for key, unit in (("temperature_c", " °C"), ("humidity_pct", "% humidity"),
                      ("wind_m_s", " m/s wind"), ("precipitation_mm", " mm precipitation")):
        if key in window:
            items.append(f"{window[key]:g}{unit}")
    return " · ".join([*items, f'{window["source"]} ({window["kind"]})'])


def _conditions_card(context: dict) -> str:
    rows = []
    snapshot = context["garmin_snapshot"]
    if snapshot:
        temp = _f(snapshot.get("temperature_c"), 1, " °C")
        humidity = (f'{snapshot["humidity_pct"]:g}% humidity' if "humidity_pct" in snapshot else "")
        value = " · ".join(v for v in (temp if "temperature_c" in snapshot else "", humidity,
                                      snapshot.get("description")) if v)
        rows.append(_row(snapshot["source"], _e(value), snapshot.get("reference_time", "")))
    windows = []
    for window in context["windows"]:
        start = window["start_utc"].replace("T", " ").removesuffix("+00:00")
        end = window["end_utc"].replace("T", " ").removesuffix("+00:00")
        windows.append(_row("Conditions window", _e(_condition_readout(window)), f"{start} to {end} UTC"))
    if not rows and not windows:
        return ""
    note = ("Timed readings appear on the chart where their source window covers a sample."
            if context["windows"] else "Garmin’s saved snapshot for this activity.")
    body = f'<ul class="rows">{"".join(rows)}</ul>' if rows else ""
    if windows:
        body += (f'<details><summary>{len(windows)} timed source windows</summary>'
                 f'<ul class="rows">{"".join(windows)}</ul></details>')
    return _card("Outdoor conditions", body, note, wide=True)


def _hr_zone_bounds(raw: str | None) -> list[float]:
    try:
        values = json.loads(raw or "null")
    except ValueError:
        return []
    if (not isinstance(values, list) or not 2 <= len(values) <= 8
            or not all(type(value) in (int, float) and 0 < value <= 255 for value in values)
            or not all(left < right for left, right in pairwise(values))):
        return []
    return values


def _trace_rating(key: str, value: float, hr_bounds: tuple | list) -> tuple[str, str] | None:
    if rating := running.rate(key, value):
        label = "lowest reference band" if rating["colour"] == "red" else rating["label"]
        return rating["colour"], f"Garmin band: {label}"
    if key == "hr" and hr_bounds:
        colours = ("blue", "green", "green", "orange", "red", "purple")
        for index, upper in enumerate(hr_bounds):
            if value < upper:
                return colours[min(index, len(colours) - 1)], f"Recorded heart-rate band {index + 1}"
    return None


def _trace_legend(key, label, hr_bounds, *, secondary=False, shared_scale=False):
    stroke = "Dashed" if secondary else "Solid"
    scale = (" · left axis" if shared_scale else " · right axis") if secondary else ""
    bands = running.GAUGES.get(key)
    band_key = ""
    if bands:
        labels = {"red": "lowest band", "orange": "below average", "green": "average",
                  "blue": "above average", "purple": "top 5%"}
        swatches = "".join(f'<span class="zone-{colour}">{labels[colour]}</span>' for _, colour, _ in bands)
        band_key = f'<span class="trace-bands" aria-label="Garmin reference bands">{swatches}</span>'
    if key in running.FORM_GUIDE:
        band_key += f'<span class="chart-definition">{_e(running.FORM_GUIDE[key][0])}</span>'
    if key in {"vertical_oscillation_cm", "vertical_ratio_pct"}:
        band_key += '<span class="chart-definition">Colours use the chest-sensor reference.</span>'
    if key == "hr" and hr_bounds:
        band_key = f'<span class="chart-definition">{_e(running.HEART_RATE_BOUNDS_NOTE)}</span>'
    track = f' class="chart-key overlay-secondary" data-overlay-track="{key}"' if secondary else ' class="chart-key"'
    return f'<p{track}><b>{_e(label)}</b> · {stroke}{scale}{band_key}</p>' if secondary or band_key else ""


def _paired_chart(stream: list[dict[str, Any]], primary: tuple, alternatives: tuple,
                  interval: int, w: int = W, *, context_by_second: dict[int, dict] | None = None,
                  faster_at_top: bool = False, hr_bounds: tuple | list = (),
                  crossings: tuple = (), elapsed_end: int = 0,
                  date_axis: bool = False, shared_scale: bool = False,
                  context: dict | None = None) -> str:
    """Compare two series on a shared time axis, with a second scale when units differ."""
    akey, alabel, axis_a, afmt = primary

    allow_zero = {"power_w", "distance_km", "long_load", "short_load", "sleep_score"}

    def series(key: str) -> dict[int, float]:
        return {p["t_s"]: value for p in stream
                if isinstance(value := p.get(key), (float, int)) and math.isfinite(value)
                and (key != "sleep_score" or value <= 100)
                and (value > 0 or key == "altitude_m" or (key in allow_zero and value == 0))}

    a = series(akey)
    if len(a) < 2 or stream[0]["t_s"] == stream[-1]["t_s"]:
        return '<p class="empty">Too few recorded points for this chart.</p>'
    options = []
    for key, label, axis, fmt in alternatives:
        samples = {t: value for t, value in series(key).items() if t in a}
        if len(samples) >= 3:
            options.append((key, label, axis, fmt, samples))
    h, left, right, top, bottom = 186, 52, w - (47 if options or crossings else 24), 28, 140
    start, end = stream[0]["t_s"], max(stream[-1]["t_s"], elapsed_end)

    def x(seconds: float) -> float:
        return left + (right - left) * (seconds - start) / (end - start)

    context = context or {}
    band = context.get("band")
    trend = context.get("trend", {})
    chart_values = list(a.values()) + list(band or ()) + list(trend.values())
    common_values = chart_values.copy()
    if shared_scale:
        common_values += [value for *_, samples in options for value in samples.values()]

    gap = 1 if date_axis else 2 * interval

    def track(key, values, caption, fmt, *, secondary=False, reverse=False):
        ticks = ([0, 25, 50, 75, 100] if key == "sleep_score" else
                 _ticks(*_scale(common_values if shared_scale else list(values.values()) if secondary else chart_values)))
        low, high = ticks[0], ticks[-1]

        def y(value: float) -> float:
            ratio = (value - low) / (high - low)
            return top + (bottom - top) * ratio if reverse else bottom - (bottom - top) * ratio

        if secondary:
            parts = ([] if shared_scale else [f'<path class="overlay-axis" d="M{right},{top}V{bottom}"/>'])
            parts.append(f'<text x="{right}" y="{top - 9}" class="axis-label overlay-label" '
                         f'text-anchor="end">{_e(caption)}</text>')
            if not shared_scale:
                parts += [f'<text x="{right + 6}" y="{y(tick) + 4:.2f}" class="tick overlay-label">'
                          f'{_e(fmt(tick))}</text>' for tick in ticks]
        else:
            parts = _horizontal_scale(ticks, left, right, y, fmt)
            parts += _axes(left, right, top, bottom, h, "", caption)[:2]
        base = "s2" if secondary else "s1"
        paths: dict[str, list[str]] = {}
        samples = [(second, value, _trace_rating(key, value, hr_bounds)) for second, value in values.items()]
        ends = {}

        def segment(colour, start_point, end_point):
            commands = paths.setdefault(colour, [])
            if ends.get(colour) != start_point:
                commands.append("M" + start_point)
            commands.append("L" + end_point)
            ends[colour] = end_point

        for (t0, v0, rate0), (t1, v1, rate1) in pairwise(samples):
            if t1 - t0 > gap:
                continue
            col0, col1 = (rate[0] if rate else base for rate in (rate0, rate1))
            x0, x1, y0, y1 = x(t0), x(t1), y(v0), y(v1)
            first, last = f'{x0:.2f},{y0:.2f}', f'{x1:.2f},{y1:.2f}'
            if col0 == col1:
                segment(col0, first, last)
            else:
                mid = f'{(x0 + x1) / 2:.2f},{(y0 + y1) / 2:.2f}'
                segment(col0, first, mid)
                segment(col1, mid, last)
        for colour, path in paths.items():
            tone = colour if colour == base else f"zone-line zone-{colour}"
            style = " overlay-line" if secondary else ""
            parts.append(f'<path class="ln {tone}{style}" d="{" ".join(path)}"/>')
        return parts, y

    g, y_a = track(akey, a, axis_a, afmt if faster_at_top else _tick_number, reverse=faster_at_top)
    if band:
        g.insert(0, f'<rect class="band" x="{left}" y="{y_a(band[1]):.2f}" width="{right-left}" '
                    f'height="{y_a(band[0])-y_a(band[1]):.2f}"><title>{_e(context["band_label"])}</title></rect>')
    if trend and date_axis:
        dates = [date.fromordinal(t).isoformat() for t in range(start, end + 1)]
        g.append(_smooth_line(dates, trend, lambda i: x(start + i), y_a))
    guides = []
    last_label = left - 28
    for km, elapsed in enumerate(crossings, 1):
        if start < elapsed <= end:
            position = x(elapsed)
            guides.append(f'<line x1="{position:.2f}" x2="{position:.2f}" y1="{top}" y2="{bottom}">'
                          f'<title>Km {km} · {loads._hms(elapsed)} elapsed</title></line>')
            if position - last_label >= 28:
                label_x = min(position, right - 10)
                guides.append(f'<text x="{label_x:.2f}" y="{top + 12}" text-anchor="middle">{km}</text>')
                last_label = position
    if guides:
        g.insert(0, f'<g class="split-guides" aria-hidden="true">{"".join(guides)}</g>')
    context_labels: dict[str, int] = {}
    x_label = "Date" if date_axis else "Elapsed time"

    def label_at(t):
        return date.fromordinal(t).isoformat() if date_axis else loads._hms(t)

    previous = None
    for t, v in a.items():
        starts_segment = previous is None or t - previous > gap
        condition = _condition_readout((context_by_second or {}).get(t))
        index = context_labels.setdefault(condition, len(context_labels)) if condition else None
        reading = f"{alabel} {afmt(v)}" + ("/km" if faster_at_top else "")
        rating = _trace_rating(akey, v, hr_bounds)
        if label_at(t) in trend:
            reading += f' · {context["trend_label"]}: {afmt(trend[label_at(t)])}'
        marker = "context-dot" if starts_segment or date_axis else "hit"
        if rating:
            marker = f"zone-dot zone-{rating[0]}"
            reading += f" · {rating[1]}"
        g.append(_point(x(t), y_a(v), label_at(t), reading, cls=marker, condition_index=index))
        previous = t
    weekdays = date_axis and end - start <= 6
    ticks_at = (list(range(start, end + 1)) if weekdays else
                sorted({start, (end + start) // 2, end}))
    labels = [label_at(t) for t in ticks_at]
    g += _x_ticks(labels, lambda i: x(ticks_at[i]), bottom, w > W, weekdays=weekdays)
    g.append(f'<text x="{(left + right) / 2:.1f}" y="{h - 8}" text-anchor="middle" '
             'class="axis-label">' + x_label + "</text>")
    buttons = []
    legend = [_trace_legend(akey, alabel, hr_bounds)]
    for key, label, axis, fmt, samples in options:
        pace = key == "pace_s_km"
        parts, y_overlay = track(key, samples, axis, fmt if pace else _tick_number, secondary=True, reverse=pace)
        legend.append(_trace_legend(key, label, hr_bounds, secondary=True, shared_scale=shared_scale))
        readings = {}
        last = None
        for t, value in samples.items():
            readings[t] = f"{label} {fmt(value)}"
            if rating := _trace_rating(key, value, hr_bounds):
                colour, description = rating
                readings[t] += f" · {description}"
                parts.append(f'<circle class="zone-dot zone-{colour}" cx="{x(t):.2f}" '
                             f'cy="{y_overlay(value):.2f}" r="3"/>')
            elif last is None or t - last > gap:
                parts.append(f'<circle class="overlay-dot" cx="{x(t):.2f}" cy="{y_overlay(value):.2f}" r="1.6"/>')
            last = t
        g.append(f'<g class="overlay-secondary" data-overlay-track="{key}">{"".join(parts)}</g>')
        buttons.append(f'<button type="button" class="overlay-control" data-overlay-control="{key}" '
                       f'data-readings="{_e(json.dumps([readings.get(t) for t in a], ensure_ascii=False))}" '
                       f'aria-pressed="false">{_e(label)}</button>')
    controls = (f'<div class="overlay-options" role="group" aria-label="Compare with">'
                f'<span>Compare with</span>{"".join(buttons)}</div>') if buttons else ""
    return _chart("line", g, w, h, (left, right, top, bottom), x_label, axis_a,
                  controls=controls + "".join(legend), dense=not date_axis,
                  condition_labels=list(context_labels))


def _run_trace(r: dict[str, Any]) -> str:
    trace = r["trace"]
    stream = trace.get("stream") or []
    for_chart = [{**p, "pace_s_km": 1000 / p["speed_m_s"] if p.get("pace") else None} for p in stream]
    interval = trace.get("every_s", 10)
    crossings = tuple(r["pacing"].get("km_crossings_s") or ())
    timeline = {"crossings": crossings, "elapsed_end": r["pacing"].get("recorded_elapsed_s") or 0}
    context = r["conditions"]
    near_sample = conditions.for_samples(trace.get("start_utc"), stream, context)
    heart_rate = ("hr", "Heart rate", "Heart rate (bpm)", lambda v: _f(v, unit=" bpm"))
    cadence = ("cadence_spm", "Cadence", "Cadence (steps/min)", lambda v: _f(v, unit=" steps/min"))
    step = ("step_length_m", "Step length", "Step length (m)", lambda v: _f(v, 2, " m"))
    power = ("power_w", "Power", "Power (W)", lambda v: _f(v, unit=" W"))
    climb = ("altitude_m", "Elevation", "Elevation (m)", lambda v: _f(v, unit=" m"))
    pace = ("pace_s_km", "Pace", "Pace (min/km)", loads._hms)
    distance = ("distance_km", "Distance", "Distance (km)", lambda v: _f(v, 2, " km"))
    pace_hr = both(_paired_chart, for_chart, pace,
                   (heart_rate, cadence, climb, power, distance), interval,
                   context_by_second=near_sample, faster_at_top=True, hr_bounds=r.get("hr_zone_bounds", ()),
                   **timeline)
    contact = ("ground_contact_ms", "Ground contact", "Ground contact (ms)",
               lambda v: _f(v, unit=" ms"))
    bounce = ("vertical_oscillation_cm", "Bounce", "Bounce (cm)", lambda v: _f(v, 1, " cm"))
    ratio = ("vertical_ratio_pct", "Vertical ratio", "Vertical ratio (%)",
             lambda v: _f(v, 1, "%"))
    cadence_step = both(_paired_chart, for_chart, cadence,
                        (step, pace, heart_rate, power, contact, bounce, ratio), interval,
                        hr_bounds=r.get("hr_zone_bounds", ()), **timeline)
    elevation = both(_paired_chart, for_chart, climb, (pace, heart_rate, power, distance), interval,
                     hr_bounds=r.get("hr_zone_bounds", ()), **timeline)
    power_detail = ""
    if sum(p.get("power_w") is not None for p in stream) >= 3:
        power_chart = both(_paired_chart, for_chart, power, (pace, heart_rate, climb, cadence), interval,
                           hr_bounds=r.get("hr_zone_bounds", ()), **timeline)
        power_detail = (f'<details class="card wide"><summary><strong>Running power</strong></summary>'
                        f'{power_chart}</details>')
    drift = r["pacing"].get("hr_drift_bpm")
    cue = ("" if drift is None else
           f'Heart rate averaged {_f(abs(drift), 1)} bpm {"higher" if drift > 0 else "lower"} '
           "in the second half of moving time." if drift else
           "Average heart rate was the same in both halves of moving time.")
    if r.get("hr_zone_bounds"):
        cue += " Heart-rate colors use the bands saved with this workout."
    toggle = ('<label class="split-toggle wide"><input type="checkbox"> Kilometre splits</label>'
              if crossings else "")
    body = (toggle + _card("Pace", pace_hr, cue, wide=True)
            + _card("Running form", cadence_step + _form_reference(),
                    "Compare form at similar paces and on similar terrain.", wide=True)
            + _card("Elevation", elevation, wide=True)
            + power_detail
            + _conditions_card(context))
    return body


def page_body(d: dict[str, Any]) -> str:
    fa = d["fitness_age"]
    lev = "".join(_row(x["lever"] if x["lever"] == "BMI" else x["lever"].capitalize(),
                       f'{_f(x["current"], 1)} → {_f(x["target"], 1)}'
                       f'<small> {_e(x.get("unit"))}</small>',
                       f'Garmin estimates age {_f(x["fitness_age_if_reached"], 1)} at that target'
                       if x["fitness_age_if_reached"] is not None else "")
                  for x in (fa.get("levers") or [])
                  if x["current"] is not None and x["target"] is not None)
    ag = d["ageing"]
    ag_html = (f'<div class="big">{ag["pace_of_ageing"]:.1f}<small>years/year</small></div>'
               f'<p class="sub">{_e(ag["meaning"])}</p>' if ag.get("available")
               else f'<p class="empty">{_e(ag.get("reason"))}</p>')
    mo = d["month"]
    names = {"sessions": ("Sessions", 0), "hours": ("Training hours", 1),
             "run_km": ("Running km", 1), "avg_sleep_h": ("Average sleep h", 1),
             "avg_resting_hr": ("Resting HR", 0), "avg_steps": ("Steps / day", 0),
             "avg_hrv": ("HRV ms", 0)}
    mrows = "".join(_row(lab, _f(mo["this_month"].get(k), nd),
                         f'{mo["change"].get(k):+,.{nd}f} vs month before'
                         if isinstance(mo["change"].get(k), (int, float)) else "")
                    for k, (lab, nd) in names.items())
    body = ""
    if fa.get("garmin_fitness_age") is not None:
        body += _card("Fitness age", f'<div class="big">{_f(fa.get("garmin_fitness_age"), 1)}'
                  f'<small> yrs</small></div><p class="sub">Calendar age '
                  f'{_e(fa.get("chronological_age"))} · best reachable '
                  f'{_f(fa.get("achievable_age"), 1)}</p><ul class="rows">{lev}</ul>',
                  "Garmin’s estimate")
    if ag.get("available"):
        body += _card("Fitness-age trend", ag_html, "Change in Garmin’s estimate per year")
    body += _card(f"Month report · {mo['month']}", f'<ul class="rows">{mrows}</ul>',
                  "See your month in detail", wide=True, href="#month-detail")
    if "vo2_reference" in d:
        body += _card("VO₂max reference", vo2_reference(d["vo2_reference"]),
                      "Garmin and our effective estimate, shown separately", wide=True)
    return _page("body", "Body", "Changes over months.", body, back="#trends")


def _month_label(month: str) -> str:
    return date.fromisoformat(month + "-01").strftime("%B %Y")


def _date_label(day: str) -> str:
    return date.fromisoformat(day).strftime("%a, %-d %b %Y")


def _history_nav(d: dict[str, Any], current: str, *, day: str | None = None,
                 month: str | None = None) -> str:
    calendar = d["calendar"]
    if day not in calendar["detail_days"]:
        day = max(calendar["detail_days"], default=None)
    month = month or calendar["current_month"]
    controls = (
        ("Day", f"#day-{day}" if day else None),
        ("Week", "#history"),
        ("Month", f"#month-{month}"),
        ("Year", "#month-detail"),
    )
    links = []
    for label, href in controls:
        if href:
            active = ' aria-current="page"' if label == current else ""
            links.append(f'<a href="{href}"{active}>{label}</a>')
    return f'<nav class="history-tabs wide" aria-label="History periods">{"".join(links)}</nav>'


def _record_link(label: str, note: str, href: str | None = None) -> str:
    caption = f'<small>{_e(note)}</small>' if note else ""
    content = f'<span><strong>{_e(label)}</strong>{caption}</span>'
    return (f'<li><a class="record-link" href="{href}">{content}{icon("chev")}</a></li>'
            if href else f'<li class="record-link">{content}</li>')


def _date_list(days: list[str], calendar: dict[str, Any]) -> str:
    if not days:
        return '<p class="empty">No readings or workouts recorded in this period.</p>'
    rows = []
    for day in days:
        row = calendar["days"][day]
        daily, sleep = row.get("daily", {}), row.get("sleep", {})
        notes = []
        if daily.get("steps") is not None:
            notes.append(_f(daily["steps"]) + " steps")
        if (sleep.get("sleep_s") or 0) >= 10800:
            notes.append(_f(sleep["sleep_s"] / 3600, 1) + " h sleep")
        if day < calendar["detail_start"]:
            if daily.get("resting_hr") is not None:
                notes.append(_f(daily["resting_hr"]) + " bpm resting")
            if row.get("hrv") is not None:
                notes.append(_f(row["hrv"], 1) + " ms HRV")
        if row.get("activities"):
            count = len(row["activities"])
            notes.append(f'{count} {"workout" if count == 1 else "workouts"}')
        href = f"#day-{day}" if day >= calendar["detail_start"] else None
        rows.append(_record_link(_date_label(day), " · ".join(notes), href))
    return f'<ul class="record-list">{"".join(rows)}</ul>'


def _coverage_rows(windows, unit):
    rows = []
    for label, item in windows.items():
        first, last = (item[key] for key in ("first", "last"))
        date_range = f'{_date_label(first)} through {_date_label(last)}'
        gaps = item["gap_count"]
        note = f'{date_range} · {item["missing"]} dates without usable readings in {gaps} gap{"s" if gaps != 1 else ""}'
        if sparse := item["sparse_gaps"]:
            note += " · missing " + ", ".join(_short(start) if start == end else
                                             f"{_short(start)}–{_short(end)}" for start, end in sparse)
        elif item["longest"]:
            start, end = item["longest"]
            gap = _date_label(start) if start == end else f'{_date_label(start)} through {_date_label(end)}'
            note += f' · longest gap {gap}'
        typical = item["typical"]
        if typical is None:
            value = f'{item["count"]} usable readings · {baseline.MIN_READINGS} needed for a baseline'
        else:
            median, low, high = typical
            value = (f'{_f(median, 1, unit)} median · {_f(low, 1)}–{_f(high, 1, unit)} middle half '
                     f'· {item["count"]} readings')
        rows.append(_row(label, _e(value), note))
    return f'<ul class="rows">{"".join(rows)}</ul>'


def _archive_baselines(coverage):
    if not coverage:
        return ""
    metrics = "".join(f'<details><summary>{_e(label)}</summary>{_coverage_rows(coverage[key], unit)}</details>'
                      for key, (label, unit) in baseline.METRICS.items())
    return _card("What your archive can tell you",
                 '<p>Compare your recent readings with the preceding 28 days, 90 days and all earlier '
                 'records available in this dashboard’s archive. Each window ends before this dashboard’s '
                 'date. The middle half describes the readings you recorded.</p>' + metrics, wide=True)


def page_history_week(d: dict[str, Any]) -> str:
    calendar = d["calendar"]
    steps = [(day, calendar["days"].get(day, {}).get("daily", {}).get("steps"))
             for day in recovery._days_back(d["end"], 7)]
    chart = both(bar_chart, steps, " steps", y_label="Daily steps", weekdays=True)
    span = f'{_short(calendar["week_start"])}–{_short(d["end"])}'
    body = (_history_nav(d, "Week")
            + _card("Steps by day", chart, wide=True)
            + _card("Open a day", _date_list(calendar["week"], calendar), wide=True)
            + _archive_baselines(calendar.get("baseline_coverage")))
    return _page("history", "Week history", span, body, back="#trends")


def page_history_month(d: dict[str, Any], month: str) -> str:
    c = d["calendar"]
    days = c["by_month"].get(month, [])
    first = date.fromisoformat(month + "-01")
    to = min(date.fromisoformat(d["end"]),
             (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1))
    slots = recovery._days_back(to.isoformat(), (to - first).days + 1)
    sleep = []
    for day in slots:
        seconds = c["days"].get(day, {}).get("sleep", {}).get("sleep_s") or 0
        sleep.append((day, seconds / 3600 if seconds >= 10800 else None))
    chart = _sleep_trend_chart(sleep, d.get("sleep_review", {}).get("nights", {}))
    recent = any(day >= c["detail_start"] for day in days)
    days_label = "Daily readings" if not recent else "Open a recent day"
    body = (_history_nav(d, "Month", month=month, day=days[-1] if days else None)
            + _card("Sleep by night", chart, wide=True)
            + _card(days_label, _date_list(days, c),
                    "Full day pages cover the last 30 days. Ask Claude for older daily detail.",
                    wide=True))
    return _page(f"month-{month}", _month_label(month),
                 "Month to date" if month == c["current_month"] else "Recorded days",
                 body, back="#month-detail")


def _resting_pulse_card(check, *, flagged_only=False):
    if not check or (flagged_only and not check["verify"]):
        return ""
    value = check["value"]
    comparison = "Fewer than 14 usable readings in the prior 28 days. See the longer baselines below."
    if check["median"] is not None:
        lo, hi = check["range"]
        relation = {"lower": "Below", "higher": "Above", "near": "Within"}[check["direction"]]
        comparison = (f'{relation} your personal reference · '
                      f'{check["median"]:g} bpm median · {lo:.0f}–{hi:.0f} bpm review range · '
                      f'{check["count"]} prior readings.')
    advice = ""
    if check["verify"]:
        concern = ("unusually low or high" if check["direction"] == "higher" else "unusually low")
        advice = ('<p><b>Check it while awake.</b> Sit quietly, then count your wrist pulse for '
                  f'a full minute. If it keeps reading {concern} for you, ask a clinician. '
                  'If a sudden unusual change comes with chest pain, shortness of breath, '
                  'dizziness or fainting, seek urgent medical help.</p>')
    sources = {"pa_daily_summary": "Garmin Personal API", "user_summary": "Garmin Connect",
               "ex_daily_summary": "Garmin export"}
    rows = "".join(_row(label, ", ".join(f"{v:g} bpm" for v in check["sources"][key]))
                   for key, label in sources.items() if key in check["sources"])
    disagreement = ('<p class="sub">Garmin records for this date report different estimates.</p>'
                    if len(set().union(*check["sources"].values())) > 1 else "")
    source_note = (f'{disagreement}<details><summary>Source readings for this date</summary>'
                   f'<ul class="rows">{rows}</ul>'
                   '</details>' if rows else "")
    history = (f'<details><summary>Resting pulse baseline coverage</summary>'
               f'{_coverage_rows(check["coverage"], " bpm")}</details>' if "coverage" in check else "")
    return _card("Resting pulse check", f'<p><b>{value:g} bpm · Garmin daily resting estimate</b></p>'
                 f'<p>{_e(comparison)}</p>{advice}'
                 '<p class="sub">Garmin describes this as the lowest 30-minute average in 24 hours, which '
                 'can be during sleep. A low wrist reading can occur in active adults. Compare it '
                 'with an awake pulse and your own history.</p>'
                 '<p class="chart-note"><a class="source-link" href="https://support.garmin.com/en-US/?faq=F8YKCB4CJd5PG0DR9ICV3A">'
                 'Garmin’s calculation</a> · <a class="source-link" href="https://www.heart.org/en/health-topics/high-blood-pressure/the-facts-about-high-blood-pressure/all-about-heart-rate-pulse/">'
                 'American Heart Association pulse guidance</a></p>' + source_note + history, wide=True)


def _intraday_pulse_card(pulse, activities, *, day, zone):
    if not pulse:
        return ""
    slots = pulse["slots"]
    peak = max((s for s in slots if s["count"] >= 2), key=lambda s: s["median"], default=None)
    headline = (f'Highest 15-minute median · {peak["median"]:g} bpm at {peak["time"]}.'
                if peak else "The available windows contain single readings.")
    detail = {s["time"]: f'{s["count"]} sample{"s" if s["count"] != 1 else ""}' for s in slots}
    workouts = [(a["start"][11:16], a["name"] or "Workout") for a in activities
                if a["start"][:10] == day and len(a["start"]) >= 16]
    guides = {}
    for clock, name in workouts:
        try:
            local = datetime.fromisoformat(f"{day}T{clock}").replace(tzinfo=zone)
        except ValueError:
            continue
        if local.utcoffset() == local.replace(fold=1).utcoffset():
            guides[local.timestamp() / 60] = name
    chart = both(line_chart, [(s["time"], s["median"]) for s in slots], " bpm", nd=0,
                 x_label="Local time", y_label="Heart rate (bpm)", max_gap=15.1, whiskers=True,
                 band_series=[s["range"] for s in slots], band_label="sample span",
                 elapsed={s["time"]: s["minute"] for s in slots}, details=detail,
                 break_gaps=True, guides=guides)
    source = "Garmin Personal API" if pulse["dataset"] == "pa_heart_rate" else "Garmin Connect"
    markers = "".join(_row(clock, _e(name), "Recorded workout start on this date")
                      for clock, name in workouts)
    marker_key = " Dashed guides mark workout starts where the timeline covers them." if guides else ""
    return _card("Heart rate during the day", f'<p><b>{_e(headline)}</b></p>{chart}'
                 f'<p class="chart-note">{pulse["samples"]} samples in {len(slots)} windows '
                 f'· {source} · Line: 15-minute median · bars: recorded low to high. '
                 f'Gaps show windows without samples.{marker_key}</p>'
                 + (f'<ul class="rows">{markers}</ul>' if markers else ""), wide=True)


def _intraday_wellness_card(wellness, day, zone):
    start = datetime.fromisoformat(day).replace(tzinfo=zone)
    time_ticks = [(f"{hour:02}:00", (start + timedelta(hours=hour)).timestamp() / 60)
                  for hour in (0, 6, 12, 18, 24)]
    panels = []
    for metric, title in (("stress", "Garmin stress"), ("battery", "Garmin Body Battery")):
        series = wellness.get(metric)
        if not series:
            panels.append(f'<div><h4>{title}</h4><p class="sub">Timeline unavailable for this date.</p></div>')
            continue
        slots = series["slots"]
        first, last = series["first"], series["last"]
        if metric == "stress":
            peak = max((slot for slot in slots if slot["count"] >= 2),
                       key=lambda slot: slot["value"], default=None)
            headline = (f'Highest measured 15-minute median · {peak["value"]:g}/100 at {peak["time"]}.'
                        if peak else "The available windows contain single readings.")
            ranges = [slot["span"] for slot in slots]
            method = "Line shows the window median. Bars show the observed low and high."
        else:
            headline = (f'{first[1]:g}/100 at {first[0]} → {last[1]:g}/100 at {last[0]}.'
                        if series["count"] >= 2 else f'{first[1]:g}/100 at {first[0]}.')
            ranges = None
            method = "Each window shows its last recorded reading."
        chart = line_chart([(slot["time"], slot["value"]) for slot in slots], "/100",
                     nd=1, x_label="Local time", y_label=f"{title} (0–100)",
                     elapsed={slot["time"]: slot["minute"] for slot in slots}, time_ticks=time_ticks,
                     value_ticks=(0, 25, 50, 75, 100), break_gaps=True, max_gap=15.1,
                     band_series=ranges, whiskers=True, band_label="recorded span",
                     details={slot["time"]: f'{slot["count"]} recorded' for slot in slots})
        panels.append(f'<div><h4>{title}</h4><p><b>{_e(headline)}</b></p>{chart}'
                      f'<p class="chart-note">{series["count"]} readings · {method}</p></div>')
    return _card("Stress and Body Battery", f'<div class="wellness-panels">{"".join(panels)}</div>',
                 "Garmin Connect · Empty stretches have no usable recordings. "
                 "The two Garmin estimates share some inputs.", wide=True)


def page_history_day(d: dict[str, Any], day: str) -> str:
    row = d["calendar"]["days"][day]
    daily = row.get("daily", {})
    sleep = row.get("sleep", {})
    measurements = [
        ("Steps", daily.get("steps"), " steps", 0),
        ("Daily distance", daily["distance_m"] / 1000 if daily.get("distance_m") is not None else None,
         " km", 2),
        ("Garmin resting estimate", daily.get("resting_hr"), " bpm", 0),
        ("Overnight HRV", row.get("hrv"), " ms", 1),
        ("Daytime stress", daily.get("stress_avg"), "/100", 0),
        ("Garmin daily Pulse Ox", daily.get("spo2_avg"), "%", 1),
        ("Body Battery low", daily.get("body_battery_min"), "/100", 0),
        ("Body Battery high", daily.get("body_battery_max"), "/100", 0),
    ]
    sleep_hours = (sleep.get("sleep_s") or 0) / 3600
    if sleep_hours >= 3:
        measurements.extend((
            ("Overnight Pulse Ox", sleep.get("avg_spo2"), "%", 1),
            ("Overnight breathing rate", sleep.get("avg_respiration"), " breaths/min", 1),
        ))
    meanings = {"Steps": (f'Usual: {row["steps_typical"]:,} steps on recorded prior days'
                          if "steps_typical" in row else "Recorded steps so far for this date"),
                "Garmin resting estimate": "See the resting pulse check above.",
                "Overnight HRV": "Beat-to-beat variation during sleep.",
                "Daytime stress": "Garmin’s estimate from heart-rate variability.",
                "Body Battery low": "Lowest recorded Garmin energy estimate.",
                "Body Battery high": "Highest recorded Garmin energy estimate.",
                "Garmin daily Pulse Ox": "Wrist estimate of oxygen saturation.",
                "Overnight Pulse Ox": "Wrist estimate during the recorded night.",
                "Overnight breathing rate": "Average breathing rate during the recorded night."}
    readings = "".join(_row(name, _f(value, precision, unit), meanings.get(name, ""))
                       for name, value, unit, precision in measurements if value is not None)
    stages = []
    if sleep_hours >= 3:
        for key, name in (("deep_s", "Deep"), ("light_s", "Light"), ("rem_s", "REM"), ("awake_s", "Awake")):
            if sleep.get(key) is not None:
                stages.append(_row(name, _e(loads._hms(sleep[key]))))
    run_ids = {r["activity_id"] for r in d["runs"]}
    workouts = []
    for a in row.get("activities", []):
        note = " · ".join(v for v in (a["start"][11:16], a["duration"],
                        _f(a["distance_km"], 2, " km") if a["distance_km"] is not None else None,
                        _f(a["avg_hr"], unit=" bpm avg") if a["avg_hr"] is not None else None) if v)
        name = a["name"] or (a["type"] or "Workout").replace("_", " ").capitalize()
        workouts.append(_record_link(name, note, _workout_link(d, a["id"], run_ids)))
    body = _history_nav(d, "Day", day=day, month=day[:7])
    days = d["calendar"]["detail_days"]
    index = days.index(day)
    neighbours = ""
    if index:
        neighbours += (f'<a class="flow-link" href="#day-{days[index - 1]}">'
                       f'{icon("back")}<span>Earlier · {_e(_short(days[index - 1]))}</span></a>')
    if index + 1 < len(days):
        neighbours += (f'<a class="flow-link" href="#day-{days[index + 1]}">'
                       f'<span>Later · {_e(_short(days[index + 1]))}</span>{icon("chev")}</a>')
    if neighbours:
        body += f'<nav class="day-neighbours wide" aria-label="Adjacent recorded days">{neighbours}</nav>'
    if highlights := row.get("highlights"):
        context = "".join(_row(h["label"], f'{_f(h["value"], int(h["unit"] == " h"), h["unit"])} '
                               f'· {h["direction"]} than usual',
                               f'Usual median {_f(h["median"], int(h["unit"] == " h"), h["unit"])} '
                               f'across {h["count"]} readings in the prior 28 days.')
                          for h in highlights)
        body += _card("What stands out this day", f'<ul class="rows">{context}</ul>',
                      "Compared with your recent recorded days.", wide=True)
    body += _resting_pulse_card(row.get("resting_pulse_check"))
    watch_zone = d.get("day_zones", {}).get(day, d.get("zone", UTC))
    body += _intraday_pulse_card(row.get("intraday_hr"), row.get("activities", []), day=day, zone=watch_zone)
    if wellness := row.get("intraday_wellness"):
        body += _intraday_wellness_card(wellness, day, watch_zone)
    if readings:
        body += _card("Readings", f'<details><summary>All recorded values</summary>'
                      f'<ul class="rows">{readings}</ul></details>', wide=True)
    night = d.get("sleep_review", {}).get("nights", {}).get(day)
    if night:
        body += f'<section class="sleep-band wide"><h3>Sleep</h3>{_night_record(night)}</section>'
    elif stages:
        body += _card("Recorded sleep stages", f'<ul class="rows">{"".join(stages)}</ul>')
    if workouts:
        body += _card("Workouts", f'<ul class="record-list">{"".join(workouts)}</ul>', wide=True)
    if not any((readings, workouts, night, stages, row.get("intraday_hr"), wellness)):
        body += _card("Readings", '<p class="empty">No usable readings for this date.</p>')
    return _page(f"day-{day}", _date_label(day), "Garmin records for this date",
                 body, back=f"#month-{day[:7]}")


def page_months(d: dict[str, Any]) -> str:
    c = d["calendar"]
    history = c["months"]
    hours = [(date.fromisoformat(m["month"] + "-01").strftime("%b %y"),
              m["values"]["avg_sleep_h"]) for m in history]
    chart = both(bar_chart, hours, " h", nd=1, x_label="Month", y_label="Average sleep (h)")
    rows = []
    for month in reversed(history):
        cov = month["coverage"]
        label = _month_label(month["month"])
        info = (f'{cov["sleep_nights"]}/{cov["calendar_days"]} sleep nights · '
                f'{month["values"]["sessions"]} workouts')
        run_km = month["values"]["run_km"]
        if run_km is not None:
            info += f" · {run_km:.1f} km running"
        href = f'#month-{month["month"]}' if month["month"] in c["by_month"] else None
        rows.append(_record_link(label, info if href else "No recorded days", href))
    body = (_history_nav(d, "Year")
            + _card("Sleep by month", chart, wide=True)
            + _card("Open a month", f'<ul class="record-list">{"".join(rows)}</ul>', wide=True))
    return _page("month-detail", "Year history", "Last 12 completed calendar months.", body, back="#history")


def vo2_reference(r: dict[str, Any]) -> str:
    facts = (_row("Garmin VO₂max", _f(r.get("garmin"), 1),
                  f'Recorded {_e(r.get("garmin_as_of") or "date unavailable")}')
             + _row("Effective VO₂max", _f(r.get("effective"), 1),
                    f'{r.get("effective_runs", 0)} qualifying runs over 180 days'))
    caveat = r.get("caveat", "")
    if not r.get("hr_max_user_override"):
        caveat += " Effective estimate depends on your untested max HR."
    else:
        caveat += f' Effective estimate uses your max-HR setting ({_f(r.get("hr_max"))} bpm).'
    if not r.get("available"):
        return (f'<ul class="rows">{facts}</ul><p class="empty">{_e(r.get("reason"))}</p>'
                f'<p class="sub">{_e(caveat)}</p>')
    svg = both(_vo2_plot, r)
    return (f'{svg}<p class="sub">Grey dot: Garmin · blue outline: effective estimate. '
            f'Line: 5th–95th · solid band: 25th–75th.</p>'
            f'<ul class="rows">{facts}</ul><p class="sub">{_e(caveat)}</p>'
            f'<p class="chart-note">{_e(r["sex"].title())}, age {_e(r["age_group"])} · '
            f'<a class="source-link" href="{norms.SOURCE}" rel="noreferrer">FRIEND 2015, Table 3</a></p>')


def _vo2_plot(r: dict[str, Any], w: int) -> str:
    v = r["values"]
    markers = [(name, value, cls) for name, value, cls in (
        ("Garmin", r.get("garmin"), "vo2-garmin"),
        ("Effective", r.get("effective"), "vo2-effective")) if isinstance(value, (int, float))]
    lo, hi = _scale(list(v.values()) + [x[1] for x in markers], 0.05)
    left, right = 20, w - 20

    def x(value):
        return left + (right - left) * (value - lo) / (hi - lo)

    parts = [
        (f'<line x1="{x(v[5]):.1f}" x2="{x(v[95]):.1f}" y1="34" y2="34" class="vo2-range"/>'),
        (f'<line x1="{x(v[25]):.1f}" x2="{x(v[75]):.1f}" y1="34" y2="34" class="vo2-middle"/>'),
    ]
    for percentile, value in v.items():
        parts.append(_point(x(value), 34, f"{percentile}th reference percentile",
                            f"{value:.1f} mL/kg/min"))
    parts.extend(_point(x(value), 20 if cls == "vo2-garmin" else 48,
                        f"{name} VO₂max", f"{value:.1f} mL/kg/min", cls)
                 for name, value, cls in markers)
    parts.extend(f'<text x="{x(v[p]):.1f}" y="72" class="tick" text-anchor="middle">'
                 f'{p}th · {v[p]:.1f}</text>' for p in (5, 50, 95))
    return _chart("scatter", parts, w, 84, (left, right, 10, 55),
                  "VO₂max (mL/kg/min)", "Population reference",
                  compact=True)


def page_patterns(d: dict[str, Any]) -> str:
    lab = _PATTERN_LABELS
    explore = d["explore"]
    cards = ""
    for p in explore["pairs"]:
        if not p["notable"]:
            continue
        x, y = lab.get(p["x"], p["x"]), lab.get(p["y"], p["y"])
        when = "same day" if p["lag_days"] == 0 else "next day"
        ux = "points" if p["x"] == "trimp" else engine.UNITS[p["x"]]
        uy = "points" if p["y"] == "trimp" else engine.UNITS[p["y"]]
        drawn = sorted(p["points"])[-SCATTER_POINTS:]
        paired = p["points"]
        center = (sum(row[1] for row in paired) / len(paired),
                  sum(row[2] for row in paired) / len(paired)) if paired else None
        plot = both(scatter, drawn, x, y, p.get("slope"),
                    x_unit=ux, y_unit=uy, lag=p["lag_days"], fit_center=center)
        statement = p["statement"].partition(" (r =")[0]
        statement = statement.replace("TRIMP more training load", "more training load points")
        statement = statement.replace("TRIMP", "training load points")
        body = (f'<p>{_e(statement)}.</p>'
                f'<p class="chart-note">{p["n"]} paired days'
                + (f' (latest {len(drawn)} drawn)' if len(drawn) < len(p["points"]) else "")
                + ' · Each dot is a pair of readings. Zero is your recent average. The dashed line shows their overall relationship.</p>'
                f'<details><summary>See the paired readings and uncertainty</summary>{plot}<p class="sub">'
                f'Correlation {p["r"]:+.2f} · 95% range '
                f'{p["r_ci95"][0]:+.2f} to {p["r_ci95"][1]:+.2f}.'
                ' This relationship alone cannot establish a cause.</p></details>')
        cards += _card(f"{x} & {y} ({when})", body, wide=True)
    shown = sum(p["notable"] for p in explore["pairs"])
    checked = explore["eligible"] - explore["notable"]
    if checked:
        cards += _card("Other comparisons",
                       f'<p class="sub">{checked} had enough data but showed no clear pattern.</p>',
                       wide=True)
    count = "No clear patterns yet" if not shown else f"{shown} patterns shown"
    return _page("patterns", "Patterns", count, cards or _card(
        "Patterns", '<p class="empty">Not enough data yet.</p>'), back="#trends")



# =============================================================================== render
CSS = """
:root{color-scheme:light;--page:#f2f5f8;--surface:#fff;--ink:#172033;--ink2:#48556a;
--muted:#546174;--grid:#dfe4ec;--axis:#687487;--border:#dce3eb;--s1:#1868c4;
--accent:#edf5ff;--active:#104f9d;--cursor:#39669a;
--split-guide:#7e8fab;--overlay-ink:#48556a;--band-green:#087340;--band-amber:#986000;--band-red:#b92f3b;
--focus:#e7f1fb;--focus-edge:#c6dbf1;
--s2:#eb6834;--good:#0ca30c;--warn:#fab219;--serious:#ec835a;--bad:#d03b3b;--purple:#6250d6;
--band:rgba(42,120,214,.12);--goodtext:#006300}
:root[data-theme=dark]{color-scheme:dark;--page:#10151f;--surface:#1a2230;--ink:#f3f6fa;
--ink2:#c4cede;--muted:#aab8cd;--grid:#354155;--axis:#899bb4;--border:#303c50;--s1:#6baaff;
--accent:#202f48;--active:#b6d9ff;--cursor:#b6d9ff;
--split-guide:#8197b7;--overlay-ink:#c4cede;--band-green:#67d69a;--band-amber:#ffc36b;--band-red:#ff8894;
--focus:#1c324b;--focus-edge:#355275;
--s2:#d95926;--purple:#9085e9;--band:rgba(57,135,229,.18);--goodtext:#0ca30c}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,
"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
a:focus-visible,summary:focus-visible,button:focus-visible,input:focus-visible,.chart:focus-visible,.table-wrap:focus-visible{
outline:3px solid var(--s1);outline-offset:3px}
.chart:focus:not(:focus-visible){outline:none}
.wrap{max-width:1160px;margin:0 auto;padding:16px 24px 48px}
.mast{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px}
.mast b{font-size:17px;letter-spacing:-.025em;display:flex;gap:9px;align-items:center}
.mast b .ic{width:24px;height:24px;padding:4px;border-radius:7px;background:var(--s1);color:var(--page)}
.theme{display:none;border:1px solid var(--border);border-radius:12px;background:var(--surface)}
[data-interactive] .theme{display:flex}
.theme button{min-height:42px;border:0;background:transparent;color:var(--ink2);font:600 13px system-ui;
padding:0 13px;border-radius:11px;cursor:pointer}
.theme button[aria-pressed=true]{background:var(--accent);color:var(--active)}
.top{display:flex;gap:4px;padding:5px;margin:0 0 22px;background:var(--surface);
border:1px solid var(--border);border-radius:14px}
.top a{flex:none;display:inline-flex;align-items:center;gap:7px;min-height:44px;padding:8px 15px;
border-radius:9px;font-size:13px;font-weight:650;color:var(--ink2)}
.top a:hover,.top a[aria-current=page]{background:var(--accent);color:var(--active)}
@media(min-width:641px){
.top{position:sticky;top:8px;z-index:5}
.page[id],.run-section[id],.running-anchor[id]{scroll-margin-top:76px}
}
@media(max-width:640px){
.wrap{padding:12px 14px calc(96px + env(safe-area-inset-bottom))}
.page[id]{scroll-margin-top:60px}
.top{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:2px;position:fixed;z-index:5;
inset:auto 0 0;margin:0;padding:4px max(8px,env(safe-area-inset-right)) calc(4px + env(safe-area-inset-bottom))
max(8px,env(safe-area-inset-left));border-width:1px 0 0;border-radius:0}
.top a{justify-content:center;flex-direction:column;gap:4px;min-height:51px;padding:4px 1px;font-size:11px}
.top .ic{width:18px;height:18px}
}
.sr-only{width:1px;height:1px;position:absolute;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
.page{display:none}#today{display:block}
body:has(.page:target,.run-section:target,.running-anchor:target) #today:not(:target){display:none}
.page:target,.page:has(.run-section:target,.running-anchor:target){display:block}
.card.run-section{padding:0;border:0;background:transparent}
.run-section>summary{color:var(--ink);font-weight:650;min-height:44px;box-sizing:border-box;
padding:12px 16px;background:var(--surface);border:1px solid var(--border);border-radius:14px}
.run-section .grid{margin-top:10px}
.secondary-metrics{margin:0}
.secondary-metrics>summary{font-size:15px;font-weight:650}
.secondary-metrics>.grid{margin-top:6px}
.secondary-metrics .card{background:var(--page)}
.run-jumps{display:flex;gap:0 16px;flex-wrap:wrap}
.ph{margin:0 0 18px}.ph h2{font-size:clamp(28px,4vw,38px);line-height:1.1;letter-spacing:-.045em;margin:0 0 5px}
.lede{margin:0;color:var(--ink2);font-size:17px;line-height:1.4}
.back{display:inline-flex;align-items:center;gap:4px;min-height:44px;color:var(--active);font-weight:600;
font-size:14px;margin:0 0 5px}
.grid{display:grid;grid-template-columns:1fr;gap:16px}
@media (min-width:768px){.grid{grid-template-columns:1fr 1fr}.wide{grid-column:1/-1}}
@media (min-width:768px){#today>.grid{grid-template-columns:minmax(0,5fr) minmax(0,3fr)}}
.card{background:var(--surface);border:1px solid var(--border);border-radius:16px;
padding:20px;min-width:0}
@media (max-width:480px){.card{padding:16px}}
.card h3{font-size:16px;letter-spacing:-.01em;color:var(--ink);
margin:0 0 5px;font-weight:680;line-height:1.28}
.card-link{display:flex;flex-wrap:wrap;align-items:baseline;column-gap:8px}
.card-link .chev{margin-left:auto}
.card-link:hover h3{text-decoration:underline}
.sub{color:var(--ink2);font-size:13px;line-height:1.45;margin:0 0 12px}
.say{font-size:22px;line-height:1.25;font-weight:600;letter-spacing:-.01em;margin:8px 0 4px}
.big{font-size:48px;line-height:1.05;font-weight:700;letter-spacing:-.02em;margin:8px 0 4px}
.big small{font-size:.45em;font-weight:500;color:var(--ink2);margin-left:2px}
.empty{color:var(--muted);font-size:13px;margin:12px 0}
.card.today-focus{background:linear-gradient(115deg,var(--focus),var(--surface));
border-color:var(--focus-edge);padding:clamp(16px,2.5vw,28px)}
.today-focus h3{font-size:clamp(22px,4vw,31px);line-height:1.2;max-width:29ch}
.today-focus p{margin:8px 0 0;color:var(--ink2);max-width:65ch}
.today-focus .focus-label,.insight-label{color:var(--active);font-size:12px;font-weight:700}
.today-focus .focus-label{margin:0 0 7px}
.local-insight{margin:12px 0;padding:10px 12px;border-radius:10px;background:var(--accent)}
.local-insight p{margin:0 0 4px}
.finding .insight-label{display:block;margin-bottom:3px}
.flow-link{display:inline-flex;align-items:center;gap:7px;min-height:44px;color:var(--active);
font-size:14px;font-weight:650}
.history-entry{justify-self:start}
.overview h3{font-size:16px;margin:0 0 7px}
.overview-tiles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.overview-tile{display:flex;flex-direction:column;gap:4px;border:1px solid var(--border);
border-radius:14px;padding:clamp(9px,1.65vw,17px);background:var(--surface);min-width:0}
.overview-tile:hover{background:var(--accent)}
.overview-tile>span{display:flex;align-items:center;gap:5px;color:var(--ink2);font-size:12px}
.overview-tile .ic{width:13px;height:13px;color:var(--active)}
.overview-tile .chev{margin-left:auto}
.overview-tile strong{font-size:clamp(17px,3.1vw,29px);line-height:1.2;font-variant-numeric:tabular-nums}
.overview-tile small{font-size:11px;color:var(--ink2);line-height:1.25}
.week-cue{font-size:16px;margin:7px 0 0;color:var(--ink)}
.run-first{font-size:17px;margin:8px 0 12px;max-width:64ch}
@media(max-width:360px){
#today .grid{gap:10px}
#today .ph{margin-bottom:12px}
#today .today-focus{padding:13px}
#today .today-focus h3{font-size:21px}
#today .today-focus p{font-size:13px}
#today .flow-link{min-height:44px}
#today .overview-tile{padding:8px 7px}
#today .overview-tile .chev{display:none}
#today .card:not(.today-focus){padding:12px}
#today .week-cue{font-size:14px}
}
.recovery-history .sm figure{max-width:310px}
.recovery-history .lg figure{max-width:635px}
.ic{width:16px;height:16px;flex:none;fill:none;stroke:currentColor;stroke-width:1.75;
stroke-linecap:round;stroke-linejoin:round}
.ic.good{color:var(--goodtext)}.ic.warn{color:var(--serious)}.ic.chev{color:var(--muted)}
.rows{list-style:none;margin:8px 0 0;padding:0}
.rows li{display:grid;grid-template-columns:1fr auto;column-gap:12px;row-gap:2px;
padding:12px 0;border-top:1px solid var(--grid)}
.rows li:first-child{border-top:0}
.v small{font-size:12px;font-weight:500;color:var(--ink2);margin-left:3px}
.rows .k{font-size:15px}.rows .v{font-size:17px;font-weight:600;text-align:right;
font-variant-numeric:tabular-nums}
.rows .n{grid-column:1/-1;display:flex;align-items:center;gap:8px;font-size:13px;
color:var(--ink2)}
.rows .n:empty{display:none}
.tiles{display:grid;gap:0}
.tile{display:grid;grid-template-columns:1fr auto;align-items:center;padding:14px 0;
border-top:1px solid var(--grid)}
.tiles h3+.tile{border-top:0}.tile b{font-weight:600}
.tile:hover b{text-decoration:underline}
.tile span{grid-column:1;font-size:13px;color:var(--ink2)}
.tile .ic{grid-row:1/3;grid-column:2;color:var(--muted)}
.chart,.gauge{display:block;width:100%;height:auto;overflow:visible}
.chart-interaction{margin:10px 0 0;max-width:720px}
.sm .chart-interaction{max-width:420px}
.sm .chart-compact{max-width:390px}
[data-ready] .chart{touch-action:pan-y pinch-zoom;cursor:crosshair;user-select:none}
.chart-readout{display:none;color:var(--ink2);border-radius:10px;padding:6px 10px;min-height:52px;
font-size:13px;line-height:1.35}
[data-ready] .chart-readout.selected{display:flex;flex-direction:column;justify-content:center}
.chart-readout.selected{background:var(--accent);color:var(--ink)}
.chart-readout.selected{border-inline-start:3px solid var(--active)}
.chart-readout strong{color:var(--active);font-size:13px;font-weight:650}
.chart-readout span{overflow-wrap:anywhere;font-variant-numeric:tabular-nums}
.chart-compact .chart-readout{min-height:48px}
.chart-interaction[data-conditions] .chart-readout{min-height:75px}
.chart-cursor{visibility:hidden;pointer-events:none}
.chart-cursor.visible{visibility:visible}
.chart-cursor line{stroke:var(--cursor);stroke-width:.9;stroke-dasharray:3 3;vector-effect:non-scaling-stroke}
.chart-cursor circle{fill:var(--surface);stroke:var(--active);stroke-width:1.6}
.chart-note{font-size:12px;color:var(--muted);margin:3px 0 0}
.chart-readings ul{padding-inline-start:1.3em}
.chart-readings li{font-size:.875em;line-height:1.5;padding-block:3px;overflow-wrap:anywhere}
.source-link{text-decoration:underline;color:var(--active)}
.grid line.grid,.chart .grid{stroke:var(--grid);stroke-width:1}
.chart .axis,.chart .zero{stroke:var(--axis);stroke-width:1;fill:none}
.split-faster{fill:var(--s1)}.split-slower{fill:var(--purple)}.split-even{fill:var(--axis)}
.split-value{fill:var(--ink);font-weight:640}
.chart .ref{stroke:var(--ink2);stroke-width:1;stroke-dasharray:3 3}
.split-toggle{display:flex;align-items:center;gap:8px;min-height:44px;color:var(--active);
font-size:14px;font-weight:650;width:max-content}
.split-toggle input{width:18px;height:18px;accent-color:var(--active)}
.split-guides{display:none;pointer-events:none}
.run-section:has(.split-toggle input:checked) .split-guides{display:initial}
.split-guides line{stroke:var(--split-guide);stroke-width:1;stroke-dasharray:2 3;vector-effect:non-scaling-stroke}
.split-guides text{font-size:11px;fill:var(--ink2)}
.tick{font-size:11px;fill:var(--ink2);font-variant-numeric:tabular-nums}
.axis-label{font-size:12px;fill:var(--ink);font-weight:640}
.ln{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.ln.context{stroke-width:1.45}
.observed-span{stroke:var(--axis);stroke-width:1.15}
.timeline-guide{stroke:var(--axis);stroke-dasharray:3 3;stroke-width:1}
.day-tick{font-size:9.5px}
.ln.s1{stroke:var(--s1)}.ln.s2{stroke:var(--s2)}
.dot.s1{fill:var(--s1);stroke:var(--surface);stroke-width:2}
.context-dot{fill:var(--s1);r:1.7}
.zone-dot{stroke:var(--surface);stroke-width:.7;r:3px}
.zone-red{--zone-ink:var(--band-red)}.zone-orange{--zone-ink:var(--band-amber)}
.zone-green{--zone-ink:var(--band-green)}.zone-blue{--zone-ink:var(--s1)}
.zone-purple{--zone-ink:var(--purple)}
.zone-dot{fill:var(--zone-ink)}.ln.zone-line{stroke:var(--zone-ink)}
.hit{fill:transparent}.pt{fill:var(--s1);fill-opacity:.85;r:1.6px}
.chart-dense :is(.pt,.zone-dot,.context-dot){r:.95px;stroke:none}
.chart-interaction .pt.pt-sparse{r:4px;stroke:var(--surface);stroke-width:.8}
.fit{stroke:var(--overlay-ink);stroke-dasharray:4 2;stroke-width:2;stroke-linecap:round}.band{fill:var(--band)}
.moving-average{fill:none;stroke:var(--overlay-ink);stroke-width:1.8;stroke-dasharray:5 3}
.overlay-secondary{display:none}
.overlay-secondary.active{display:initial}
.overlay-axis{stroke:var(--overlay-ink);stroke-width:1}
.overlay-label{fill:var(--overlay-ink)}
.overlay-secondary .ln.s2{stroke:var(--overlay-ink)}
.overlay-dot{fill:var(--overlay-ink)}
.ln.overlay-line{stroke-dasharray:4 2}
.chart-key{margin:4px 0;color:var(--ink2);font-size:12px}
.chart-key.overlay-secondary.active{display:block}
.trace-bands{display:flex;flex-wrap:wrap;gap:3px 10px}
.trace-bands span::before{content:"";display:inline-block;width:.75em;border-top:3px solid var(--zone-ink);
margin-inline-end:4px;vertical-align:middle}
.overlay-options{display:none;align-items:center;flex-wrap:wrap;gap:6px;margin:0 0 6px}
[data-ready] .overlay-options{display:flex}
.overlay-options span{color:var(--ink2);font-size:13px;margin-right:4px}
.overlay-control{display:none;align-items:center;min-height:44px;border:1px solid var(--border);
border-radius:10px;background:var(--surface);color:var(--ink);font:600 13px system-ui;
padding:0 10px;cursor:pointer}
[data-ready] .overlay-control{display:inline-flex}
.overlay-control[aria-pressed=true]{background:var(--accent);color:var(--active)}
.vo2-range{stroke:var(--axis);stroke-width:4}.vo2-middle{stroke:var(--s1);stroke-width:8}
.vo2-garmin{fill:var(--muted);stroke:var(--surface);stroke-width:2}
.vo2-effective{fill:var(--surface);stroke:var(--s1);stroke-width:2}
.bar.s1{fill:var(--s1)}.bar.good{fill:var(--band-green)}.bar.warn{fill:var(--band-amber)}
.bar.bad{fill:var(--bad)}.bar.muted{fill:var(--muted)}
.gauge{position:relative;height:20px;margin:8px 0 6px}
.gbar{display:flex;gap:2px;height:8px;position:absolute;left:0;right:0;top:6px}
.gbar i{border-radius:4px}
.g-purple{background:var(--purple)}.g-blue{background:var(--s1)}.g-green{background:var(--good)}
.g-orange{background:var(--serious)}.g-red{background:var(--bad)}
.gauge b{position:absolute;top:2px;width:16px;height:16px;margin-left:-8px;border-radius:50%;
box-sizing:border-box}
.gauge .mk{background:var(--ink);border:2px solid var(--surface)}
.gauge .mk2{background:var(--surface);border:2px solid var(--ink)}
.chart-layout>.lg{display:none}
@supports (container-type:inline-size){
.chart-layout{container-type:inline-size}
.wellness-panels{display:grid;gap:12px}
.wellness-panels>div{min-width:0}
.wellness-panels h4{margin:10px 0 6px}
@media(min-width:800px){.wellness-panels{grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}}
@container (min-width:600px){
.chart-layout>.sm{display:none}.chart-layout>.lg{display:block}
}}
@supports not (container-type:inline-size){
@media (min-width:768px){.wide .chart-layout>.sm{display:none}.wide .chart-layout>.lg{display:block}}
}
.form-row{padding:12px 0;border-top:1px solid var(--grid)}.form-row:first-of-type{border-top:0}
.fr-head{display:flex;justify-content:space-between;font-size:15px}
.fr-head b{font-variant-numeric:tabular-nums}
.metric-meaning{margin:5px 0;max-width:72ch}
.form-reference dt{font-weight:650;margin-top:8px}
.form-reference dd{margin:2px 0 8px;color:var(--ink2);max-width:72ch}
.chart-definition{display:block;margin-top:3px;color:var(--ink2)}
.form-row .sub{margin:0}
.legend{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--muted);margin:8px 0 0}
.legend i{display:inline-block;width:10px;height:10px;border-radius:50%}
.legend i.mk{background:var(--ink)}.legend i.mk2{border:2px solid var(--ink)}
.work{margin:8px 0 0;padding-left:20px}.work li{margin:0 0 12px;line-height:1.5}
.track{height:8px;border-radius:999px;background:var(--grid);margin:12px 0 4px;overflow:hidden}
.track i{display:block;height:100%;background:var(--s1);border-radius:999px}
.track-marks{position:relative;height:18px;font-size:11px;color:var(--muted);margin-bottom:8px}
.track-marks span{position:absolute;transform:translateX(-50%);white-space:nowrap}
.track-marks span:last-child{transform:translateX(-100%)}
table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}
.race-estimates{list-style:none;margin:0;padding:0}
.race-estimates li{padding:10px 0;border-top:1px solid var(--grid)}
.race-estimates li div{display:flex;flex-wrap:wrap;gap:8px 18px;margin-top:5px}
.race-estimates small{display:block;color:var(--muted)}
.race-estimates b{font-variant-numeric:tabular-nums}
.month-bars td:nth-child(2){width:43%;font-weight:600}
.month-bar{display:block;height:4px;margin:4px 0;background:var(--grid);border-radius:4px}
.month-bar i{display:block;height:100%;background:var(--s1);border-radius:4px}
th{font-weight:600;color:var(--muted);text-align:right;padding:6px 4px;font-size:12px}
td{padding:8px 4px;text-align:right;border-top:1px solid var(--grid)}
td:first-child,th:first-child{text-align:left}.g{color:var(--muted)}
.pats{list-style:none;padding:0;margin:0}.pat{padding:16px 0;border-top:1px solid var(--grid)}
.pat:first-child{border-top:0}
details{margin-top:8px}summary{font-size:13px;color:var(--ink);cursor:pointer;min-height:44px;padding:10px 0}
caption{text-align:left;font-size:12px;color:var(--ink2);padding:8px 0}
.table-wrap{max-width:100%;overflow-x:auto}th,td{overflow-wrap:anywhere}
.findings{list-style:none;margin:0;padding:0}
.findings li+li{border-top:1px solid var(--grid)}
.finding{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:44px;padding:10px 0}
.finding-detail,.finding-action{display:block;color:var(--ink2);font-size:13px;margin-top:3px}
.finding-action{color:var(--ink)}.findings details{margin:0 10px}.findings details p{max-width:62ch}
.finding:hover strong{text-decoration:underline}
.history-tabs{display:flex;gap:5px;flex-wrap:wrap}
.history-tabs a{display:inline-flex;align-items:center;min-height:44px;padding:0 14px;
border-radius:10px;border:1px solid var(--border);background:var(--surface);font-weight:600}
.history-tabs a[aria-current=page]{background:var(--accent);color:var(--active)}
.history-tabs a:hover{border-color:var(--s1)}
.day-neighbours{display:flex;justify-content:space-between;flex-wrap:wrap;gap:4px 16px}
.record-list{list-style:none;padding:0;margin:0}
.record-list li+li{border-top:1px solid var(--grid)}
.record-link{display:flex;justify-content:space-between;gap:12px;align-items:center;min-height:44px;padding:10px 0}
.record-link>span{min-width:0;overflow-wrap:anywhere}
.record-link small{display:block;color:var(--ink2);font-size:13px}
a.record-link:hover strong{text-decoration:underline}
.signal-status{margin:8px 0 3px;color:var(--active)}
.sleep-hero,.coach-change{padding:20px;border-radius:16px;background:var(--focus)}
.sleep-hero h3,.coach-change h3,.sleep-band h3{margin:0;font-size:16px}
.daily-interpretation{border-inline-start:3px solid var(--active);padding:6px 0 6px clamp(12px,2.5vw,24px)}
.daily-interpretation h3{margin:0;font-size:16px}
.daily-interpretation .insight-label{margin:4px 0 0}
.daily-interpretation .say{max-width:55ch;font-size:clamp(20px,3vw,26px)}
.daily-interpretation p{max-width:64ch}
.running-lead{display:grid;min-width:0;gap:14px;background:linear-gradient(120deg,var(--focus),var(--surface));
border:1px solid var(--focus-edge);border-radius:20px;padding:clamp(16px,3vw,30px)}
.running-next h3{font-size:clamp(24px,4vw,36px);letter-spacing:-.04em;line-height:1.08;margin:6px 0;max-width:22ch}
.running-next p{margin:5px 0;max-width:55ch}.running-next .insight-label{display:flex;align-items:center;gap:6px}
.running-next .flow-link{font-size:13px}
.running-block-summary{align-self:end;border-top:1px solid var(--border);padding-top:12px}
.running-block-summary h3{font-size:14px;margin:0}
.running-measures{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:12px 0 0}
.running-measures dt,.running-measures small{font-size:12px;color:var(--ink2);line-height:1.3}
.running-measures dd{margin:3px 0;font-size:clamp(19px,3vw,30px);font-weight:720;
letter-spacing:-.04em;font-variant-numeric:tabular-nums}
.split-measures{grid-template-columns:repeat(2,minmax(0,1fr))}
.running-effort-list{list-style:none;padding:0;margin:8px 0}
.running-effort-list li{display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px 12px;
padding:9px 0;border-top:1px solid var(--border)}.running-effort-list p{margin:0}
@media(min-width:800px){.running-lead{grid-template-columns:5fr 4fr;gap:24px}
.running-block-summary{border-top:0;border-inline-start:1px solid var(--border);padding:8px 0 8px 20px}}
.sleep-band,.sleep-brief{border-top:1px solid var(--border);padding:12px 0;margin:0;min-width:0}
.sleep-brief{display:flex;align-items:center;justify-content:space-between;gap:8px;color:var(--active)}
.sleep-band summary{font-size:16px}
.sleep-band summary span{display:block;color:var(--ink2);font-size:13px;margin-top:4px}
.sleep-measures{display:grid;grid-template-columns:repeat(auto-fit,minmax(108px,1fr));gap:12px;margin:12px 0}
.sleep-measures dt{color:var(--ink2);font-size:13px}
.sleep-measures dd{margin:0;font-size:clamp(19px,4vw,31px);font-weight:700;font-variant-numeric:tabular-nums}
.stage-strip{display:flex;height:10px;overflow:hidden;border-radius:10px}
.stage-key{display:flex;flex-wrap:wrap;gap:5px 16px;padding:0;list-style:none;font-size:13px}
.stage-key li::before{content:"";display:inline-block;width:8px;height:8px;border-radius:50%;
background:var(--stage);margin-right:5px}
.stage-strip span,.sleep-timeline span{background:var(--stage)}
.sleep-timeline{position:relative;min-height:68px;background:var(--surface);border-radius:8px;overflow:hidden}
.sleep-timeline span{position:absolute;height:15px;top:var(--lane)}
.sleep-timeline .awake{--lane:2px}.sleep-timeline .rem{--lane:18px}
.sleep-timeline .light{--lane:34px}.sleep-timeline .deep{--lane:50px}
.deep{--stage:var(--purple)}.light{--stage:var(--s1)}.rem{--stage:var(--good)}.awake{--stage:var(--s2)}
@media(min-width:900px){
body{font-size:16px}
.wrap{max-width:1300px}
.top a,.theme button{font-size:14px}
.card h3,.sleep-hero h3,.sleep-band h3{font-size:18px}
.sub,.rows .n,.record-link small,.empty,summary{font-size:15px}
.chart-note,.chart-key,.chart-readout,.chart-readout strong{font-size:14px}
.lg .chart-interaction{max-width:940px}
.lg .tick{font-size:12px}
.lg .axis-label{font-size:13px}
.lg .day-tick{font-size:10px}
}
footer{margin-top:48px;font-size:12px;color:var(--muted);line-height:1.6}
@media print{.top,.mast,.back,.chart-readout,.overlay-options{display:none!important}
.page{display:block!important;break-after:page}}
"""


def page_trends() -> str:
    links = (("Recovery", "Heart rate, HRV and overnight readings", "#recovery"),
             ("Body", "Fitness, VO₂max and longer-term changes", "#body"),
             ("Patterns", "How measurements move together", "#patterns"),
             ("History", "Find past workouts and daily readings", "#history"))
    body = "".join(_card(title, "", note, href=target) for title, note, target in links)
    return _page("trends", "Trends", "Explore your records over time.", body)


def render(d: dict[str, Any]) -> str:
    built_at = datetime.now(UTC)
    snapshot = f"{SNAPSHOT_PREFIX}{built_at.isoformat()}"
    links = (("today", "Today"), ("sleep", "Sleep"), ("training", "Training"),
             ("running", "Running"), ("trends", "Trends"))
    if d.get("available") is False:
        secondary = (("recovery", "Recovery"), ("body", "Body"), ("patterns", "Patterns"),
                     ("history", "History"))
        pages = [_page(pid, title, "", _card("No data yet", f'<p>{_e(d["reason"])}</p>'))
                 for pid, title in (*links[:-1], *secondary)]
        pages.append(page_trends())
        freshness = "No Garmin measurements are available yet."
    else:
        pages = [page_today(d), page_sleep(d), page_recovery(d), page_training(d), page_trends(),
                 page_running(d), page_body(d), page_months(d), page_patterns(d), page_history_week(d)]
        run_ids = {r["activity_id"] for r in d["runs"]}
        post_run = deep_insight.post_run_fallback(d)
        for index, r in enumerate(d["runs"]):
            narration = d.get("narration", {})
            summary = narration.get(f'run-{r["activity_id"]}')
            check = d.get("narration", {}).get(f'run-check-{r["activity_id"]}', {})
            pages.append(page_run(r, d.get("trial"), summary, run_ids=run_ids,
                                  run_check=check.get("choice"),
                                  post_run=(narration.get(f'post-run-insight-{r["activity_id"]}') or post_run)
                                  if index == 0 else None))
        pages.extend(_workout_page(workout, d.get("narration", {}).get(f'workout-{workout["id"]}'))
                     for workout in d.get("workouts", []))
        calendar = d["calendar"]
        pages.extend(page_history_month(d, month) for month in
                     sorted({calendar["current_month"], *calendar["by_month"]}))
        pages.extend(page_history_day(d, day) for day in calendar["detail_days"])
        freshness = f'Data through {_e(d["end"])} from your own Garmin records.'
    sync = d.get("last_full_sync") or "none recorded"
    build_time = built_at.astimezone(d.get("zone", UTC)).strftime("%-d %b %Y, %H:%M %Z")
    status = f'Last complete sync {_e(sync)} · Dashboard built {build_time} · Code v{__version__}.'
    symbols = ("home", "moon", "bolt", "run", "trend")
    ai_state = ""
    if ai := d.get("narrator_status"):
        labels = {
            "disabled": "disabled",
            "sync_incomplete": "waiting for a complete Garmin sync",
            "pending": "waiting for review",
            "cloud_blocked": "waiting for confirmation that Ollama cloud is off",
            "unavailable": "Ollama or the selected model was unavailable",
            "unsupported": "the selected model lacks a required capability",
            "incomplete": "a review could not finish",
            "withheld": "no output passed review",
            "no_evidence": "no eligible readings",
        }
        parts = []
        if ai["count"]:
            parts.append(f'{ai["count"]} checked results')
        if reason := labels.get(ai["outcome"]):
            parts.append(reason)
        if stamp := ai.get("last_accepted"):
            last = datetime.fromisoformat(stamp).astimezone(d.get("zone", UTC))
            parts.append(f'last accepted {last:%-d %b %Y, %H:%M %Z}')
        ai_state = f' Local AI · {_e(" · ".join(parts))}.'
    elif d.get("narrator_enabled"):
        accepted = len(d.get("narration", {}))
        ai_state = (f' Local AI · {accepted} checked results.' if accepted else
                    ' Local AI enabled · no checked results in this snapshot.')
    nav = "".join(f'<a href="#{p}">{icon(symbol)}<span>{t}</span></a>'
                  for (p, t), symbol in zip(links, symbols, strict=True))
    narration_id = narrator.summary_id(d.get("narration", {})).decode("ascii")
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="garmin-dashboard" content="{_e(snapshot)}">'
        f'<meta name="garmin-narration" content="{narration_id}">'
        f'<meta http-equiv="Content-Security-Policy" content="{_e(CONTENT_POLICY)}">'
        '<meta name="viewport" '
        'content="width=device-width,initial-scale=1,viewport-fit=cover"><title>Garmin Health'
        f'</title><style>{CSS}</style></head><body><main class="wrap">'
        f'<header class="mast"><b>{icon("trend")}Garmin Health</b>'
        '<div class="theme" role="group" aria-label="Appearance">'
        '<button type="button" data-theme-choice="light" aria-pressed="true">Light</button>'
        '<button type="button" data-theme-choice="dark" aria-pressed="false">Dark</button>'
        '</div></header><p class="sr-only" id="chart-help">Arrow keys select a reading. '
        'Home and End move to the first and last readings. Escape clears the selection. '
        'Open Chart readings for the exact values.</p>'
        '<nav class="top" '
        f'aria-label="Dashboard pages">{nav}</nav>{"".join(pages)}<footer>{freshness} {status}{ai_state} '
        f'</footer></main><script>{SCRIPT}</script></body></html>')


_COORD = re.compile(r'(\b(?:x|y|x1|x2|y1|y2|cx|cy|width|height)=")(-?\d+\.\d)\d+"')
_PATH_NUM = re.compile(r'(-?\d+\.\d)\d+')
_PATH = re.compile(r'( (?:d|points)=")([^"]*)"')


def _compact(html_text: str) -> str:
    """Round chart coordinates to 0.1 px (invisible on screen; roughly a fifth smaller)."""
    html_text = _COORD.sub(r'\1\2"', html_text)
    return _PATH.sub(lambda m: m.group(1) + _PATH_NUM.sub(r"\1", m.group(2)) + '"', html_text)


def _atomic_write(path: Path, content: str) -> None:
    """Readers see either the old complete file or the new complete file; new mode is 0600."""
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".dashboard-", delete=False) as f:
            temp = Path(f.name)
            f.write(content)
        if path.exists():
            os.chmod(temp, stat.S_IMODE(path.stat().st_mode))
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def _snapshot_paths(out_dir: Path | None = None) -> tuple[Path, Path | None]:
    from garmin_mcp.config import data_dir

    configured = data_dir() / "dashboard"
    selected = out_dir or configured
    local = selected / "index.html"
    if selected.resolve() != configured.resolve():
        return local, None  # a custom build must not overwrite the owner's iCloud copy
    icloud = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs"
    return local, icloud / "Garmin" / "dashboard.html" if icloud.is_dir() else None


def _read_stamp(path: Path, name: bytes) -> bytes:
    try:
        with path.open("rb") as source:
            head = source.read(512)
    except OSError:
        return b""
    return head.partition(b'<meta name="' + name + b'" content="')[2].partition(b'"')[0]


def _snapshot_id(path: Path) -> bytes:
    return _read_stamp(path, b"garmin-dashboard")


def _narration_id(path: Path) -> bytes:
    return _read_stamp(path, b"garmin-narration")


def needs_rebuild(out_dir: Path | None = None) -> bool:
    local, icloud = _snapshot_paths(out_dir)
    snapshot = _snapshot_id(local)
    return (not snapshot.startswith(SNAPSHOT_PREFIX.encode()) or not _narration_id(local)
            or (icloud is not None and _snapshot_id(icloud) != snapshot))


def build(conn: sqlite3.Connection, out_dir: Path | None = None, *,
          queue_narration: bool = True, only_if_snapshot: bytes | None = None) -> Path:
    path, icloud = _snapshot_paths(out_dir)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Collect and write in the same order so a slower build cannot replace fresher data.
    with (path.parent / ".snapshot.lock").open("a") as lock:
        if os.name == "posix":
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX)
        if only_if_snapshot is not None and (
            _snapshot_id(path) != only_if_snapshot or narrator._sync_in_progress(conn)
        ):
            return path
        data = collect(conn)
        if only_if_snapshot is not None and narrator._sync_in_progress(conn):
            return path
        if data.get("available", True) and not (data["older_snapshot"] or data["sync_retry_required"]):
            data["guidance_change"] = coach_review.guidance(
                conn, data["end"], data["brief"]["focus"], evidence=data["guidance_evidence"])
        data["narrator_enabled"] = narrator.settings(conn)["enabled"]
        data["narration"], pending = narrator.cached(conn, data)
        data["narrator_status"] = narrator.snapshot_status(conn, data, data["narration"], pending)
        _write_copies(path, icloud, _compact(render(data)))
        if only_if_snapshot is None and data.get("available", True) and not (
                data["older_snapshot"] or data["sync_retry_required"]):
            coach_review.guidance(conn, data["end"], data["brief"]["focus"],
                                  evidence=data["guidance_evidence"], save=True)
        snapshot = (_snapshot_id(path) if queue_narration and pending
                    and only_if_snapshot is None and not narrator._sync_in_progress(conn) else b"")
    if snapshot:
        narrator.start_worker(conn, path, snapshot)
    return path


def _write_copies(path: Path, icloud: Path | None, content: str) -> None:
    _atomic_write(path, content)
    if icloud is not None:
        try:
            icloud.parent.mkdir(mode=0o700, exist_ok=True)
            _atomic_write(icloud, content)
        except OSError:
            warnings.warn("iCloud copy failed; the local dashboard is available.",
                          RuntimeWarning, stacklevel=2)


def main() -> None:
    import json
    import sys

    from garmin_mcp import db
    from garmin_mcp.config import db_path
    from garmin_mcp.publish import publish_if_enabled

    conn = db.connect(db_path())
    try:
        path = build(conn)
    finally:
        conn.close()
    print(path)
    result = publish_if_enabled(path)
    if result["status"] != "disabled":
        print(json.dumps({"dashboard_publish": result}), file=sys.stderr)


if __name__ == "__main__":
    main()
