"""Summarize Mac archive and local model acceptance without exporting individual records."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from contextlib import closing
from datetime import date
from pathlib import Path

from garmin_mcp import archive_audit, baseline, narrator
from garmin_mcp.normalize import daily_from_summary
from garmin_mcp.verify import replay_dashboard


def _pulse_check(conn, day, expected):
    text = day.isoformat()
    row = conn.execute("SELECT resting_hr FROM daily WHERE day=?", (text,)).fetchone()
    value = row[0] if row else None
    datasets = ("pa_daily_summary", "user_summary", "ex_daily_summary")
    sources = {}
    for dataset, payload in conn.execute(
        "SELECT dataset,payload FROM raw_daily WHERE day=? AND dataset IN (?,?,?) "
        "UNION ALL SELECT dataset,payload FROM raw_range WHERE start_day<=? AND end_day>=? "
        "AND dataset IN (?,?,?)", (text, *datasets, text, text, *datasets)
    ):
        try:
            for stamp, readings in daily_from_summary(json.loads(payload), exported=dataset == "ex_daily_summary"):
                reading = readings.get("resting_hr")
                if stamp == text and reading is not None:
                    sources.setdefault(dataset, set()).add(reading)
        except (TypeError, ValueError):
            continue
    return {"normalized_available": value is not None,
            "normalized_matches_expected": value == expected,
            "dated_sources_checked": sorted(sources),
            "dated_sources_matching": sorted(source for source, readings in sources.items() if readings == {expected}),
            "dated_sources_disagree": len(set().union(*sources.values())) > 1}


def _archive_coverage(conn):
    latest = conn.execute("SELECT max(day) FROM daily").fetchone()[0]
    if not latest:
        return {"recorded_daily_months": 0, "expected_months": 36, "signal_days": {}}
    end = date.fromisoformat(latest)
    first_month = end.year * 12 + end.month - 36
    first = date(first_month // 12, first_month % 12 + 1, 1).isoformat()
    months = conn.execute(
        "SELECT count(DISTINCT substr(day,1,7)) FROM daily WHERE day BETWEEN ? AND ?", (first, latest)
    ).fetchone()[0]
    _, signals = baseline.collect(conn, latest)
    keys = ("resting_hr", "sleep_h", "stress_avg", "body_battery_max")
    return {"recorded_daily_months": months, "expected_months": 36,
            "signal_days": {key: sum(day >= first for day in signals[key]) for key in keys}}


def _ollama_check(conn):
    state = narrator.settings(conn)
    model = state["model"]
    checks = {"enabled": state.get("enabled") is True, "uses_default_model": model == narrator.DEFAULT_MODEL,
              "thinking_enabled": state.get("thinking") is True}
    deadline = time.monotonic() + 5
    try:
        if not narrator._cloud_disabled(deadline):
            return {**checks, "service": "cloud_disabled_not_verified"}
        tags = narrator._request("GET", "/api/tags", deadline).get("models", [])
        tag = model if ":" in model else model + ":latest"
        if not isinstance(tags, list) or not any(isinstance(row, dict) and row.get("name") == tag for row in tags):
            return {**checks, "service": "local_model_not_installed"}
        profile = narrator._model_profile(model, deadline)
    except (narrator.OllamaUnavailable, TimeoutError):
        return {**checks, "service": "local_api_unavailable"}
    return {**checks, "service": "ready" if profile["text_generation"] else "text_generation_unsupported",
            "supports_thinking": profile["thinking"]}


def report(path, day, expected=44, *, replay=False):
    """Report match flags, aggregate counts and loopback availability, with no source paths."""
    if not path.is_file():
        return {"archive_available": False, "reason": "No local archive was found."}
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            result = {"archive_available": True, "pulse": _pulse_check(conn, day, expected),
                      "recent_36_calendar_months": _archive_coverage(conn), "ollama": _ollama_check(conn)}
    except (sqlite3.Error, ValueError, TypeError, KeyError, OverflowError):
        return {"archive_available": False, "reason": "Could not read the expected archive schema."}
    inventory = archive_audit.audit(path)
    result["archive_audit_passed"] = inventory.get("ok", False)
    if "fit_references" in inventory:
        result["fit_references"] = inventory["fit_references"]
        result["usable_intraday_days"] = {
            key: stats["usable_days"] for key, stats in inventory["wellness_timelines"].items()
            if isinstance(stats, dict)
        }
    if replay:
        try:
            result["dashboard_replay"] = replay_dashboard(path)
        except (OSError, sqlite3.Error, ValueError, TypeError, KeyError):
            result["dashboard_replay"] = {"ok": False, "reason": "Could not replay the local archive."}
    return result


def main():
    parser = argparse.ArgumentParser(description="Check the owner's Garmin archive without exporting records.")
    parser.add_argument("--pulse-date", type=date.fromisoformat, required=True, help="Exact date shown in Garmin Connect.")
    parser.add_argument("--expected-bpm", type=int, default=44)
    parser.add_argument("--replay-dashboard", action="store_true", help="Replay up to 36 months on a temporary copy.")
    args = parser.parse_args()
    if not 1 <= args.expected_bpm <= 300:
        parser.error("--expected-bpm must be between 1 and 300.")
    data_dir = os.environ.get("GARMIN_DATA_DIR", "~/.garmin-mcp")
    path = Path(os.environ.get("GARMIN_DB_PATH") or (Path(data_dir) / "garmin.db")).expanduser()
    result = report(path, args.pulse_date, args.expected_bpm, replay=args.replay_dashboard)
    print(json.dumps(result, indent=2))
    if not result["archive_available"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
