"""Personal dashboard: multi-page, one self-contained HTML file with offline controls.

Pages are sections addressed by links (#today, #sleep, #run-<id>, ...). CSS `:target` shows one
at a time, including in readers that do not run scripts. Charts are inline SVG. A bundled
script handles point selection, theme and active navigation. Built from the same functions as the MCP
tools, so the dashboard and Claude always agree. Design rules: DASHBOARD_PLAN.md sections 6-8.
Output: $GARMIN_DATA_DIR/dashboard/index.html (+ a copy in iCloud Drive/Garmin if it exists).
"""

from __future__ import annotations

import html
import math
import os
import sqlite3
import stat
import tempfile
import warnings
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

from garmin_mcp import coaching, engine, health, insights, loads, norms, recovery, running, scores
from garmin_mcp.dashboard_interaction import CONTENT_POLICY, SCRIPT

W = 340  # SVG viewBox width: phone-first, text stays ~11-16 px from phone to desktop


def _e(v: Any) -> str:
    return html.escape("" if v is None else str(v))


def _f(v: Any, nd: int = 0, unit: str = "") -> str:
    if not isinstance(v, (int, float)) or not math.isfinite(v):
        return "–"
    return f"{v:,.{nd}f}{unit}"


# =============================================================================== data
def _last_full_night(conn: sqlite3.Connection, end: str) -> str | None:
    row = conn.execute("SELECT MAX(day) FROM sleep WHERE day <= ? AND sleep_s >= 3*3600",
                       (end,)).fetchone()
    return row[0] if row else None


def collect(conn: sqlite3.Connection, end: str | None = None) -> dict[str, Any]:
    if not _has(conn, "daily") or not insights._latest_day(conn):
        return {"available": False, "reason": "No Garmin data is available yet. Sync or import "
                "your history on the Mac to build your dashboard."}
    end = end or insights._latest_day(conn)
    e = date.fromisoformat(end)

    def lo(n: int) -> str:
        return (e - timedelta(days=n - 1)).isoformat()

    night = _last_full_night(conn, end)
    night_summary = conn.execute("SELECT sleep_s/3600.0, score FROM sleep WHERE day=?",
                                 (night,)).fetchone() if night else None
    ds = scores.daily_scores(conn, end)
    runs = []
    for aid, start, dist in conn.execute(
            "SELECT activity_id, start_time_local, distance_m FROM activities WHERE type LIKE "
            "'%run%' AND fit_parsed=1 ORDER BY start_time_local DESC LIMIT 8"):
        b = running.running_breakdown(conn, aid, _weight(conn))
        if b.get("available"):
            b.update(date=start[:10], km=round((dist or 0) / 1000, 2))
            runs.append(b)
    return {
        "_conn": conn, "end": end, "scores": ds, "bedtime": scores.bedtime_suggestion(conn, end),
        "older_snapshot": (datetime.now(engine._tz(conn)).date() - e).days > 1,
        "history": scores.history(conn, end, 14),
        "brief": insights.daily_brief(conn, end),
        "ranges": engine.personal_ranges(conn, end)["metrics"],
        "night": health.sleep_breakdown(conn, night) if night else None,
        "night_summary": night_summary,
        "sleep": conn.execute("SELECT day, sleep_s/3600.0, sleep_start FROM sleep WHERE day "
                              "BETWEEN ? AND ? AND sleep_s >= 3*3600 ORDER BY day",
                              (lo(30), end)).fetchall(),
        "hrv": recovery.recovery_trend(conn, end, 60)["days"],
        "rhr": conn.execute("SELECT day, resting_hr FROM daily WHERE day BETWEEN ? AND ? AND "
                            "resting_hr IS NOT NULL ORDER BY day", (lo(60), end)).fetchall(),
        "fitness": conn.execute("SELECT day, ctl, atl FROM fitness WHERE day BETWEEN ? AND ? "
                                "ORDER BY day", (lo(120), end)).fetchall()
        if _has(conn, "fitness") else [],
        "weekly_review": insights.weekly_review(conn, end)
        if _has(conn, "fitness") and _has(conn, "activity_load") else None,
        "weekly_load": _weekly_load(conn, end),
        "shifts": health.shifts(conn, end)["shifts"],
        "ageing": health.pace_of_ageing(conn, end),
        "marathon": health.marathon_shape(conn, end),
        "fitness_age": coaching.fitness_age(conn),
        "predictions": loads.race_predictions(conn, end, 180),
        "month": health.monthly_report(conn, _prev_month(end)),
        "month_history": health.monthly_history(conn, _prev_month(end)),
        "runs": runs, "form": running.form_trends(conn, 40),
        "explore": engine.explore(conn, end, 365, 8),
        "tests": running.test_runs(conn),
        "vo2_reference": norms.comparison(conn, end),
        "sync_retry_required": conn.execute("SELECT 1 FROM meta WHERE key='sync_retry_required'").fetchone()
        is not None,
        "feed": engine.insight_feed(conn, end, include_relationships=False)["insights"],
    }


