"""Opt-in weather and air-quality retrieval for outdoor runs (Open-Meteo, free, no account).

**Off by default.** Turn it on with the MCP tool `weather_retrieval(enable=True)` or
`garmin-mcp-weather --enable`. When on, each scheduled sync fills in hourly conditions for
recent outdoor runs that don't already have any.

What leaves your Mac, per run: the run's start position **rounded to 2 decimals (~1 km)**
and its UTC date range. A final-hour weather query includes the next UTC date for rain.
Only Open-Meteo's public weather and air-quality services are contacted. Turning it off stops all requests;
`--clear` removes what was fetched.

What comes back, per hour that overlaps the run (modelled, not a station measurement):
temperature (°C), relative humidity (%), wind (m/s), precipitation (mm), US AQI.
It is stored in the same format as locally imported condition windows
(`conditions.DETAIL_KIND`), so the run timeline and matched-run comparisons use it.
A run that already has imported windows is never overwritten.

Sources: Open-Meteo forecast API (recent days), historical archive (ERA5-based reanalysis,
older days) and air-quality API (CAMS model). Free for non-commercial use.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import urllib.parse
import urllib.request
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
from typing import Any

from garmin_mcp import conditions, db

OPT_IN_KEY = "weather_opt_in"
SOURCE = conditions.OPEN_METEO_SOURCE
FORECAST = "https://api.open-meteo.com/v1/forecast"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
AIR = "https://air-quality-api.open-meteo.com/v1/air-quality"
RECENT_DAYS = 60          # forecast API covers recent past days; older dates use the archive
LOOKBACK_DAYS = 14        # each sync fills runs from the last two weeks
MAX_RUNS_PER_SYNC = 10
TIMEOUT_S = 20
WEATHER_VARS = {"temperature_2m": "temperature_c", "relative_humidity_2m": "humidity_pct",
                "wind_speed_10m": "wind_m_s", "precipitation": "precipitation_mm"}


def enabled(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (OPT_IN_KEY,)).fetchone()
    return bool(row and row[0] == "1")


def set_enabled(conn: sqlite3.Connection, on: bool) -> dict[str, Any]:
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                 (OPT_IN_KEY, "1" if on else "0"))
    conn.commit()
    return {"weather_retrieval": "on" if on else "off",
            "sends": "rounded start position (~1 km) and requested UTC dates, to Open-Meteo"
            if on else "nothing"}


def _get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}",
                                 headers={"User-Agent": "garmin-mcp-weather"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return json.load(resp)


def _run_window(conn: sqlite3.Connection, aid: int) -> tuple[float, float, datetime,
                                                                 datetime] | None:
    row = conn.execute("SELECT lat, lon FROM fit_records WHERE activity_id=? AND lat IS NOT NULL "
                       "AND lon IS NOT NULL ORDER BY ts LIMIT 1", (aid,)).fetchone()
    span = conn.execute("SELECT min(ts), max(ts) FROM fit_records WHERE activity_id=?",
                        (aid,)).fetchone()
    if not row or not span or not span[0]:
        return None
    lat, lon = row
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    first, last = (conditions._stored_time(t) for t in span)
    return round(lat, 2), round(lon, 2), first, last


def _hourly(payload: dict[str, Any], names: dict[str, str]) -> dict[str, dict[str, float]]:
    hours = (payload.get("hourly") or {})
    times = hours.get("time") or []
    out: dict[str, dict[str, float]] = {}
    for api_name, field in names.items():
        for t, v in zip(times, hours.get(api_name) or [], strict=False):
            if v is not None:
                out.setdefault(t, {})[field] = v
    return out


def fetch_for_run(conn: sqlite3.Connection, aid: int, *, today: date | None = None,
                  get: Any = _get) -> list[dict[str, Any]]:
    """Fetch hourly conditions overlapping one run. Returns the stored windows ([] if none)."""
    where = _run_window(conn, aid)
    if not where:
        return []
    lat, lon, first, last = where
    day0, day1 = first.date().isoformat(), last.date().isoformat()
    today = today or datetime.now(UTC).date()
    common = {"latitude": lat, "longitude": lon, "start_date": day0, "end_date": day1,
              "timezone": "UTC"}
    recent = (today - first.date()).days <= RECENT_DAYS
    # A run in the final UTC hour needs the following midnight's rain reading.
    weather_end = (last + timedelta(hours=1)).date().isoformat()
    weather = get(FORECAST if recent else ARCHIVE,
                  {**common, "end_date": weather_end, "hourly": ",".join(WEATHER_VARS),
                   "wind_speed_unit": "ms"})
    rows = _hourly(weather, {name: field for name, field in WEATHER_VARS.items()
                             if name != "precipitation"})
    # The API stamps the preceding hour's accumulation with its end time.
    for stamp, value in _hourly(weather, {"precipitation": "precipitation_mm"}).items():
        start = datetime.fromisoformat(stamp) - timedelta(hours=1)
        rows.setdefault(start.isoformat(timespec="minutes"), {}).update(value)
    try:
        air = get(AIR, {**common, "hourly": "us_aqi"})
        for t, v in _hourly(air, {"us_aqi": "aqi"}).items():
            rows.setdefault(t, {}).update(v)
    except OSError:
        pass  # air quality is optional; weather alone is still useful
    windows = []
    for t, values in sorted(rows.items()):
        start = datetime.fromisoformat(t).replace(tzinfo=UTC)
        end = start + timedelta(hours=1)
        if end <= first or start > last:
            continue
        window: dict[str, Any] = {"start_utc": start.isoformat(), "end_utc": end.isoformat(),
                                  "source": SOURCE, "kind": "model"}
        for field, value in values.items():
            limits = conditions.FIELDS[field]
            ok = conditions._value(value, limits)
            if ok is None:
                continue
            if field == "aqi":
                ok = float(round(ok))
                window["aqi_standard"] = "US-EPA"
            if field == "precipitation_mm":
                window["precipitation_alignment"] = conditions.ALIGNED_RAIN
            window[field] = ok
        if len(window) > 4:
            windows.append(window)
    if windows:
        db.put_activity_detail(conn, aid, conditions.DETAIL_KIND, windows)
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('dashboard_rebuild_pending','1')")
        conn.commit()
    return windows


def fill_recent(conn: sqlite3.Connection, *, today: date | None = None,
                get: Any = _get) -> dict[str, Any]:
    """Called by sync. Does nothing unless the owner opted in."""
    if not enabled(conn):
        return {"skipped": "weather retrieval is off (opt-in)"}
    from garmin_mcp.loads import RUN_TYPES

    today = today or datetime.now(UTC).date()
    since = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
    marks = ",".join("?" * len(RUN_TYPES))
    todo = [aid for (aid,) in conn.execute(
        f"SELECT a.activity_id FROM activities a WHERE a.type IN ({marks}) AND a.fit_parsed=1 "
        "AND substr(a.start_time_local,1,10) >= ? AND NOT EXISTS (SELECT 1 FROM "
        "activity_details d WHERE d.activity_id=a.activity_id AND d.kind=?) "
        "ORDER BY a.start_time_local DESC LIMIT ?",
        (*RUN_TYPES, since, conditions.DETAIL_KIND, MAX_RUNS_PER_SYNC))]
    filled, errors = 0, []
    for aid in todo:
        try:
            filled += bool(fetch_for_run(conn, aid, today=today, get=get))
        except (OSError, ValueError) as exc:
            errors.append(f"{aid}: {type(exc).__name__}")
    return {"runs_checked": len(todo), "runs_filled": filled, "errors": errors[:5]}


def clear(conn: sqlite3.Connection) -> int:
    """Remove every window this module fetched (imported windows from other sources stay)."""
    removed = 0
    for aid, payload in conn.execute("SELECT activity_id, payload FROM activity_details "
                                     "WHERE kind=?", (conditions.DETAIL_KIND,)).fetchall():
        windows = json.loads(payload or "[]")
        if windows and all(w.get("source") == SOURCE for w in windows):
            conn.execute("DELETE FROM activity_details WHERE activity_id=? AND kind=?",
                         (aid, conditions.DETAIL_KIND))
            removed += 1
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('dashboard_rebuild_pending','1')")
    conn.commit()
    return removed


def main() -> None:
    from garmin_mcp.config import db_path

    parser = argparse.ArgumentParser(description="Opt-in Open-Meteo conditions for runs.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--enable", action="store_true", help="turn retrieval on")
    group.add_argument("--disable", action="store_true", help="turn retrieval off")
    group.add_argument("--fetch", action="store_true", help="fill recent runs now (if on)")
    group.add_argument("--clear", action="store_true", help="remove fetched conditions")
    group.add_argument("--status", action="store_true")
    args = parser.parse_args()
    with closing(db.connect(db_path())) as conn:
        if args.enable or args.disable:
            print(json.dumps(set_enabled(conn, args.enable)))
        elif args.fetch:
            print(json.dumps(fill_recent(conn)))
        elif args.clear:
            print(f"Removed fetched conditions from {clear(conn)} run(s).")
        else:
            print("on" if enabled(conn) else "off")


if __name__ == "__main__":
    main()
