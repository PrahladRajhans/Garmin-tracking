"""Retrospective check of recorded Garmin readiness against matched-run heart rate."""

from __future__ import annotations

import json
import sqlite3
import statistics
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from garmin_mcp import coaching, run_evidence
from garmin_mcp.normalize import _calendar_day, _records

MIN_PAIRED_DAYS = 20
LOOKBACK_DAYS = 365


def _garmin_time(value: str | None) -> datetime | None:
    if not isinstance(value, str) or len(value) < 19 or value[10] not in ("T", " "):
        return None
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError:
        return None
    return timestamp.replace(tzinfo=timestamp.tzinfo or UTC).astimezone(UTC)


def _first_scores(conn: sqlite3.Connection, lo: str, end: str) -> dict:
    earliest = {}
    for day, payload in conn.execute(
            "SELECT day,payload FROM raw_daily WHERE dataset IN "
            "('training_readiness','ex_training_readiness') AND day BETWEEN ? AND ? "
            "AND payload IS NOT NULL ORDER BY dataset DESC", (lo, end)):
        for record in _records(json.loads(payload)):
            if _calendar_day(record.get("calendarDate")) != day:
                continue
            timestamp, score = _garmin_time(record.get("timestamp")), record.get("score")
            if timestamp is None or type(score) not in (int, float) or not 0 <= score <= 100:
                continue
            if day not in earliest or timestamp < earliest[day][0]:
                earliest[day] = (timestamp, score)
    return earliest


def benchmark(
    conn: sqlite3.Connection, end: str,
    *, read_metrics: Callable[[sqlite3.Connection, int], dict | None] = coaching.run_metrics,
) -> dict:
    lo = (date.fromisoformat(end) - timedelta(days=LOOKBACK_DAYS - 1)).isoformat()
    scores = _first_scores(conn, lo, end)
    pairs = {}
    for aid, local, utc in conn.execute(
            f"SELECT activity_id,start_time_local,start_time_gmt FROM activities "
            f"WHERE type IN ({coaching.RUN_IN}) AND fit_parsed=1 "
            "AND substr(start_time_local,1,10) BETWEEN ? AND ? "
            "ORDER BY julianday(start_time_gmt), activity_id",
            (*coaching.RUN_TYPES, lo, end)):
        day = local[:10]
        if day not in scores or day in pairs:
            continue
        timestamp = _garmin_time(utc)
        recorded_at, score = scores[day]
        if timestamp is None or recorded_at >= timestamp:
            continue
        metrics = read_metrics(conn, aid)
        if not metrics:
            continue
        comparison = run_evidence.matched_effort(conn, aid, metrics, read_metrics)
        if comparison["available"]:
            pairs[day] = {"date": day, "activity_id": aid, "readiness_score": score,
                          "hr_vs_matches_bpm": comparison["difference_hr_bpm"],
                          "matched_runs": len(comparison["matches"])}
    series = [pairs[day] for day in sorted(pairs)]
    result = {"available": False, "dated_readiness_scores": len(scores), "pairs": series,
              "paired_days": len(series), "minimum_paired_days": MIN_PAIRED_DAYS,
              "from": lo, "through": end}
    if len(series) < MIN_PAIRED_DAYS:
        return {**result, "reason": f"{len(series)} of {MIN_PAIRED_DAYS} paired days. "
                "Each needs a timestamped Garmin score before a run with earlier matches."}
    try:
        rank_correlation = statistics.correlation([r["readiness_score"] for r in series],
                                                   [r["hr_vs_matches_bpm"] for r in series],
                                                   method="ranked")
    except statistics.StatisticsError:
        return {**result, "reason": "The recorded scores or run differences do not vary."}
    return {**result, "available": True, "spearman_rho": round(rank_correlation, 3),
            "interpretation": "Historical association. Lower heart rate at matched pace can "
            "reflect several factors. This check cannot predict the next run or establish cause."}