def _has(conn: sqlite3.Connection, t: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone() is not None


def _weight(conn: sqlite3.Connection) -> float | None:
    if not _has(conn, "fit_profile"):
        return None
    row = conn.execute("SELECT weight_kg FROM fit_profile ORDER BY rowid DESC LIMIT 1").fetchone()
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
        v = conn.execute("SELECT SUM(load) FROM fitness WHERE day BETWEEN ? AND ?",
                         (a.isoformat(), min(e, a + timedelta(days=6)).isoformat())).fetchone()[0]
        out.append((a.isoformat(), round(v) if v is not None else None))
    return out


# =============================================================================== svg kit
ICONS = {
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


def dial(pct: float | None, label: str, value: str, sub: str, tone: str, href: str,
         frac: float | None = None) -> str:
    """270-degree ring. frac overrides pct/100 (used for strain 0-21)."""
    import math

    r, cx, cy, sw = 52, 64, 64, 10
    circ = 2 * math.pi * r
    arc = circ * 0.75
    f = frac if frac is not None else (pct or 0) / 100
    f = max(0.0, min(1.0, f))
    track = (f'<circle cx="{cx}" cy="{cy}" r="{r}" class="dial-track" stroke-width="{sw}" '
             f'stroke-dasharray="{arc:.1f} {circ:.1f}" transform="rotate(135 {cx} {cy})"/>')
    val = (f'<circle cx="{cx}" cy="{cy}" r="{r}" class="dial-val {tone}" stroke-width="{sw}" '
           f'stroke-dasharray="{arc * f:.1f} {circ:.1f}" transform="rotate(135 {cx} {cy})">'
           f'<title>{_e(label)}: {_e(value)}</title></circle>') if pct is not None or frac else ""
    return (f'<a class="dial" href="{href}"><svg viewBox="0 0 128 112" role="img" '
            f'aria-label="{_e(label)} {_e(value)}">{track}{val}'
            f'<text x="64" y="66" class="dial-num">{_e(value)}</text></svg>'
            f'<span class="dial-label">{_e(label)}</span><span class="dial-sub">{_e(sub)}'
            f'</span></a>')


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


def _point(x: float, y: float, label: str, value: str, cls: str = "hit") -> str:
    return (f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.4" class="{cls}" data-point '
            f'data-title="{_e(label)}" data-value="{_e(value)}">'
            f'<title data-native>{_e(label)} · {_e(value)}</title></circle>')


def _chart(kind: str, parts: list[str], w: int, h: int, limits: tuple,
           x_label: str, y_label: str, initial: str) -> str:
    left, right, top, bottom = limits
    overlay = (f'<g class="chart-cursor" aria-hidden="true">'
               f'<line class="cursor-x" y1="{top}" y2="{bottom}"/>'
               f'<line class="cursor-y" x1="{left}" x2="{right}"/>'
               '<circle r="3.3"/></g>')
    return (f'<figure class="chart-interaction" data-chart="{kind}">'
            f'<figcaption class="chart-readout"><strong>Explore chart</strong>'
            f'<span>{_e(initial)}</span></figcaption><span class="sr-only" role="status"></span>'
            f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" '
            f'aria-label="{_e(y_label)} by {_e(x_label)}" aria-describedby="chart-help">'
            f'{"".join(parts)}{overlay}</svg></figure>')


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


def _x_ticks(labels: list[str], x, bottom: int, wide: bool) -> list[str]:
    if len(labels) <= 3:
        indices = range(len(labels))
    else:
        divisions = 4 if wide and len(labels) >= 6 else 2
        indices = sorted({round(i * (len(labels) - 1) / divisions) for i in range(divisions + 1)})
    return [f'<text x="{x(i):.2f}" y="{bottom + 17}" text-anchor="middle" class="tick">'
            f'{_e(_short(labels[i]))}</text>' for i in indices]


def line_chart(points: list[tuple[str, float]], unit: str = "", band: tuple | None = None,
               band_series: list[tuple[float, float] | None] | None = None, h: int = 190,
               nd: int = 0, cls: str = "s1", w: int = W, fmt: Any = None,
               x_label: str = "Date", y_label: str = "Value") -> str:
    """Date spacing reflects elapsed days. Missing observations stay out of the cursor."""
    bounds = band_series if band_series and len(band_series) == len(points) else [band] * len(points)
    rows = [(label, value, interval) for (label, value), interval in
            zip(points, bounds, strict=True) if isinstance(value, (int, float)) and math.isfinite(value)]
    if not rows:
        return '<p class="empty">No measurements recorded for this chart.</p>'
    days = None
    try:
        rows.sort(key=lambda row: date.fromisoformat(row[0][:10]))
        days = [date.fromisoformat(row[0][:10]).toordinal() for row in rows]
    except ValueError:
        pass
    values = [v for _, v, _ in rows]
    values.extend(v for _, _, interval in rows if interval for v in interval)
    ticks = _ticks(*_scale(values))
    h = max(h, 184)
    left, right, top, bottom = 51, w - 31, 29, h - 49

    def x(i: int) -> float:
        if len(rows) == 1:
            return (left + right) / 2
        if days and days[-1] > days[0]:
            return left + (right - left) * (days[i] - days[0]) / (days[-1] - days[0])
        return left + (right - left) * i / (len(rows) - 1)

    def y(v: float) -> float:
        return bottom - (bottom - top) * (v - ticks[0]) / (ticks[-1] - ticks[0])

    g = _horizontal_scale(ticks, left, right, y, fmt or _tick_number)
    if band:
        g.append(f'<rect class="band" x="{left}" y="{y(band[1]):.2f}" width="{right - left}" '
                 f'height="{max(0, y(band[0]) - y(band[1])):.2f}"><title>Your usual range</title></rect>')
    elif band_series:
        # Draw the envelope only across adjacent valid bounds.
        for i, (a, b) in enumerate(pairwise(rows)):
            if a[2] and b[2]:
                g.append(f'<polygon class="band" points="{x(i):.2f},{y(a[2][1]):.2f} '
                         f'{x(i + 1):.2f},{y(b[2][1]):.2f} {x(i + 1):.2f},{y(b[2][0]):.2f} '
                         f'{x(i):.2f},{y(a[2][0]):.2f}"/>')
    g += _axes(left, right, top, bottom, h, x_label, y_label)
    locations = [f"{'M' if i == 0 else 'L'}{x(i):.2f},{y(v):.2f}" for i, (_, v, _) in enumerate(rows)]
    g.append(f'<path d="{" ".join(locations)}" class="ln {cls}"/>')
    for i, (label, value, interval) in enumerate(rows):
        display = fmt(value) if fmt else _f(value, nd, unit)
        if interval:
            display += f" · usual range {_f(interval[0], nd)}–{_f(interval[1], nd, unit)}"
        g.append(_point(x(i), y(value), label, display,
                        "dot s1" if i == len(rows) - 1 else "hit"))
    g += _x_ticks([label for label, _, _ in rows], x, bottom, w > W)
    return _chart("line", g, w, h, (left, right, top, bottom), x_label, y_label,
                  "Hover, tap, or slide to read a point")


def bar_chart(items: list[tuple[str, float]], unit: str = "", ref: float | None = None,
              ref_label: str = "", h: int = 190, nd: int = 0,
              tones: list[str] | None = None, w: int = W, x_label: str = "Date",
              y_label: str = "Value") -> str:
    if not any(isinstance(v, (int, float)) and math.isfinite(v) for _, v in items):
        return '<p class="empty">No measurements recorded for this chart.</p>'
    values = [v for _, v in items if isinstance(v, (int, float)) and math.isfinite(v)]
    ticks = _ticks(0, max(max(values), ref or 0) or 1)
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
        g.append(f'<rect x="{x(i) - width / 2:.2f}" y="{y(value):.2f}" width="{width:.2f}" '
                 f'height="{max(0, bottom - y(value)):.2f}" rx="2" class="bar {_e(tone)}">'
                 f'<title data-native>{_e(label)} · {_e(display)}</title></rect>')
        g.append(_point(x(i), y(value), label, display))
    g += _x_ticks([label for label, _ in items], x, bottom, w > W)
    return _chart("bar", g, w, h, (left, right, top, bottom), x_label, y_label,
                  "Hover, tap, or slide to read a bar")


def scatter(points: list[tuple[str, float, float]], xl: str, yl: str, slope: float | None,
            w: int = W, h: int = 238, x_unit: str = "", y_unit: str = "", lag: int = 0) -> str:
    """Signed axes show how each measurement differs from its own recent average."""
    points = [(d, a, b) for d, a, b in points if math.isfinite(a) and math.isfinite(b)]
    if len(points) < 3:
        return '<p class="empty">Not enough paired observations yet.</p>'
    xs, ys = [p[1] for p in points], [p[2] for p in points]
    x_ticks = _ticks(*_scale(xs + [0], 0.05))
    x0, x1 = x_ticks[0], x_ticks[-1]
    y_values = ys + [0]
    fit_values = None
    if slope is not None:
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
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
    g = _horizontal_scale(y_ticks, left, right, y, signed)
    for v in x_ticks:
        g.append(f'<line x1="{x(v):.2f}" x2="{x(v):.2f}" y1="{top}" y2="{bottom}" '
                 f'class="{"zero" if v == 0 else "grid"}"/>'
                 f'<text x="{x(v):.2f}" y="{bottom + 17}" class="tick" text-anchor="middle">'
                 f'{signed(v)}</text>')
    g.append(f'<line x1="{left}" x2="{right}" y1="{y(0):.2f}" y2="{y(0):.2f}" class="zero"/>')
    g += _axes(left, right, top, bottom, h, x_label, y_label)
    if fit_values is not None:
        g.append(f'<line x1="{x(min(xs)):.2f}" y1="{y(fit_values[0]):.2f}" '
                 f'x2="{x(max(xs)):.2f}" y2="{y(fit_values[1]):.2f}" class="fit"/>')
    for d, a, b in points:
        second = (date.fromisoformat(d) + timedelta(days=lag)).isoformat() if lag else d
        when = f"{d} → {second}" if lag else d
        value = f"{xl}: {a:+.2f} {x_unit} · {yl}: {b:+.2f} {y_unit}"
        g.append(_point(x(a), y(b), when, value, "pt"))
    return _chart("scatter", g, w, h, (left, right, top, bottom), x_label, y_label,
                  "Hover or tap a dot · difference from your usual")


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
    return (f'<div class="sm">{fn(*a, w=W, **k)}</div><div class="lg">{fn(*a, w=720, **k)}'
            f'</div>')


def _clock(h: float) -> str:
    m = round(h * 60) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def _short(d: str) -> str:
    try:
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
    nav = "" if pid == "today" else (f'<a class="back" href="{back}">{icon("back")}'
                                     f'<span>Back</span></a>')
    return (f'<article class="page" id="{pid}">{nav}<header class="ph"><h2>{_e(title)}</h2>'
            f'<p class="lede">{lede}</p></header><div class="grid">{body}</div></article>')


def _row(label: str, value: str, note: str = "", state: str = "") -> str:
    ic = {"good": icon("ok", "good"), "up": icon("up", "warn"), "down": icon("down", "warn")}
    return (f'<li><span class="k">{_e(label)}</span><span class="v">{value}</span>'
            f'<span class="n">{ic.get(state, "")}{_e(note)}</span></li>')


_TREND_LABELS = {
    "hrv": ("Overnight HRV", "ms", "recovery"),
    "rhr": ("Resting heart rate", "bpm", "recovery"),
    "sleep_h": ("Sleep duration", "h", "sleep"),
    "vo2max": ("Garmin VO₂max", "mL/kg/min", "body"),
    "ctl": ("Training load trend", "load units", "training"),
    "steps": ("Daily steps", "steps", "training"),
}

_PATTERN_LABELS = {
    "sleep_h": "Sleep duration", "hrv": "Overnight HRV", "rhr": "Resting heart rate",
    "garmin_readiness": "Garmin readiness", "bedtime_h": "Bedtime",
    "trimp": "Training load", "sleep_score": "Sleep score", "last_training_end_h": "Workout end time",
    "stress": "Daytime stress", "steps": "Daily steps", "intensity_min": "Intensity minutes",
}
_VITAL_LABELS = {
    "hrv_ms": ("Heart rate variability", "ms", 0),
    "resting_hr_bpm": ("Resting heart rate", "bpm", 0),
    "respiration_brpm": ("Breathing rate", "/min", 1),
    "sleep_spo2_pct": ("Blood oxygen in sleep", "%", 0),
    "sleep_hr_bpm": ("Heart rate in sleep", "bpm", 0),
}


def _insight(title: str, details: str, target: str) -> str:
    return (f'<li><a class="finding" href="#{target}"><span><strong>{_e(title)}</strong>'
            f'<span class="finding-detail">{_e(details)}</span></span>{icon("chev")}</a></li>')


def _standouts(d: dict[str, Any]) -> str:
    rows = []
    for item in d["feed"]:
        if item["kind"] == "trend" and item["per_30_days"] and item["metric"] in _TREND_LABELS:
            name, unit, link = _TREND_LABELS[item["metric"]]
            direction = "trending up" if item["direction"] == "rising" else "trending down"
            rows.append(_insight(f"{name} is {direction}",
                                 f'{item["per_30_days"]:+g} {unit} per 30 days · '
                                 f'{item["points"]} readings in the last 90 days', link))
        elif item["kind"] == "hrv_guided":
            direction = "below" if "below" in item["title"] else "above"
            rows.append(_insight(f"Overnight HRV is {direction} your usual range",
                                 "Based on your seven-day average", "recovery"))
        elif item["kind"] == "vitals":
            changes = [f'{_VITAL_LABELS[k][0]} {v["state"]} usual' for k, v in d["ranges"].items()
                       if k in _VITAL_LABELS and v["state"] in ("above", "below")]
            rows.append(_insight("Several readings differ from your usual range",
                                 " · ".join(changes), "recovery"))
        elif item["kind"] == "load":
            title = "Your weekly load increased" if item["title"] == "Load jump" else "Your longest run increased"
            rows.append(_insight(title, item["detail"], "training"))
        if len(rows) == 2:
            break
    best = next((p for p in d["explore"]["pairs"] if p["notable"]), None)
    if best:
        x, y = _PATTERN_LABELS[best["x"]], _PATTERN_LABELS[best["y"]]
        rows.append(_insight(f"{x} and {y} showed a relationship",
                             f'{best["n"]} paired days · personal association', "patterns"))
    if not rows:
        return '<p class="sub">There are no clear changes or recurring patterns in the records available.</p>'
    return '<ul class="findings">' + "".join(rows) + '</ul>'


def page_today(d: dict[str, Any]) -> str:
    s = d["scores"]
    rec, sl, st = s["recovery"], s["sleep"], s["strain"]
    tone = TONE.get(rec.get("band") or "", "muted")
    sleep_sub = (f'{_f(sl.get("hours"), 1)} of {_f(sl.get("need_h"), 1)} h'
                 if sl.get("hours") else "last night not recorded")
    tr = st.get("target_range") or [None, None]
    dials = (
        dial(rec.get("pct"), "Recovery", _f(rec.get("pct"), 0, "%"),
             (rec.get("label") or "calibrating").capitalize(), tone, "#recovery")
        + dial(sl.get("pct"), "Sleep goal", _f(sl.get("pct"), 0, "%"), sleep_sub, "s1", "#sleep")
        + dial(None, "Strain", _f(st.get("value"), 1),
               f"target {tr[0]}–{tr[1]}" if tr[0] is not None else "target unavailable", "s2",
               "#training", frac=(st.get("value") or 0) / 21))
    sug = d["brief"].get("suggestion") or {}
    bt = d["bedtime"]
    plan = (sug.get("suggest") or "Training guidance is unavailable").capitalize()
    reason = (sug.get("why") or "").capitalize().rstrip(".")
    if plan == "Planned training is fine":
        plan = "Train as planned if you feel well"
        if "our readiness is normal" in (sug.get("why") or ""):
            reason = "Your recovery signals are within their usual range overall"
    today = f'<p class="say">{_e(plan)}.</p>'
    if reason:
        today += f'<p class="sub">{_e(reason)}.</p>'
    if bt.get("available"):
        today += (f'<p class="pill">{icon("moon")}<span>Bed by <b>{_e(bt["suggested_bedtime"])}'
                  f'</b> for a usual {_e(bt["usual_wake"])} wake time</span></p>')
    garmin = (f'<span class="chip">Garmin readiness {_f(rec["garmin_readiness"])}'
              f'{_e(" · " + rec["garmin_level"].title()) if rec.get("garmin_level") else ""}</span>'
              if rec.get("garmin_readiness") is not None else "")
    if d.get("older_snapshot"):
        today = (f'<p class="say">Sync for current training guidance.</p>'
                 f'<p class="sub">This snapshot uses your records through {_short(d["end"])}.</p>')
    rows = []
    for k, (lab, unit, nd) in _VITAL_LABELS.items():
        m = d["ranges"].get(k)
        if not m or m.get("value") is None:
            continue
        rg = m.get("range") or [None, None]
        state = {"in range": "good", "above": "up", "below": "down"}.get(m.get("state"), "")
        note = (f'{m.get("state", "")} · usual {_f(rg[0], nd)}–{_f(rg[1], nd)}'
                if m.get("range") else "Personal range is still calibrating")
        rows.append(_row(lab, f'{_f(m["value"], nd)} <small>{unit}</small>', note, state))
    hist = d["history"]
    week = bar_chart([(h["day"], h["recovery"]) for h in hist], "%", y_label="Recovery (%)",
                     tones=[TONE.get(h.get("band") or "", "muted") for h in hist])
    why = f'<ul class="rows">{"".join(rows)}</ul>' if rows else (
        '<p class="empty">Not enough recent measurements to compare with your personal ranges.</p>')
    body = (_card("Training plan", today + garmin)
            + f'<section class="card hero"><div class="dials">{dials}</div>'
              f'<p class="hero-note">Recovery uses {rec.get("signals_used", 0)} of '
              f'{rec.get("signals_total", 4)} signals. Strain covers recorded workouts.</p></section>'
            + _card("What stands out", _standouts(d))
            + _card("Your measurements", why, "Latest readings against your usual range")
            + _card("Recovery over 14 days", week, "Green ≥ 67 · amber 34–66 · red ≤ 33",
                    href="#recovery", wide=True))
    lede = f'Data through {_short(d["end"])}'
    if d.get("sync_retry_required"):
        lede += " Latest sync is incomplete; some measurements may be missing."
    return _page("today", "Today", lede, body)


def page_sleep(d: dict[str, Any]) -> str:
    n = d["night"] or {}
    parts = n.get("parts") or {}
    stages = ""
    for lab in ("Deep sleep", "REM sleep", "Light sleep"):
        p = parts.get(lab)
        if p and p.get("value") is not None:
            o = p.get("optimal") or [None, None]
            stages += _row(lab, f'{p["value"]}<small>%</small>',
                           f'{p.get("rating") or ""} · ideal {_f(o[0])}–{_f(o[1])} %',
                           "good" if p.get("rating") in ("Excellent", "Good") else "down")
    for lab in ("Duration", "Awakenings", "Restlessness", "Stress during sleep"):
        p = parts.get(lab)
        if p:
            stages += _row(lab, _e(p.get("rating") or "–"))
    dip = n.get("heart_rate_dip")
    dip_html = ""
    if dip:
        dip_html = (f'<div class="big">{dip["dip_pct"]:.0f}<small>%</small></div>'
                    f'<p class="say">{_e(dip["label"].capitalize())}</p><p class="sub">Day '
                    f'{dip["awake_mean_hr"]:.0f} bpm → sleep {dip["sleep_mean_hr"]:.0f} bpm. '
                    f'{_e(dip["meaning"])}</p>')
    need = d["scores"]["sleep"].get("need_h") or recovery.DEFAULT_SLEEP_NEED_H
    ref_name = ("Garmin sleep need" if d["scores"]["sleep"].get("need_source") == "Garmin sleep need"
                else "Planning target")
    sleep_by_day = {row[0]: row[1] for row in d["sleep"]}
    nights = [(day, sleep_by_day.get(day)) for day in recovery._days_back(d["end"], 30)]
    durations = both(bar_chart, nights, " h", ref=need,
                     nd=1, y_label="Sleep duration (h)",
                     x_label="Wake date")
    bed = []
    tz = engine._tz(d['_conn'])
    for day, _, start in d["sleep"]:
        if start:
            loc = datetime.fromisoformat(start).replace(tzinfo=UTC).astimezone(tz)
            bed.append((day, ((loc.hour - 12) % 24) + loc.minute / 60 + 12))  # 25.5 = 01:30
    bedtimes = both(line_chart, bed, fmt=_clock, y_label="Bedtime (local)", x_label="Wake date")
    hours, saved_score = d["night_summary"] or (None, None)
    score = n.get("overall") if n.get("overall") is not None else saved_score
    headline = (f'<div class="big">{_f(hours, 1)}<small> h asleep</small></div>'
                if hours is not None else '<p class="empty">No complete night recorded yet.</p>')
    recorded = f'Wake date {_short(n["day"])}' if n.get("day") else ""
    garmin = f' · Garmin sleep score {_f(score)}/100' if score is not None else ""
    body = (_card("Latest recorded night", headline + f'<p class="sub">{recorded}{garmin}</p>',
                  wide=True)
            + _card("Sleep duration over 30 nights", durations,
                    f"Dashed line · {ref_name} {need:.1f} h", wide=True)
            + _card("Bedtime", bedtimes, "When you fell asleep in your local time zone.", wide=True))
    if stages:
        body += _card("Garmin sleep breakdown", f'<ul class="rows">{stages}</ul>')
    if dip_html:
        body += _card("Day and sleep heart rate", dip_html)
    debt = d["scores"]["sleep"].get("debt_7d_h")
    lede = (f"Seven-night sleep shortfall <b>{_f(debt, 1)} h</b>" if debt is not None else
            "Sleep shortfall needs more nights of data.")
    return _page("sleep", "Sleep", lede, body)


def page_recovery(d: dict[str, Any]) -> str:
    hv = [(x["day"], x.get("hrv_7d_ms")) for x in d["hrv"]]
    bands = [tuple(x["hrv_band_ms"]) if x.get("hrv_band_ms") else None for x in d["hrv"]]
    hv_ok = [(p, b) for p, b in zip(hv, bands, strict=True) if p[1] is not None]
    hrv_chart = both(line_chart, [p for p, _ in hv_ok], " ms",
                     band_series=[b for _, b in hv_ok], y_label="Average HRV (ms)")
    rhr = both(line_chart, list(d["rhr"]), " bpm", y_label="Resting heart rate (bpm)")
    sh = d["shifts"]
    names = {"resting_hr": ("Resting HR", "bpm"), "hrv": ("HRV", "ms"),
             "sleep_h": ("Sleep", "h")}
    shift_rows = "".join(_row(names[k][0], f'{v["change"]:+.1f} <small>{names[k][1]}</small>',
                              f'since {_short(v["date"])} ({v["before_mean"]:.1f} → '
                              f'{v["after_mean"]:.1f})') for k, v in sh.items())
    body = (_card("Heart rate variability (7-day average)", hrv_chart,
                  "Shaded = your normal band. Interpret sustained changes alongside sleep, "
                  "training, stress and how you feel.", wide=True)
            + _card("Resting heart rate", rhr, "Compare with your own baseline; recent training, "
                    "sleep, stress and illness can influence it.", wide=True)
            + _card("Lasting changes", f'<ul class="rows">{shift_rows}</ul>' if shift_rows
                    else '<p class="empty">No lasting shift in the last 6 months.</p>',
                    "Step changes found in the last 180 days"))
    return _page("recovery", "Recovery", "How well your body is absorbing training and life.",
                 body)


def _status_label(st: Any) -> str:
    """Readable Garmin training status; unknown codes show as a dash, never crash the page."""
    if not isinstance(st, str) or not st or st.isdigit():
        return "–"
    return st.replace("_", " ").title()


def page_training(d: dict[str, Any]) -> str:
    fit = both(line_chart, [(r[0], r[1]) for r in d["fitness"]], " load units", nd=1,
               y_label="Smoothed training load")
    wl = both(bar_chart, d["weekly_load"], " load units", y_label="Weekly training load",
              x_label="Week beginning")
    week_card = ""
    review = d["weekly_review"]
    if review:
        week, usual, rest = review["week"], review["previous_4wk_weekly_avg"], review["recovery"]
        prior_text = (f'Previous four-week average: {_f(usual["trimp"])} points/week'
                      if usual["sessions"] else "No recent comparison weeks with recorded workouts")
        rows = (_row("Recorded workouts", _f(week["sessions"]),
                     f'{_f(week["hours"], 1)} h · {_f(week["run_km"], 1)} km running')
                + _row("Training load", _f(week["trimp"]), prior_text)
                + _row("Average sleep", _f(rest["avg_sleep_h"], 1, " h"),
                       f'{rest["sleep_nights"]} of 7 nights used'))
        week_card = _card("Training and recovery this week", f'<ul class="rows">{rows}</ul>',
                          f'{_short(week["from"])}–{_short(week["to"])} · recorded data', wide=True)
    body = (week_card
            + _card("Training load trend", fit, "42-day smoothed load. Tracks training exposure, "
                  "not a direct fitness test.", wide=True)
            + _card("Load per week", wl, "Weeks start on Monday. The latest week may still be in progress.",
                    wide=True))
    status = _status_label(d["brief"].get("garmin_training_status"))
    lede = (f"Garmin training status <b>{_e(status)}</b>" if status != "–" else
            "Your recorded workouts, load and recovery.")
    return _page("training", "Training", lede, body)


def _run_label(r: dict[str, Any]) -> str:
    return f'{_short(r["date"])} · {r["km"]:.1f} km · {r["pace"]}/km'


def page_running(d: dict[str, Any]) -> str:
    runs = d["runs"]
    lst = "".join(f'<a class="tile" href="#run-{r["activity_id"]}"><b>{_e(_run_label(r))}</b>'
                  f'<span>avg HR {_f(r.get("avg_hr"))} · cadence '
                  f'{_f((r["form"].get("cadence_spm") or {}).get("value"))}</span>'
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
    mshape = ""
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
    body = (f'<nav class="card tiles wide">{lst or "<p class=empty>No runs with detail yet.</p>"}'
            f'</nav>'
            + _card("Aerobic fitness on your usual run", _tests(d["tests"]),
                    "Same-distance steady runs: speed per heartbeat over time", wide=True)
            + _card("Marathon shape", mshape, "Endurance readiness (Runalyze method)")
            + _card("Race time estimates", races, "Recorded efforts, endurance and max HR affect accuracy.")
            + _card("Cadence over your runs", cad, "Steps per minute. Rises with pace, so "
                    "compare runs on each run's page.", wide=True))
    return _page("running", "Running", "Tap a run for a coach-style breakdown.", body)


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


def page_run(r: dict[str, Any]) -> str:
    rows = ""
    for key, fm in r["form"].items():
        rng = GAUGE_RANGE.get(key)
        g = gauge(fm["value"], running.GAUGES[key], *rng,
                  marker2=fm.get("your_usual_at_this_pace"),
                  unit="") if rng else ""
        rating = (fm.get("garmin_gauge") or {}).get("label", "")
        vs = fm.get("vs_usual_pct")
        bits = [rating.capitalize()] + ([f"{vs:+.1f} % vs your usual at this pace"]
                                        if vs is not None else [])
        vs_txt = " · ".join(b for b in bits if b)
        rows += (f'<div class="form-row"><div class="fr-head"><span>{_e(fm["label"])}</span>'
                 f'<b>{fm["value"]}</b></div>{g}<p class="sub">{_e(vs_txt)}</p></div>')
    p = r["pacing"]
    work = "".join(f'<li>{_e(w)}</li>' for w in r["work_on"])
    facts = (_row("Pace", f'{_e(r["pace"])}<small>/km</small>')
             + _row("Average heart rate", f'{_f(r.get("avg_hr"))}<small> bpm</small>')
             + _row("Heart-rate change", f'{_f(p.get("hr_drift_bpm"), 1)}<small> bpm</small>',
                    "Second half of recorded moving time versus the first")
             + _row("Power (wrist)", f'{_f(r.get("power_w"))}<small> W</small>')
             + _row("Running effectiveness", _f(r.get("running_effectiveness"), 2),
                    "speed per W/kg; compare only with yourself"))
    body = (_card("What to work on", f'<ol class="work">{work}</ol>', "From this run's data",
                  wide=True)
            + _card("Form", rows + '<p class="legend"><i class="mk"></i>this run <i class='
                    '"mk2"></i>your usual at this pace · colours = Garmin rating</p>',
                    "Garmin's colour bands, plus how this run compares with you", wide=True)
            + _card("Pacing and effort", "", "Kilometre splits, timing and pace versus heart rate",
                    href=f'#run-{r["activity_id"]}-pacing')
            + _card("Numbers", f'<ul class="rows">{facts}</ul>'))
    return _page(f'run-{r["activity_id"]}', _run_label(r),
                 f'Compared with {r["comparison_runs"]} earlier runs.', body, back="#running")


def page_run_pacing(r: dict[str, Any]) -> str:
    p = r["pacing"]
    splits = [(f"km {i}", seconds) for i, seconds in enumerate(p["km_split_s"], 1)]
    chart = both(line_chart, splits, fmt=loads._hms, y_label="Elapsed time (min:sec)",
                 x_label="Kilometre")
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
    effort = (_row("Heart-rate change", f'{_f(p["hr_drift_bpm"], 1)}<small> bpm</small>')
              + _row("Efficiency change", f'{_f(-dc if dc is not None else None, 1)}<small> %</small>',
                     "Lower means less grade-adjusted speed per heartbeat in the second half"))
    body = (_card("Kilometre splits", chart + f'<p class="sub">{_e(half_note)}</p>',
                  "Elapsed time for each full recorded kilometre. "
                  "Pauses count toward these splits.", wide=True)
            + _card("Timing", f'<ul class="rows">{timing}</ul>')
            + _card("Pace and heart rate", f'<ul class="rows">{effort}</ul>',
                    "Equal moving-time halves. Needs a steady run with enough heart-rate data."))
    aid = r["activity_id"]
    return _page(f"run-{aid}-pacing", "Pacing and effort", _e(_run_label(r)), body, back=f"#run-{aid}")


def page_body(d: dict[str, Any]) -> str:
    fa = d["fitness_age"]
    lev = "".join(_row(x["lever"].capitalize(), f'{_f(x["current"], 1)} → {_f(x["target"], 1)}'
                       f'<small> {x.get("unit") or ""}</small>',
                       f'fitness age {_f(x["fitness_age_if_reached"], 1)} if reached')
                  for x in (fa.get("levers") or [])[:4])
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
    body = (_card("Fitness age", f'<div class="big">{_f(fa.get("garmin_fitness_age"), 1)}'
                  f'<small> yrs</small></div><p class="sub">Calendar age '
                  f'{_e(fa.get("chronological_age"))} · best reachable '
                  f'{_f(fa.get("achievable_age"), 1)}</p><ul class="rows">{lev}</ul>',
                  "Garmin's estimate and the levers that move it")
            + _card("Fitness-age trend", ag_html, "Change in Garmin's estimate per calendar year")
            + _card(f"Month report · {mo['month']}", f'<ul class="rows">{mrows}</ul>',
                    "Explore six months and check how many days were recorded",
                    wide=True, href="#month-detail"))
    if "vo2_reference" in d:
        body += _card("VO₂max reference", vo2_reference(d["vo2_reference"]),
                      "Garmin and our effective estimate, shown separately", wide=True)
    return _page("body", "Body & long term", "Slow signals that change over months.", body)


def _month_bars(history: list[dict[str, Any]], key: str, unit: str, nd: int,
                coverage_key: str) -> str:
    values = [m["values"][key] for m in history]
    top = max((v for v in values if v is not None), default=0) or 1
    rows = []
    for month, value in zip(history, values, strict=True):
        cov = month["coverage"]
        width = max(0, 100 * value / top) if value is not None else 0
        bar = f'<span class="month-bar" aria-hidden="true"><i style="width:{width:.1f}%"></i></span>'
        count = (f'{cov[coverage_key]}/{cov["calendar_days"]}'
                 if coverage_key != "runs_with_distance" else str(cov[coverage_key]))
        label = date.fromisoformat(month["month"] + "-01").strftime("%b %Y")
        rows.append(f'<tr><th scope="row">{label}</th><td>{_f(value, nd, unit)}{bar}</td>'
                    f'<td>{count}</td></tr>')
    heading = "Recorded runs" if coverage_key == "runs_with_distance" else "Days covered"
    return ('<table class="month-bars"><thead><tr><th scope="col">Month</th>'
            f'<th scope="col">Value</th><th scope="col">{heading}</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def page_months(d: dict[str, Any]) -> str:
    history = d["month_history"]
    cards = (
        _card("Sleep duration", _month_bars(history, "avg_sleep_h", " h", 2, "sleep_nights"),
              "Average across nights with at least three recorded hours")
        + _card("Overnight HRV", _month_bars(history, "avg_hrv", " ms", 1, "hrv_nights"),
                "Average of recorded nightly values")
        + _card("Running distance", _month_bars(history, "run_km", " km", 1, "runs_with_distance"),
                "Recorded kilometres from activities with distance", wide=True)
    )
    return _page("month-detail", "Monthly history", "Six full calendar months. Compare coverage "
                 "before interpreting differences.", cards, back="#body")


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
    v = r["values"]
    markers = [(name, value, cls) for name, value, cls in (
        ("Garmin", r.get("garmin"), "vo2-garmin"),
        ("Effective", r.get("effective"), "vo2-effective")) if isinstance(value, (int, float))]
    lo, hi = _scale(list(v.values()) + [x[1] for x in markers], 0.05)

    def x(value):
        return 20 + 300 * (value - lo) / (hi - lo)

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
    svg = _chart("scatter", parts, W, 84, (20, 320, 10, 55),
                 "VO₂max (mL/kg/min)", "Population reference", "Hover or tap the reference band")
    return (f'{svg}<p class="sub">Grey dot: Garmin · blue outline: effective estimate. '
            f'Line: 5th–95th · solid band: 25th–75th.</p>'
            f'<ul class="rows">{facts}</ul><p class="sub">{_e(caveat)}</p>'
            f'<p class="chart-note">{_e(r["sex"].title())}, age {_e(r["age_group"])} · '
            f'<a class="source-link" href="{norms.SOURCE}" rel="noreferrer">FRIEND 2015, Table 3</a></p>')


def page_patterns(d: dict[str, Any]) -> str:
    lab = _PATTERN_LABELS
    explore = d["explore"]
    cards = ""
    for p in explore["pairs"]:
        x, y = lab.get(p["x"], p["x"]), lab.get(p["y"], p["y"])
        when = "same day" if p["lag_days"] == 0 else "next day"
        trend = p.get("slope") if p["notable"] else None
        status = "Pattern found" if p["notable"] else "No clear pattern"
        plot = both(scatter, p["points"], x, y, trend, x_unit=engine.UNITS[p["x"]],
                    y_unit=engine.UNITS[p["y"]], lag=p["lag_days"])
        statement = p["statement"].partition(" (r =")[0] if p["notable"] else ""
        comment = f'<p class="sub">{_e(statement)}.</p>' if statement else ""
        body = (f'<p class="sub"><strong>{status}</strong> · {p["n"]} paired days</p>'
                f'{comment}{plot}<p class="chart-note">Zero is your recent average. '
                f'Correlation {p["r"]:+.2f} · 95% range '
                f'{p["r_ci95"][0]:+.2f} to {p["r_ci95"][1]:+.2f}.</p>')
        cards += _card(f"{x} & {y} ({when})", body, wide=True)
    count = ("No clear patterns yet" if not explore["notable"] else
             f'{explore["notable"]} patterns found')
    lede = (f'{count} · {explore["eligible"]} comparisons had enough data. '
            f'Values show differences from your recent averages.')
    return _page("patterns", "Patterns", lede, cards or _card(
        "Patterns", '<p class="empty">Not enough data yet.</p>'))


# =============================================================================== render
CSS = """
:root{color-scheme:light;--page:#f3f5f8;--surface:#fff;--ink:#172033;--ink2:#48556a;
--muted:#546174;--grid:#dfe4ec;--axis:#687487;--border:#dce3eb;--s1:#1868c4;
--accent:#edf5ff;--active:#104f9d;--cursor:#39669a;
--s2:#eb6834;--good:#0ca30c;--warn:#fab219;--serious:#ec835a;--bad:#d03b3b;--purple:#6250d6;
--band:rgba(42,120,214,.12);--goodtext:#006300}
:root[data-theme=dark]{color-scheme:dark;--page:#10151f;--surface:#1a2230;--ink:#f3f6fa;
--ink2:#c4cede;--muted:#aab8cd;--grid:#354155;--axis:#899bb4;--border:#303c50;--s1:#6baaff;
--accent:#202f48;--active:#b6d9ff;--cursor:#b6d9ff;
--s2:#d95926;--purple:#9085e9;--band:rgba(57,135,229,.18);--goodtext:#0ca30c}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,
"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
a:focus-visible,summary:focus-visible,button:focus-visible,.chart:focus-visible,.table-wrap:focus-visible{
outline:3px solid var(--s1);outline-offset:3px}
.chart:focus:not(:focus-visible){outline:none}
.wrap{max-width:1080px;margin:0 auto;padding:16px 16px 48px}
.mast{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:10px}
.mast b{font-size:16px;letter-spacing:-.01em}
.theme{display:none;border:1px solid var(--border);border-radius:12px;background:var(--surface)}
[data-interactive] .theme{display:flex}
.theme button{min-height:42px;border:0;background:transparent;color:var(--ink2);font:600 13px system-ui;
padding:0 13px;border-radius:11px;cursor:pointer}
.theme button[aria-pressed=true]{background:var(--accent);color:var(--active)}
.top{display:flex;gap:4px;padding:4px;margin:0 -4px 22px;border-bottom:1px solid var(--border)}
.top a{flex:none;display:inline-flex;align-items:center;min-height:44px;padding:8px 14px;border-radius:10px;font-size:13px;font-weight:600;
color:var(--ink2)}
.top a:hover,.top a[aria-current=page]{background:var(--accent);color:var(--active)}
@media(max-width:620px){
.top{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));overflow:visible}
.top a{justify-content:center;padding:4px;font-size:12px}
}
.sr-only{width:1px;height:1px;position:absolute;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
.page{display:none}#today{display:block}body:has(.page:target) #today:not(:target){display:none}
.page:target{display:block}
.ph{margin:0 0 19px}.ph h2{font-size:34px;line-height:1.1;letter-spacing:-.03em;margin:0 0 6px}
.lede{margin:0;color:var(--ink2);font-size:17px;line-height:1.4}
.back{display:inline-flex;align-items:center;gap:4px;min-height:44px;color:var(--active);font-weight:600;
font-size:14px;margin:0 0 5px}
.grid{display:grid;grid-template-columns:1fr;gap:16px}
@media (min-width:768px){.grid{grid-template-columns:1fr 1fr}.wide{grid-column:1/-1}}
.card{background:var(--surface);border:1px solid var(--border);border-radius:16px;
padding:20px;min-width:0}
@media (max-width:480px){.card{padding:16px}}
.card h3{font-size:16px;letter-spacing:-.01em;color:var(--ink);
margin:0 0 5px;font-weight:680;line-height:1.28}
.card-link{display:flex;flex-wrap:wrap;align-items:baseline;column-gap:8px}
.card-link .chev{margin-left:auto}
.sub{color:var(--ink2);font-size:13px;line-height:1.45;margin:0 0 12px}
.say{font-size:22px;line-height:1.25;font-weight:600;letter-spacing:-.01em;margin:8px 0 4px}
.big{font-size:48px;line-height:1.05;font-weight:700;letter-spacing:-.02em;margin:8px 0 4px}
.big small{font-size:.45em;font-weight:500;color:var(--ink2);margin-left:2px}
.empty{color:var(--muted);font-size:13px;margin:12px 0}
.hero{padding:16px 12px}
.hero-note{font-size:12px;color:var(--ink2);text-align:center;margin:9px 0 0}
.dials{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;max-width:640px;margin:0 auto}
.dial{display:flex;flex-direction:column;align-items:center;text-align:center;gap:2px}
.dial svg{width:100%;max-width:90px}
.dial-track{fill:none;stroke:var(--grid);stroke-linecap:round}
.dial-val{fill:none;stroke-linecap:round}
.dial-val.good{stroke:var(--good)}.dial-val.warn{stroke:var(--warn)}
.dial-val.bad{stroke:var(--bad)}.dial-val.s1{stroke:var(--s1)}.dial-val.s2{stroke:var(--s2)}
.dial-val.muted{stroke:var(--muted)}
.dial-num{font-size:28px;font-weight:700;letter-spacing:-.02em;fill:var(--ink);
text-anchor:middle}
.dial-label{font-size:15px;font-weight:600}.dial-sub{font-size:12px;color:var(--ink2)}
.pill{display:inline-flex;align-items:center;gap:8px;background:var(--page);border-radius:999px;
padding:8px 14px;font-size:13px;margin:12px 0 0}
.chip{display:inline-block;margin-top:12px;font-size:12px;color:var(--muted);
border:1px solid var(--border);border-radius:999px;padding:4px 10px}
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
.tiles{display:grid;gap:0;padding:4px 20px}
.tile{display:grid;grid-template-columns:1fr auto;align-items:center;padding:14px 0;
border-top:1px solid var(--grid)}
.tile:first-child{border-top:0}.tile b{font-weight:600}
.tile span{grid-column:1;font-size:13px;color:var(--ink2)}
.tile .ic{grid-row:1/3;grid-column:2;color:var(--muted)}
.chart,.gauge{display:block;width:100%;height:auto;overflow:visible}
.chart-interaction{margin:10px 0 0}
[data-ready] .chart{touch-action:pan-y pinch-zoom;cursor:crosshair;user-select:none}
.chart-readout{display:none;color:var(--ink2);border-radius:10px;padding:8px 12px;min-height:72px;
font-size:13px;line-height:1.35}
[data-ready] .chart-readout{display:flex;flex-direction:column;justify-content:center}
.chart-readout.selected{background:var(--accent);color:var(--ink)}
.chart-readout strong{color:var(--active);font-size:13px;font-weight:650}
.chart-readout span{overflow-wrap:anywhere;font-variant-numeric:tabular-nums}
.chart-cursor{visibility:hidden;pointer-events:none}
.chart-cursor.visible{visibility:visible}
.chart-cursor line{stroke:var(--cursor);stroke-width:.9;stroke-dasharray:3 3;vector-effect:non-scaling-stroke}
.chart-cursor circle{fill:var(--surface);stroke:var(--active);stroke-width:1.6}
.chart-note{font-size:12px;color:var(--muted);margin:3px 0 0}
.source-link{text-decoration:underline;color:var(--active)}
.grid line.grid,.chart .grid{stroke:var(--grid);stroke-width:1}
.chart .axis,.chart .zero{stroke:var(--axis);stroke-width:1;fill:none}
.chart .ref{stroke:var(--ink2);stroke-width:1;stroke-dasharray:3 3}
.tick{font-size:11px;fill:var(--ink2);font-variant-numeric:tabular-nums}
.axis-label{font-size:12px;fill:var(--ink);font-weight:640}
.ln{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.ln.s1{stroke:var(--s1)}.ln.s2{stroke:var(--s2)}
.dot.s1{fill:var(--s1);stroke:var(--surface);stroke-width:2}
.hit{fill:transparent}.pt{fill:var(--s1);fill-opacity:.8}
.fit{stroke:var(--s2);stroke-width:2;stroke-linecap:round}.band{fill:var(--band)}
.vo2-range{stroke:var(--axis);stroke-width:4}.vo2-middle{stroke:var(--s1);stroke-width:8}
.vo2-garmin{fill:var(--muted);stroke:var(--surface);stroke-width:2}
.vo2-effective{fill:var(--surface);stroke:var(--s1);stroke-width:2}
.bar.s1{fill:var(--s1)}.bar.good{fill:var(--good)}.bar.warn{fill:var(--warn)}
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
.lg{display:none}@media (min-width:768px){.wide .sm{display:none}.wide .lg{display:block}}
.form-row{padding:12px 0;border-top:1px solid var(--grid)}.form-row:first-of-type{border-top:0}
.fr-head{display:flex;justify-content:space-between;font-size:15px}
.fr-head b{font-variant-numeric:tabular-nums}
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
.finding-detail{display:block;color:var(--ink2);font-size:13px;margin-top:3px}
.finding:hover strong{text-decoration:underline}
footer{margin-top:48px;font-size:12px;color:var(--muted);line-height:1.6}
@media print{.top,.mast,.back,.chart-readout{display:none!important}.page{display:block!important;break-after:page}}
"""


def render(d: dict[str, Any]) -> str:
    links = (
        ("today", "Today"), ("sleep", "Sleep"), ("recovery", "Recovery"),
        ("training", "Training"), ("running", "Running"), ("body", "Body"),
        ("patterns", "Patterns"))
    if d.get("available") is False:
        pages = [_page(pid, title, "Your dashboard is waiting for data.",
                       _card("No data yet", f'<p>{_e(d["reason"])}</p>')) for pid, title in links]
        freshness = "No Garmin measurements are available yet."
    else:
        pages = [page_today(d), page_sleep(d), page_recovery(d), page_training(d),
                 page_running(d), *(page for r in d["runs"]
                                    for page in (page_run(r), page_run_pacing(r))), page_body(d), page_months(d),
                 page_patterns(d)]
        freshness = f'Data through {_e(d["end"])} from your own Garmin records.'
    nav = "".join(f'<a href="#{p}">{t}</a>' for p, t in links)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta http-equiv="Content-Security-Policy" content="{_e(CONTENT_POLICY)}">'
        '<meta name="viewport" '
        'content="width=device-width,initial-scale=1,viewport-fit=cover"><title>Garmin Health'
        f'</title><style>{CSS}</style></head><body><main class="wrap">'
        '<header class="mast"><b>Garmin Health</b><div class="theme" role="group" aria-label="Appearance">'
        '<button type="button" data-theme-choice="light" aria-pressed="true">Light</button>'
        '<button type="button" data-theme-choice="dark" aria-pressed="false">Dark</button>'
        '</div></header><p class="sr-only" id="chart-help">Use arrow keys to explore chart values. '
        'Home and End move to the first and last readings. Escape clears the selection.</p>'
        '<nav class="top" '
        f'aria-label="Dashboard pages">{nav}</nav>{"".join(pages)}<footer>{freshness} '
        'Our scores are estimates; Garmin values shown in grey for comparison. Not '
        f'medical advice.</footer></main><script>{SCRIPT}</script></body></html>')


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


def build(conn: sqlite3.Connection, out_dir: Path | None = None) -> Path:
    from garmin_mcp.config import data_dir

    out_dir = out_dir or data_dir() / "dashboard"
    out_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = out_dir / "index.html"
    content = render(collect(conn))
    _atomic_write(path, content)
    icloud = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs"
    if icloud.is_dir():
        try:
            (icloud / "Garmin").mkdir(mode=0o700, exist_ok=True)
            _atomic_write(icloud / "Garmin" / "dashboard.html", content)
        except OSError:
            warnings.warn("iCloud copy failed; the local dashboard is available.",
                          RuntimeWarning, stacklevel=2)
    return path


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
