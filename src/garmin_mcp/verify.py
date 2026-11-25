"""Data-quality checks: run after any mapping change (and periodically) to catch unit or
field-mapping mistakes before they reach an analysis.

1. Cross-source agreement: where two sources hold the same day, each mapped field should
   match (tolerance: 1 unit or 1%). Known small upstream differences are listed in
   KNOWN_DIFFS and reported but not failed.
2. Plausible ranges: every tidy column must fall in a physical range for its unit.
3. Fill rates: how many days each column actually has (an empty column usually means an
   unmapped field, as happened with export Body Battery/SpO2 before v0.3.0).
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from garmin_mcp import normalize as N

# (table, column) -> (min, max, unit)
RANGES: dict[tuple[str, str], tuple[float, float, str]] = {
    ("daily", "steps"): (0, 100_000, "steps"),
    ("daily", "distance_m"): (0, 100_000, "m"),
    ("daily", "resting_hr"): (25, 120, "bpm"),
    ("daily", "min_hr"): (20, 120, "bpm"),
    ("daily", "max_hr"): (40, 230, "bpm"),
    ("daily", "kcal_total"): (500, 10_000, "kcal"),
    ("daily", "stress_avg"): (0, 100, "Garmin 0-100"),
    ("daily", "stress_max"): (0, 100, "Garmin 0-100"),
    ("daily", "body_battery_min"): (0, 100, "Garmin 0-100"),
    ("daily", "body_battery_max"): (0, 100, "Garmin 0-100"),
    ("daily", "respiration_avg"): (4, 40, "breaths/min"),
    ("daily", "spo2_avg"): (70, 100, "%"),
    ("daily", "floors_up_m"): (0, 3_000, "m"),
    ("sleep", "sleep_s"): (0, 16 * 3600, "s"),
    ("sleep", "score"): (0, 100, "Garmin 0-100"),
    ("sleep", "avg_spo2"): (70, 100, "%"),
    ("sleep", "avg_respiration"): (4, 40, "breaths/min"),
    ("sleep", "avg_hr"): (25, 120, "bpm"),
    ("sleep", "sleep_need_min"): (180, 900, "min"),
    ("hrv", "last_night_avg"): (5, 250, "ms"),
    ("hrv", "weekly_avg"): (5, 250, "ms"),
    ("health_status", "hrv"): (5, 250, "ms"),
    ("health_status", "rhr"): (25, 120, "bpm"),
    ("health_status", "respiration"): (4, 40, "breaths/min"),
    ("readiness", "score"): (0, 100, "Garmin 0-100"),
    ("readiness", "recovery_time_min"): (0, 96 * 60, "min (Garmin max 96 h)"),
    ("training", "vo2max_run"): (15, 95, "ml/kg/min"),
    ("training", "acute_load"): (0, 5_000, "Garmin load"),
    ("race_predictions", "t5k_s"): (600, 3_600, "s"),
    ("race_predictions", "marathon_s"): (6_000, 30_000, "s"),
    ("fitness_age", "fitness_age"): (10, 100, "years"),
}

# FIT record columns (running only): (min, max, unit)
FIT_RANGES = {
    "speed": (0.5, 8, "m/s"),
    "cadence": (40, 120, "one-foot cadence (x2 = steps/min)"),
    "step_length": (300, 2_500, "mm"),
    "stance_time": (120, 450, "ms"),
    "vertical_oscillation": (30, 160, "mm"),
    "heart_rate": (40, 230, "bpm"),
}

# Known upstream differences between Garmin sources (not mapping errors).
KNOWN_DIFFS = {("daily", "min_hr"), ("daily", "max_hr"), ("sleep", "avg_hr")}

# Dataset groups holding the same quantity in different sources.
PAIRS = [
    ("daily", "pa_daily_summary", "ex_daily_summary"),
    ("daily", "pa_steps", "ex_daily_summary"),
    ("daily", "user_summary", "ex_daily_summary"),
    ("sleep", "pa_sleep", "ex_sleep"),
    ("sleep", "sleep", "ex_sleep"),
    ("sleep", "pa_sleep", "pa_sleep_summaries"),
    ("hrv", "pa_hrv", "pa_hrv_summaries"),
    ("readiness", "training_readiness", "ex_training_readiness"),
    ("training", "pa_vo2max", "ex_vo2max"),
    ("race_predictions", "race_predictions", "ex_race_predictions"),
]


def _collect(conn: sqlite3.Connection, dataset: str) -> dict[str, dict[str, Any]]:
    _, fn = N.EXTRACTORS[dataset]
    out: dict[str, dict[str, Any]] = {}
    rows = sorted(N.stored_payloads(conn, (dataset,)), key=lambda row: N.PRIORITY.get(row[1], 9))
    for _, _, payload, _ in rows:
        for day, values in fn(json.loads(payload)):
            recorded = out.setdefault(day, {})
            for key, value in values.items():
                if value is not None:
                    recorded.setdefault(key, value)
    return out


def _agree(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= max(1.0, 0.01 * abs(b))
    return a == b


def run(conn: sqlite3.Connection) -> dict[str, Any]:
    from garmin_mcp.engine import _tz

    today = datetime.now(_tz(conn)).date().isoformat()
    problems: list[str] = []
    agreement = []
    for table, ds_a, ds_b in PAIRS:
        a, b = _collect(conn, ds_a), _collect(conn, ds_b)
        common = sorted(d for d in set(a) & set(b) if d < today)  # today is still changing
        for col in N.TABLES[table]:
            pairs = [(d, a[d][col], b[d][col]) for d in common if col in a[d] and col in b[d]]
            if not pairs:
                continue
            bad = [p for p in pairs if not _agree(p[1], p[2])]
            entry = {"table": table, "column": col, "sources": f"{ds_a} vs {ds_b}",
                     "agree": f"{len(pairs) - len(bad)}/{len(pairs)}", "examples": bad[:2]}
            agreement.append(entry)
            if bad and (table, col) not in KNOWN_DIFFS:
                problems.append(f"{table}.{col}: {entry['sources']} disagree on {len(bad)} "
                                f"days, e.g. {bad[0]}")

    ranges = []
    for (table, col), (lo, hi, unit) in RANGES.items():
        try:
            n, out_of_range = conn.execute(
                f"SELECT COUNT({col}), SUM({col} < ? OR {col} > ?) FROM {table} "
                "WHERE day < ?", (lo, hi, today)
            ).fetchone()
        except sqlite3.OperationalError:
            continue
        ranges.append({"column": f"{table}.{col}", "unit": unit, "days": n,
                       "out_of_range": out_of_range or 0})
        if out_of_range:
            problems.append(f"{table}.{col}: {out_of_range} values outside {lo}-{hi} {unit}")

    for col, (lo, hi, unit) in FIT_RANGES.items():
        avg = conn.execute(
            f"SELECT AVG({col}) FROM fit_records r JOIN activities a USING(activity_id) "
            f"WHERE a.type LIKE '%running%' AND r.speed > 0.5 AND {col} > 0").fetchone()[0]
        ranges.append({"column": f"fit_records.{col} (running avg)", "unit": unit,
                       "value": round(avg, 1) if avg else None})
        if avg is not None and not lo <= avg <= hi:
            problems.append(f"fit_records.{col}: running average {avg:.1f} outside {lo}-{hi} "
                            f"{unit}")

    fill = {}
    for table, cols in N.TABLES.items():
        try:
            total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.OperationalError:
            continue
        fill[table] = {"days": total, **{c: conn.execute(
            f"SELECT COUNT({c}) FROM {table}").fetchone()[0] for c in cols}}

    return {"ok": not problems, "problems": problems, "agreement": agreement,
            "ranges": ranges, "fill": fill,
            "known_upstream_differences": sorted(f"{t}.{c}" for t, c in KNOWN_DIFFS)}


def run_timing(conn: sqlite3.Connection) -> dict[str, Any]:
    """Per-year paired watch/stream residuals from stored outdoor runs."""
    from garmin_mcp.coaching import run_metrics
    from garmin_mcp.fit import session_messages
    from garmin_mcp.loads import RUN_TYPES

    groups: dict[str, dict[str, Any]] = {}
    for aid, start, hr, payload in conn.execute(
            f"SELECT a.activity_id, a.start_time_local, a.avg_hr, s.payload FROM activities a "
            f"LEFT JOIN fit_sessions s USING(activity_id) WHERE a.type IN "
            f"({','.join('?' * len(RUN_TYPES))}) AND a.fit_parsed=1 "
            "AND a.start_time_local IS NOT NULL ORDER BY a.start_time_local", RUN_TYPES):
        year = groups.setdefault(start[:4], {"runs_with_fit": 0, "runs_usable": 0, "pairs": {}})
        year["runs_with_fit"] += 1
        metrics = run_metrics(conn, aid)
        if metrics is None:
            continue
        year["runs_usable"] += 1
        sessions = session_messages(payload)
        session = sessions[0] if len(sessions) == 1 else {}
        for name, measured, watch in (
            ("record_span_minus_watch_elapsed_s", metrics["recorded_elapsed_s"],
             session.get("total_elapsed_time")),
            ("recorded_moving_minus_watch_timer_s", metrics["moving_s"],
             session.get("total_timer_time")),
            ("moving_hr_minus_watch_activity_hr_bpm", metrics["avg_hr"], hr),
        ):
            if measured is not None and isinstance(watch, (int, float)) and math.isfinite(watch) and watch > 0:
                year["pairs"].setdefault(name, []).append(measured - watch)
    for year in groups.values():
        year["pairs"] = {
            name: {"paired_runs": len(diff), "median_difference": round(statistics.median(diff), 2),
                   "median_absolute_difference": round(statistics.median(map(abs, diff)), 2),
                   "largest_absolute_difference": round(max(map(abs, diff)), 2)}
            for name, diff in year["pairs"].items()
        }
    return {
        "years": groups,
        "meaning": "Recorded stream minus Garmin summary in the named units. The time/HR "
                   "definitions and sampling can differ. Residuals are diagnostics, with no "
                   "pass/fail threshold and no independent validation of Garmin's sensors.",
    }


def replay_dashboard(path, months=36) -> dict[str, Any]:
    """Replay one snapshot per recorded month on a disposable SQLite copy."""
    from contextlib import closing
    from html.parser import HTMLParser
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from garmin_mcp import dashboard, db, deep_insight

    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.ids = set()
            self.duplicates = 0
            self.targets = set()

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if target := attrs.get("id"):
                self.duplicates += target in self.ids
                self.ids.add(target)
            href = attrs.get("href") or ""
            if href.startswith("#") and len(href) > 1:
                self.targets.add(href[1:])

    with TemporaryDirectory(prefix="garmin-dashboard-replay-") as work:
        target = Path(work) / "archive.db"
        with (closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as src,
              closing(sqlite3.connect(target)) as copy):
            if not src.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='daily'").fetchone():
                return {"ok": False, "reason": "Archive has no normalized daily table."}
            src.backup(copy)
        with closing(db.connect(target)) as conn:
            anchors = [row[0] for row in conn.execute(
                "SELECT max(day) AS anchor FROM daily GROUP BY substr(day,1,7) ORDER BY anchor DESC LIMIT ?",
                (months,))]
            links = duplicates = eligible = 0
            largest = 0
            for end in anchors:
                data = dashboard.collect(conn, end)
                if deep_insight.evidence({**data, "older_snapshot": False}):
                    eligible += 1
                html = dashboard._compact(dashboard.render(data))
                structure = Links()
                structure.feed(html)
                links += len(structure.targets - structure.ids)
                duplicates += structure.duplicates
                largest = max(largest, len(html.encode()))
    return {"ok": bool(anchors) and links == duplicates == 0, "months_sampled": len(anchors),
            "broken_internal_links": links, "duplicate_ids": duplicates,
            "months_with_coaching_evidence": eligible, "largest_html_bytes": largest}


def main() -> None:
    from garmin_mcp import db
    from garmin_mcp.config import data_dir, db_path

    parser = argparse.ArgumentParser(description="Check stored Garmin data.")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--archive-audit", action="store_true",
                       help="Report local archive integrity, file references and wellness coverage.")
    modes.add_argument("--run-timing", action="store_true",
                        help="Compare stored FIT recordings with watch summaries by year, read-only.")
    modes.add_argument("--replay-dashboard", action="store_true",
                        help="Check monthly dashboard snapshots without changing the archive.")
    modes.add_argument("--preview-wellness-fit", type=Path, metavar="FILE",
                       help="Compare a monitoring FIT file with saved wellness readings without importing.")
    modes.add_argument("--export-csv", choices=("activities", "wellness"),
                       help="Export a selected local archive date range as CSV.")
    parser.add_argument("--from-date", type=date.fromisoformat, help="First local date (YYYY-MM-DD).")
    parser.add_argument("--to-date", type=date.fromisoformat, help="Last local date (YYYY-MM-DD).")
    parser.add_argument("--output", type=Path, help="New private CSV file (default: standard output).")
    parser.add_argument("--include-dates", action="store_true",
                        help="Show local dates for wellness FIT preview counts.")
    parser.add_argument("--retain", action="store_true",
                        help="Also save the validated monitoring FIT in the private data directory.")
    args = parser.parse_args()
    if (args.include_dates or args.retain) and args.preview_wellness_fit is None:
        parser.error("--include-dates and --retain require --preview-wellness-fit.")
    if args.export_csv:
        from garmin_mcp.archive_export import export_file, write_csv

        if args.from_date is None or args.to_date is None:
            parser.error("--export-csv requires --from-date and --to-date.")
        path = db_path()
        if not path.is_file():
            parser.error("No stored Garmin database. Run this where your archive is stored.")
        try:
            if args.output is None:
                write_csv(path, args.export_csv, args.from_date, args.to_date, sys.stdout)
            else:
                export_file(path, args.export_csv, args.from_date, args.to_date, args.output)
        except FileExistsError:
            parser.error("The CSV destination already exists. Choose a new filename.")
        except sqlite3.Error:
            parser.error("Could not read the expected Garmin archive tables.")
        except (ValueError, OSError) as error:
            parser.error(str(error))
        return
    if args.from_date is not None or args.to_date is not None or args.output is not None:
        parser.error("Date and output options require --export-csv.")
    if args.preview_wellness_fit:
        from garmin_mcp.monitoring_preview import preview

        path = db_path()
        if not path.is_file():
            parser.error("No stored Garmin database. Run this where your archive is stored.")
        try:
            report = preview(path, args.preview_wellness_fit, include_dates=args.include_dates,
                             retain_directory=data_dir() / "monitoring-fit" if args.retain else None)
        except sqlite3.Error:
            parser.error("Could not read the expected Garmin archive tables.")
        except (ValueError, OSError) as error:
            parser.error(str(error))
        print(json.dumps(report, indent=2))
        return
    if args.archive_audit:
        from garmin_mcp.archive_audit import audit

        path = db_path()
        if not path.is_file():
            parser.error("No stored Garmin database. Run this where your archive is stored.")
        report = audit(path)
        print(json.dumps(report, indent=2))
        raise SystemExit(0 if report["ok"] else 1)
    if args.replay_dashboard:
        path = db_path()
        if not path.is_file():
            parser.error("No stored Garmin database. Run this where your archive is stored.")
        report = replay_dashboard(path)
        print(json.dumps(report, indent=2))
        raise SystemExit(0 if report["ok"] else 1)
    if args.run_timing:
        path = db_path()
        if not path.is_file():
            parser.error("No stored Garmin database. Run this where your archive is stored.")
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as read_only:
            print(json.dumps(run_timing(read_only), indent=2))
        return

    path = db_path()
    if not path.is_file():
        parser.error("No stored Garmin database. Run this where your archive is stored.")
    conn = db.connect(path)
    N.rebuild(conn)
    result = run(conn)
    print(json.dumps({k: result[k] for k in ("ok", "problems", "known_upstream_differences")},
                     indent=2))
    print("fill rates:", json.dumps(result["fill"], indent=1))
    from garmin_mcp import loads

    day = conn.execute("SELECT MAX(day) FROM daily").fetchone()[0]
    sc = loads.sense_checks(conn, day) if day else {"checks": [], "threshold_notes": []}
    print("sense checks (ours vs Garmin / physics):")
    for c in sc["checks"]:
        mark = "ok  " if c["ok"] else ("n/a " if c["ok"] is None else "FLAG")
        print(f"  [{mark}] {c['check']}: {c['detail']} (tolerance: {c['tolerance']})")
    for note in sc["threshold_notes"]:
        print(f"  note: {note}")
    # Mapping/unit problems fail the run; sense-check flags are findings to review.
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
