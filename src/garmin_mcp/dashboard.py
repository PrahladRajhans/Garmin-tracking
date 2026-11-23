"""Personal dashboard v2: multi-page, one self-contained HTML file, no JavaScript, no CDN.

Pages are sections addressed by links (#today, #sleep, #run-<id>, ...). CSS `:target` shows one
at a time, so it works offline, from iCloud Drive, or as a private Artifact. Charts are inline SVG
drawn here; every mark has a native tooltip (<title>). Built from the same functions as the MCP
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
from pathlib import Path
from typing import Any

from garmin_mcp import coaching, engine, health, insights, loads, norms, recovery, running, scores

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
        "history": scores.history(conn, end, 14),
        "brief": insights.daily_brief(conn, end),
        "ranges": engine.personal_ranges(conn, end)["metrics"],
        "night": health.sleep_breakdown(conn, night) if night else None,
        "sleep": conn.execute("SELECT day, sleep_s/3600.0, sleep_start FROM sleep WHERE day "
                              "BETWEEN ? AND ? AND sleep_s >= 3*3600 ORDER BY day",
                              (lo(30), end)).fetchall(),
        "hrv": recovery.recovery_trend(conn, end, 60)["days"],
        "rhr": conn.execute("SELECT day, resting_hr FROM daily WHERE day BETWEEN ? AND ? AND "
                            "resting_hr IS NOT NULL ORDER BY day", (lo(60), end)).fetchall(),
        "fitness": conn.execute("SELECT day, ctl, atl FROM fitness WHERE day BETWEEN ? AND ? "
                                "ORDER BY day", (lo(120), end)).fetchall()
        if _has(conn, "fitness") else [],
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
        "feed": engine.insight_feed(conn, end)["insights"],
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


def _weekly_load(conn: sqlite3.Connection, end: str, weeks: int = 12) -> list[tuple[str, float]]:
    if not _has(conn, "fitness"):
        return []
    e = date.fromisoformat(end)
    monday = e - timedelta(days=e.weekday())
    out = []
    for i in range(weeks - 1, -1, -1):
        a = monday - timedelta(weeks=i)
        v = conn.execute("SELECT COALESCE(SUM(load),0) FROM fitness WHERE day BETWEEN ? AND ?",
                         (a.isoformat(), (a + timedelta(days=6)).isoformat())).fetchone()[0]
        out.append((a.isoformat(), round(v)))
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


def _chart_table(headers: list[str], rows: list[tuple], caption: str) -> str:
    head = "".join(f'<th scope="col">{_e(h)}</th>' for h in headers)
    body = "".join(f'<tr><th scope="row">{_e(row[0])}</th>'
                   + "".join(f'<td>{_e(v)}</td>' for v in row[1:]) + '</tr>' for row in rows)
    return ('<details class="chart-values"><summary>View values</summary>'
            '<div class="table-wrap" tabindex="0" role="region" aria-label="Chart data">'
            f'<table><caption>{_e(caption)}</caption><thead><tr>{head}</tr></thead>'
            f'<tbody>{body}</tbody></table></div></details>')


def line_chart(points: list[tuple[str, float]], unit: str = "", band: tuple | None = None,
               band_series: list[tuple[float, float]] | None = None, h: int = 150,
               nd: int = 0, cls: str = "s1", w: int = W, fmt: Any = None) -> str:
    """One series, one axis. band = fixed (lo, hi); band_series = per-point (lo, hi)."""
    valid = [i for i, (_, v) in enumerate(points) if isinstance(v, (int, float)) and math.isfinite(v)]
    pts = [points[i] for i in valid]
    if band_series and len(band_series) == len(points):
        band_series = [band_series[i] for i in valid]
    days = None
    try:
        days = [date.fromisoformat(d[:10]).toordinal() for d, _ in pts]
        order = sorted(range(len(pts)), key=lambda i: days[i])
        pts = [pts[i] for i in order]
        days = [days[i] for i in order]
        if band_series and len(band_series) == len(order):
            band_series = [band_series[i] for i in order]
    except ValueError:
        days = None  # split/km labels are categorical, rather than dates
    headers = ["Date / label", f"Value{unit}"]
    values = [(d, fmt(v) if fmt else _f(v, nd)) for d, v in pts]
    if band or (band_series and len(band_series) == len(pts)):
        headers += [f"Normal low{unit}", f"Normal high{unit}"]
        bounds_list = band_series if band_series and len(band_series) == len(pts) else [band] * len(pts)
        values = [(*row, _f(bounds[0], nd), _f(bounds[1], nd)) if bounds else (*row, "–", "–")
                  for row, bounds in zip(values, bounds_list,
                                         strict=True)]
    table = _chart_table(headers, values, "Recorded trend values")
    if len(pts) < 2:
        return '<p class="empty">Not enough data yet.</p>' + (table if pts else "")
    vals = [v for _, v in pts]
    if band:
        vals += list(band)
    if band_series:
        vals += [x for b in band_series if b for x in b if x is not None]
    y0, y1 = _scale(vals)
    L, R, T, B = 34, 8, 8, 22
    pw, ph = w - L - R, h - T - B
    n = len(pts)

    def X(i: int) -> float:
        if days and days[-1] > days[0]:
            return L + pw * (days[i] - days[0]) / (days[-1] - days[0])
        return L + pw * i / (n - 1)

    def Y(v: float) -> float:
        return T + ph * (1 - (v - y0) / (y1 - y0))

    g = []
    for t in (y0 + (y1 - y0) * k / 2 for k in range(3)):
        g.append(f'<line x1="{L}" x2="{w - R}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" class="grid"/>'
                 f'<text x="{L - 6}" y="{Y(t) + 4:.1f}" class="tick" text-anchor="end">'
                 f'{fmt(t) if fmt else f"{t:.{nd}f}"}</text>')
    if band:
        g.append(f'<rect x="{L}" y="{Y(band[1]):.1f}" width="{pw}" height="'
                 f'{max(0, Y(band[0]) - Y(band[1])):.1f}" class="band"><title>Your normal: '
                 f'{band[0]:.{nd}f}–{band[1]:.{nd}f}{unit}</title></rect>')
    if band_series and len(band_series) == n and all(band_series):
        top = " ".join(f"{X(i):.1f},{Y(b[1]):.1f}" for i, b in enumerate(band_series))
        bot = " ".join(f"{X(i):.1f},{Y(b[0]):.1f}" for i, b in reversed(list(enumerate(
            band_series))))
        g.append(f'<polygon points="{top} {bot}" class="band"><title>Your normal range'
                 f'</title></polygon>')
    path = " ".join(f"{'M' if i == 0 else 'L'}{X(i):.1f},{Y(v):.1f}" for i, (_, v) in
                    enumerate(pts))
    g.append(f'<path d="{path}" class="ln {cls}"/>')
    for i, (d, v) in enumerate(pts):  # invisible hit targets with tooltips
        lab = fmt(v) if fmt else f"{v:.{nd}f}{unit}"
        g.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="7" class="hit"><title>{_e(d)}: '
                 f'{lab}</title></circle>')
    lx, ly = X(n - 1), Y(pts[-1][1])
    g.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="4" class="dot {cls}"/>')
    g.append(f'<text x="{L}" y="{h - 4}" class="tick">{_e(_short(pts[0][0]))}</text>'
             f'<text x="{w - R}" y="{h - 4}" class="tick" text-anchor="end">'
             f'{_e(_short(pts[-1][0]))}</text>')
    return (f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" '
            f'aria-label="Trend{_e(unit)}; exact values in the following table">{"".join(g)}</svg>'
            + table)


def bar_chart(items: list[tuple[str, float]], unit: str = "", ref: float | None = None,
              ref_label: str = "", h: int = 140, nd: int = 0,
              tones: list[str] | None = None, w: int = W) -> str:
    aligned = [(k, v, tones[i] if tones and i < len(tones) else "s1") for i, (k, v) in
               enumerate(items) if isinstance(v, (int, float)) and math.isfinite(v)]
    items = [(k, v) for k, v, _ in aligned]
    tones = [t for _, _, t in aligned]
    if not items:
        return '<p class="empty">Not enough data yet.</p>'
    top = max([v for _, v in items] + ([ref] if ref else [])) * 1.1 or 1
    L, R, T, B = 8, 8, 10, 22
    pw, ph = w - L - R, h - T - B
    n = len(items)
    gap = 2
    bw = (pw - gap * (n - 1)) / n
    g = [f'<line x1="{L}" x2="{w - R}" y1="{T + ph}" y2="{T + ph}" class="axis"/>']
    for i, (k, v) in enumerate(items):
        bh = max(0.0, ph * v / top)
        x, y = L + i * (bw + gap), T + ph - bh
        rr = min(4.0, bw / 2, bh)
        tone = tones[i] if tones else "s1"
        g.append(f'<path d="M{x:.1f},{T + ph} V{y + rr:.1f} Q{x:.1f},{y:.1f} {x + rr:.1f},'
                 f'{y:.1f} H{x + bw - rr:.1f} Q{x + bw:.1f},{y:.1f} {x + bw:.1f},{y + rr:.1f} '
                 f'V{T + ph} Z" class="bar {tone}"><title>{_e(k)}: {v:.{nd}f}{unit}</title>'
                 f'</path>')
    if ref:
        yr = T + ph * (1 - ref / top)
        g.append(f'<line x1="{L}" x2="{w - R}" y1="{yr:.1f}" y2="{yr:.1f}" class="ref"/>'
                 f'<text x="{w - R}" y="{yr - 5:.1f}" class="tick" text-anchor="end">'
                 f'{_e(ref_label)}</text>')
    g.append(f'<text x="{L}" y="{h - 4}" class="tick">{_e(_short(items[0][0]))}</text>'
             f'<text x="{w - R}" y="{h - 4}" class="tick" text-anchor="end">'
             f'{_e(_short(items[-1][0]))}</text>')
    return (f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" '
            f'aria-label="Amounts{_e(unit)}; exact values in the following table">{"".join(g)}</svg>'
            + _chart_table(["Date / label", f"Value{unit}"], [(k, _f(v, nd)) for k, v in items],
                           "Recorded amounts"))


def scatter(points: list[tuple[str, float, float]], xl: str, yl: str, slope: float | None,
            w: int = W, h: int = 200, x_unit: str = "", y_unit: str = "", lag: int = 0) -> str:
    """Baseline-adjusted x vs y (0 = your usual), with the fitted line. One mark per day."""
    if len(points) < 3:
        return '<p class="empty">Not enough data yet.</p>'
    xs, ys = [p[1] for p in points], [p[2] for p in points]
    x0, x1 = _scale(xs, 0.05)
    y0, y1 = _scale(ys, 0.05)
    L, R_, T, B = 34, 8, 8, 30
    pw, ph = w - L - R_, h - T - B

    def X(v: float) -> float:
        return L + pw * (v - x0) / (x1 - x0)

    def Y(v: float) -> float:
        return T + ph * (1 - (v - y0) / (y1 - y0))

    g = []
    if x0 < 0 < x1:
        g.append(f'<line x1="{X(0):.1f}" x2="{X(0):.1f}" y1="{T}" y2="{T + ph}" class="grid"/>')
    if y0 < 0 < y1:
        g.append(f'<line x1="{L}" x2="{w - R_}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" class="grid"/>')
    for d, a, b in points:
        g.append(f'<circle cx="{X(a):.1f}" cy="{Y(b):.1f}" r="3" class="pt"><title>{_e(d)}: '
                 f'{a:+.2f}, {b:+.2f}</title></circle>')
    if slope is not None:
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        g.append(f'<line x1="{X(x0):.1f}" y1="{Y(my + slope * (x0 - mx)):.1f}" x2="{X(x1):.1f}" '
                 f'y2="{Y(my + slope * (x1 - mx)):.1f}" class="fit"/>')
    g.append(f'<text x="{w - R_}" y="{h - 6}" class="tick" text-anchor="end">{_e(xl)} → '
             f'(vs usual)</text><text x="{L}" y="{T + 10}" class="tick">↑ {_e(yl)}</text>')
    return (f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" '
            f'aria-label="Association between {_e(xl)} and {_e(yl)}; values in the following table">'
            f'{"".join(g)}</svg>' + _chart_table(
                ["First date", "Second date", f"{xl} ({x_unit})" if x_unit else xl,
                 f"{yl} ({y_unit})" if y_unit else yl],
                [(d, (date.fromisoformat(d) + timedelta(days=lag)).isoformat() if lag else d,
                  _f(a, 2), _f(b, 2)) for d, a, b in points], "Values compared with your usual"))


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
        + dial(sl.get("pct"), "Sleep", _f(sl.get("pct"), 0, "%"), sleep_sub, "s1", "#sleep")
        + dial(None, "Strain", _f(st.get("value"), 1),
               f"target {tr[0]}–{tr[1]}" if tr[0] is not None else "target unavailable", "s2",
               "#training", frac=(st.get("value") or 0) / 21))
    sug = d["brief"].get("suggestion") or {}
    bt = d["bedtime"]
    today = (f'<p class="say">{_e((sug.get("suggest") or "").capitalize())}.</p>'
             f'<p class="sub">{_e(sug.get("why"))}</p>')
    if bt.get("available"):
        today += (f'<p class="pill">{icon("moon")}<span>Bed by <b>{_e(bt["suggested_bedtime"])}'
                  f'</b> for a usual {_e(bt["usual_wake"])} wake time</span></p>')
    garmin = (f'<span class="chip">Garmin readiness {_f(rec.get("garmin_readiness"))} · '
              f'{_e((rec.get("garmin_level") or "").title())}</span>')
    names = {"hrv_ms": ("Heart rate variability", "ms", 0),
             "resting_hr_bpm": ("Resting heart rate", "bpm", 0),
             "respiration_brpm": ("Breathing rate", "/min", 1),
             "sleep_spo2_pct": ("Blood oxygen in sleep", "%", 0),
             "sleep_hr_bpm": ("Heart rate in sleep", "bpm", 0)}
    rows = []
    for k, (lab, unit, nd) in names.items():
        m = d["ranges"].get(k)
        if not m or m.get("value") is None:
            continue
        rg = m.get("range") or [None, None]
        state = {"in range": "good", "above": "up", "below": "down"}.get(m.get("state"), "")
        note = (f'{m.get("state", "")} · usual {_f(rg[0], nd)}–{_f(rg[1], nd)}'
                if m.get("range") else "Personal range is still calibrating")
        rows.append(_row(lab, f'{_f(m["value"], nd)} <small>{unit}</small>', note, state))
    hist = d["history"]
    week = bar_chart([(h["day"], h["recovery"]) for h in hist], "%", h=110,
                     tones=[TONE.get(h.get("band") or "", "muted") for h in hist])
    tiles = "".join(f'<a class="tile" href="#{p}"><b>{t}</b><span>{s}</span>{icon("chev")}</a>'
                    for p, t, s in (("sleep", "Sleep", "stages, heart-rate dip, bedtimes"),
                                    ("recovery", "Recovery", "HRV and resting HR trends"),
                                    ("training", "Training", "fitness, weekly load"),
                                    ("running", "Running", "every run, form, race times"),
                                    ("body", "Body & long term", "fitness age, month report"),
                                    ("patterns", "Patterns", "what moves together, for you")))
    why = f'<ul class="rows">{"".join(rows)}</ul>' if rows else (
        '<p class="empty">Not enough recent measurements to compare with your personal ranges.</p>')
    body = (f'<section class="card wide hero"><div class="dials">{dials}</div>'
            f'<p class="hero-note">Recovery uses {rec.get("signals_used", 0)} of '
            f'{rec.get("signals_total", 4)} signals. Strain covers recorded workouts.</p></section>'
            + _card("Today", today + garmin)
            + _card("Why", why,
                    "Last night versus your personal range")
            + _card("Recovery, last 14 days", week, "Green ≥ 67 · amber 34–66 · red ≤ 33",
                    href="#recovery")
            + f'<nav class="card tiles">{tiles}</nav>')
    lede = f'Data to {_short(d["end"])}. Tap any dial or card for the detail.'
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
    need = d["scores"]["sleep"].get("need_h") or 8
    durations = both(bar_chart, [(r[0], r[1]) for r in d["sleep"]], " h", ref=need,
                          ref_label=f"need {need:.1f} h", nd=1)
    bed = []
    tz = engine._tz(d['_conn'])
    for day, _, start in d["sleep"]:
        if start:
            loc = datetime.fromisoformat(start).replace(tzinfo=UTC).astimezone(tz)
            bed.append((day, ((loc.hour - 12) % 24) + loc.minute / 60 + 12))  # 25.5 = 01:30
    bedtimes = both(line_chart, bed, "", nd=0, h=120, fmt=_clock) if bed else ""
    score = n.get("overall")
    body = (_card("Last night", f'<div class="big">{_f(score)}<small>/100</small></div>'
                  f'<p class="sub">{_e(n.get("rating") or "")} · {_short(n.get("day", ""))}'
                  f'</p><ul class="rows">{stages}</ul>', "Garmin sleep score and its parts")
            + _card("Heart-rate dip", dip_html or '<p class="empty">Needs all-day heart rate.'
                    '</p>', "How far your heart rate falls from day to night")
            + _card("Sleep, last 30 nights", durations, "Hours asleep against your need",
                    wide=True)
            + _card("Bedtime", bedtimes, "When you fell asleep, local time. Steadier is better.", wide=True))
    debt = d["scores"]["sleep"].get("debt_7d_h")
    return _page("sleep", "Sleep", f"Sleep debt over the last 7 nights: <b>{_f(debt, 1)} h"
                 "</b>.", body)


def page_recovery(d: dict[str, Any]) -> str:
    hv = [(x["day"], x.get("hrv_7d_ms")) for x in d["hrv"]]
    bands = [tuple(x["hrv_band_ms"]) if x.get("hrv_band_ms") else None for x in d["hrv"]]
    hv_ok = [(p, b) for p, b in zip(hv, bands, strict=True) if p[1] is not None]
    hrv_chart = both(line_chart, [p for p, _ in hv_ok], " ms",
                           band_series=[b for _, b in hv_ok], h=160)
    rhr = both(line_chart, list(d["rhr"]), " bpm", h=140)
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


def page_training(d: dict[str, Any]) -> str:
    fit = both(line_chart, [(r[0], r[1]) for r in d["fitness"]], h=160, nd=1)
    wl = both(bar_chart, d["weekly_load"], " load", h=140)
    body = (_card("Training load trend", fit, "42-day smoothed load. Tracks training exposure, "
                  "not a direct fitness test.", wide=True)
            + _card("Load per week", wl, "Sum of daily training load, Monday to Sunday",
                    wide=True))
    st = d["brief"].get("garmin_training_status")
    return _page("training", "Training", f"Garmin training status: <b>{_e((st or '–').title())}"
                 "</b>.", body)


def _run_label(r: dict[str, Any]) -> str:
    return f'{_short(r["date"])} · {r["km"]:.1f} km · {r["pace"]}/km'


def page_running(d: dict[str, Any]) -> str:
    runs = d["runs"]
    lst = "".join(f'<a class="tile" href="#run-{r["activity_id"]}"><b>{_e(_run_label(r))}</b>'
                  f'<span>avg HR {_f(r.get("avg_hr"))} · cadence '
                  f'{_f((r["form"].get("cadence_spm") or {}).get("value"))}</span>'
                  f'{icon("chev")}</a>' for r in runs)
    pr = d["predictions"].get("predictions") or {}
    trows = "".join(f'<tr><td>{ {"half": "Half", "marathon": "Marathon"}.get(k, k.upper())}</td><td>'
                    f'{_e(v.get("effective_vo2max"))}</td><td>{_e(v.get("best_effort_vdot"))}'
                    f'</td><td class="g">{_e(v.get("garmin"))}</td></tr>' for k, v in pr.items())
    table = (f'<div class="table-wrap" tabindex="0" role="region" aria-label="Race time estimates">'
             f'<table class="race-times"><caption>Estimates, not targets; sparse running history '
             f'and untested maximum heart rate increase uncertainty.</caption>'
             f'<thead><tr><th scope="col">Distance</th><th scope="col">From fitness</th>'
             f'<th scope="col">From your best run</th><th scope="col" class="g">Garmin</th>'
             f'</tr></thead><tbody>{trows}</tbody></table></div>')
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
                  f'<p class="sub">You average {ms["weekly_km_avg"]} km a week; at your fitness '
                  f'a marathon needs ~{ms["weekly_km_target"]:.0f} km a week and long runs '
                  f'up to {ms["long_run_target_km"]:.0f} km.</p>')
    fs = d["form"]["series"]
    cad = both(line_chart, [(s["date"], s["cadence_spm"]) for s in fs], " spm", h=120)
    body = (f'<nav class="card tiles wide">{lst or "<p class=empty>No runs with detail yet.</p>"}'
            f'</nav>'
            + _card("Aerobic fitness on your usual run", _tests(d["tests"]),
                    "Same-distance steady runs: speed per heartbeat over time", wide=True)
            + _card("Marathon shape", mshape, "Endurance readiness (Runalyze method)")
            + _card("Race time estimates", table, "Three methods side by side; Garmin in grey")
            + _card("Cadence over your runs", cad, "Steps per minute. Rises with pace, so "
                    "compare runs on each run's page.", wide=True))
    return _page("running", "Running", "Tap a run for a coach-style breakdown.", body)


def _tests(t: dict[str, Any]) -> str:
    if not t.get("runs"):
        return f'<p class="empty">{_e(t.get("reason"))}</p>'
    chart = both(line_chart, [(r["date"], r["ef"]) for r in t["runs"]], "", nd=2, h=130)
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
    chart = both(line_chart, splits, " elapsed/km", fmt=loads._hms, h=145)
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

    marks = "".join(f'<circle cx="{x(value):.1f}" cy="{22 if cls == "vo2-garmin" else 46}" '
                    f'r="5" class="{cls}"><title>{name}: {value:.1f} mL/kg/min</title></circle>'
                    for name, value, cls in markers)
    ticks = "".join(f'<text x="{x(v[p]):.1f}" y="72" class="tick" text-anchor="middle">'
                    f'{p}th · {v[p]:.1f}</text>' for p in (5, 50, 95))
    svg = (f'<svg class="chart" viewBox="0 0 340 82" role="img" aria-label="VO2max estimates '
           f'and FRIEND reference in mL/kg/min"><title>FRIEND population reference</title>'
           f'<line x1="{x(v[5]):.1f}" x2="{x(v[95]):.1f}" y1="34" y2="34" class="vo2-range"/>'
           f'<line x1="{x(v[25]):.1f}" x2="{x(v[75]):.1f}" y1="34" y2="34" class="vo2-middle"/>'
           f'{marks}{ticks}</svg>')
    rows = "".join(f'<tr><th scope="row">{p}th</th><td>{value:.1f}</td></tr>'
                   for p, value in v.items())
    return (f'{svg}<p class="sub">Filled grey dot: Garmin · hollow blue dot: effective estimate. '
            f'Line: 5th–95th; thick centre: 25th–75th reference percentiles. mL/kg/min.</p>'
            f'<ul class="rows">{facts}</ul><p class="sub">{_e(caveat)}</p>'
            f'<details><summary>Reference values and source</summary><p class="sub">'
            f'{_e(r["sex"].title())}, age {_e(r["age_group"])}. {_e(r["cohort"])}</p>'
            f'<table><caption>FRIEND 2015 reference in mL/kg/min</caption><thead><tr>'
            f'<th scope="col">Percentile</th><th scope="col">VO₂max</th></tr></thead>'
            f'<tbody>{rows}</tbody></table><p><a href="{norms.SOURCE}" rel="noreferrer">'
            f'Kaminsky et al. 2015, Table 3</a></p></details>')


def page_patterns(d: dict[str, Any]) -> str:
    lab = engine.LABELS
    explore = d["explore"]
    cards = ""
    for p in explore["pairs"]:
        x, y = lab.get(p["x"], p["x"]), lab.get(p["y"], p["y"])
        when = "same day" if p["lag_days"] == 0 else "next day"
        trend = p.get("slope") if p["notable"] else None
        status = "Passed evidence rule" if p["notable"] else "Weak evidence"
        plot = both(scatter, p["points"], x, y, trend, x_unit=engine.UNITS[p["x"]],
                    y_unit=engine.UNITS[p["y"]], lag=p["lag_days"])
        body = (f'<p class="sub"><strong>{status}</strong> · {p["n"]} paired days</p>{plot}'
                f'<details><summary>How this was assessed</summary><p class="sub">'
                f'{_e(p["statement"]) if p["notable"] else "This pair did not pass the evidence rule after checking multiple pairs."}'
                f'</p><p class="sub">Correlation {p["r"]:+.2f} · 95% interval '
                f'{p["r_ci95"][0]:+.2f} to {p["r_ci95"][1]:+.2f} · adjusted q {_f(p["q_bh"], 3)}.</p>'
                f'</details>')
        cards += _card(f"{x} & {y} ({when})", body, wide=True)
    lede = (f'{explore["eligible"]} of {explore["tested"]} pairs could be assessed. '
            f'{explore["notable"]} passed the evidence rule. Each dot compares two '
            'measurements with your recent averages. Other factors can explain an association.')
    return _page("patterns", "Patterns", lede, cards or _card(
        "Patterns", '<p class="empty">Not enough data yet.</p>'))


# =============================================================================== render
CSS = """
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;
--muted:#6d6b66;--grid:#e1e0d9;--axis:#c3c2b7;--border:rgba(11,11,11,.10);--s1:#2a78d6;
--s2:#eb6834;--good:#0ca30c;--warn:#fab219;--serious:#ec835a;--bad:#d03b3b;--purple:#6250d6;
--band:rgba(42,120,214,.12);--goodtext:#006300}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){color-scheme:dark;
--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#a7a39a;--grid:#2c2c2a;--axis:#383835;
--border:rgba(255,255,255,.10);--s1:#3987e5;--s2:#d95926;--purple:#9085e9;
--band:rgba(57,135,229,.18);--goodtext:#0ca30c}}
:root[data-theme=dark]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;
--ink2:#c3c2b7;--muted:#a7a39a;--grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);--s1:#3987e5;
--s2:#d95926;--purple:#9085e9;--band:rgba(57,135,229,.18);--goodtext:#0ca30c}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,
"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
a:focus-visible,summary:focus-visible,.table-wrap:focus-visible{outline:3px solid var(--s1);outline-offset:3px}
.wrap{max-width:1080px;margin:0 auto;padding:16px 16px 48px}
.top{display:flex;gap:4px;overflow-x:auto;padding:4px;margin:0 -4px 24px;scrollbar-width:none}
.top a{flex:none;display:inline-flex;align-items:center;min-height:44px;padding:8px 14px;border-radius:999px;font-size:13px;font-weight:600;
color:var(--ink2)}
.top a:hover{background:var(--surface)}
@media(max-width:520px){
.top{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));overflow:visible}
.top a{justify-content:center;padding:4px;font-size:12px}
}
.page{display:none}#today{display:block}body:has(.page:target) #today:not(:target){display:none}
.page:target{display:block}
.ph{margin:0 0 24px}.ph h2{font-size:34px;line-height:1.1;letter-spacing:-.02em;margin:0 0 8px}
.lede{margin:0;color:var(--ink2);font-size:17px;line-height:1.4}
.back{display:inline-flex;align-items:center;gap:4px;color:var(--ink);font-weight:600;
font-size:15px;margin:0 0 16px}
.grid{display:grid;grid-template-columns:1fr;gap:16px}
@media (min-width:768px){.grid{grid-template-columns:1fr 1fr}.wide{grid-column:1/-1}}
.card{background:var(--surface);border:1px solid var(--border);border-radius:16px;
padding:20px;min-width:0}
@media (max-width:480px){.card{padding:16px}}
.card h3{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);
margin:0 0 4px;font-weight:600}
.card-link{display:flex;flex-wrap:wrap;align-items:baseline;column-gap:8px}
.card-link .chev{margin-left:auto}
.sub{color:var(--ink2);font-size:13px;line-height:1.45;margin:0 0 12px}
.say{font-size:22px;line-height:1.25;font-weight:600;letter-spacing:-.01em;margin:8px 0 4px}
.big{font-size:48px;line-height:1.05;font-weight:700;letter-spacing:-.02em;margin:8px 0 4px}
.big small{font-size:.45em;font-weight:500;color:var(--ink2);margin-left:2px}
.empty{color:var(--muted);font-size:13px;margin:12px 0}
.hero{padding:24px 12px}
.hero-note{font-size:12px;color:var(--ink2);text-align:center;margin:16px 0 0}
.dials{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;max-width:640px;margin:0 auto}
.dial{display:flex;flex-direction:column;align-items:center;text-align:center;gap:2px}
.dial svg{width:100%;max-width:150px}
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
.grid line.grid,.chart .grid{stroke:var(--grid);stroke-width:1}
.chart .axis{stroke:var(--axis);stroke-width:1}
.chart .ref{stroke:var(--ink2);stroke-width:1;stroke-dasharray:3 3}
.tick{font-size:10px;fill:var(--muted);font-variant-numeric:tabular-nums}
.ln{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.ln.s1{stroke:var(--s1)}.ln.s2{stroke:var(--s2)}
.dot.s1{fill:var(--s1);stroke:var(--surface);stroke-width:2}
.hit{fill:transparent}.pt{fill:var(--s1);fill-opacity:.45}
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
.race-times{min-width:310px}.race-times td{white-space:nowrap}
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
footer{margin-top:48px;font-size:12px;color:var(--muted);line-height:1.6}
@media print{.top,.back{display:none}.page{display:block!important;break-after:page}}
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
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
        'content="width=device-width,initial-scale=1,viewport-fit=cover"><title>Garmin Health'
        f'</title><style>{CSS}</style></head><body><main class="wrap"><nav class="top" '
        f'aria-label="Dashboard pages">{nav}</nav>{"".join(pages)}<footer>{freshness} '
        'Our scores are estimates; Garmin values shown in grey for comparison. Not '
        'medical advice.</footer></main></body></html>')


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
