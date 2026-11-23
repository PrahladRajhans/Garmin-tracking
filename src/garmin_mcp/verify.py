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

import json
import sqlite3
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
    for table in ("raw_daily", "raw_range"):
        for (payload,) in conn.execute(
            f"SELECT payload FROM {table} WHERE dataset=? AND payload IS NOT NULL "
            "AND payload!='null'", (dataset,)
        ):
            for day, values in fn(json.loads(payload)):
                out.setdefault(day, {}).update({k: v for k, v in values.items() if v is not None})
    return out


def _agree(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= max(1.0, 0.01 * abs(b))
    return a == b


def run(conn: sqlite3.Connection) -> dict[str, Any]:
    problems: list[str] = []
    agreement = []
    for table, ds_a, ds_b in PAIRS:
        a, b = _collect(conn, ds_a), _collect(conn, ds_b)
        today = max(set(a) | set(b), default="")
        common = sorted(d for d in set(a) & set(b) if d != today)  # today is still changing
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
                f"WHERE day < (SELECT MAX(day) FROM {table})", (lo, hi)  # today is partial
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


def main() -> None:
    from garmin_mcp import db
    from garmin_mcp.config import db_path

    conn = db.connect(db_path())
    N.rebuild(conn)
    result = run(conn)
    print(json.dumps({k: result[k] for k in ("ok", "problems", "known_upstream_differences")},
                     indent=2))
    print("fill rates:", json.dumps(result["fill"], indent=1))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
