"""Build tidy per-day tables from the raw payloads of every source.

Raw data stays untouched; these tables are rebuilt from it (fast, deterministic), so a mapping
fix only needs `rebuild()` and never a re-download.

Source priority when several sources have the same day/field (field by field, first non-null
wins): official Personal API > unofficial garminconnect > account export. All three are Garmin's
own numbers, so priority only matters for freshness; values normally agree.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from collections.abc import Callable, Iterator
from datetime import UTC
from typing import Any

from garmin_mcp.importer import _calendar_day

PRIORITY = {"personal_api": 0, "garminconnect": 1, "export": 2}

TABLES: dict[str, list[str]] = {
    "daily": [
        "steps", "distance_m", "resting_hr", "min_hr", "max_hr", "kcal_total", "kcal_active",
        "intensity_min_moderate", "intensity_min_vigorous", "stress_avg", "stress_max",
        "body_battery_min", "body_battery_max", "body_battery_charged", "body_battery_drained",
        "respiration_avg", "spo2_avg", "floors_up_m",
    ],
    "sleep": [
        "sleep_start", "sleep_end", "sleep_s", "deep_s", "light_s", "rem_s", "awake_s",
        "score", "avg_spo2", "avg_respiration", "avg_sleep_stress", "avg_hr", "awake_count",
        "sleep_need_min",
    ],
    "hrv": ["last_night_avg", "weekly_avg", "baseline_low", "baseline_high", "status"],
    "health_status": [
        "hrv", "hrv_low", "hrv_high", "rhr", "rhr_low", "rhr_high", "respiration",
        "respiration_low", "respiration_high", "spo2", "status_hrv", "status_rhr",
    ],
    "readiness": [
        "score", "level", "morning_score", "sleep_factor_pct", "recovery_factor_pct",
        "load_factor_pct", "stress_history_factor_pct", "hrv_factor_pct",
        "sleep_history_factor_pct", "recovery_time_min", "acute_load", "hrv_weekly_avg",
        "feedback",
    ],
    "training": [
        "status", "fitness_trend", "acute_load", "chronic_load", "acwr", "acwr_status",
        "vo2max_run", "vo2max_cycle",
    ],
    "race_predictions": ["t5k_s", "t10k_s", "half_s", "marathon_s"],
    "scores": ["endurance_score", "endurance_class", "hill_score", "hill_strength",
               "hill_endurance"],
    "fitness_age": ["fitness_age", "chronological_age", "achievable_age", "rhr",
                    "vigorous_days_avg", "vigorous_min_avg", "bmi"],
}


# --------------------------------------------------------------------------- helpers
def _g(obj: Any, *path: Any) -> Any:
    for key in path:
        if isinstance(obj, dict):
            obj = obj.get(key)
        elif isinstance(obj, list) and isinstance(key, int) and len(obj) > key:
            obj = obj[key]
        else:
            return None
    return obj


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):  # e.g. movement.steps -> {"value": 1234, ...}
        for key in ("value", "total", "count"):
            if isinstance(value.get(key), (int, float)):
                return float(value[key])
    return None


def _nonneg(value: Any) -> float | None:
    """Garmin uses -1/-2 for 'no data' in stress and Body Battery fields."""
    v = _num(value)
    return v if v is not None and v >= 0 else None


def _bb_stat(rec: dict[str, Any], kind: str) -> Any:
    for stat in _g(rec, "bodyBattery", "bodyBatteryStatList") or []:
        if isinstance(stat, dict) and stat.get("bodyBatteryStatType") == kind:
            return stat.get("statsValue")
    return None


def _first(*values: Any) -> Any:
    return next((v for v in values if v is not None), None)


def _records(obj: Any) -> Iterator[dict[str, Any]]:
    """Every dict (at any depth) carrying a calendar date."""
    if isinstance(obj, dict):
        if any(k in obj for k in ("calendarDate", "date")):
            yield obj
            return
        for v in obj.values():
            yield from _records(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _records(v)


def _ts_key(rec: dict[str, Any]) -> str:
    return str(_first(rec.get("timestamp"), rec.get("timestampLocal"),
                      rec.get("updateTimestamp"), ""))


def _latest(recs: list[dict[str, Any]]) -> dict[str, Any]:
    return max(recs, key=_ts_key)


def _as_list(payload: Any) -> list[Any]:
    return payload if isinstance(payload, list) else [payload]


def _ms_to_iso(value: Any) -> str | None:
    """GMT timestamp (epoch ms or Garmin string) -> 'YYYY-MM-DD HH:MM:SS' UTC."""
    if isinstance(value, (int, float)) and value > 10**11:
        from datetime import datetime

        return datetime.fromtimestamp(value / 1000, tz=UTC).strftime(
            "%Y-%m-%d %H:%M:%S")
    if isinstance(value, str) and len(value) >= 19:  # '2026-10-25T00:08:45.0'
        return value[:10] + " " + value[11:19]
    return None


# --------------------------------------------------------------------------- extractors
# Each extractor takes one raw payload and yields (day, {field: value}).
Rows = Iterator[tuple[str, dict[str, Any]]]


def daily_from_summary(payload: Any) -> Rows:
    for rec in _records(payload):
        day = _calendar_day(rec.get("calendarDate"))
        if not day:
            continue
        if "movement" in rec or "heartRate" in rec:  # Personal API daily summary
            yield day, {
                "steps": _num(_g(rec, "movement", "steps", "value")),
                "distance_m": _num(_g(rec, "movement", "steps", "distanceInMeters")),
                # floorsAscended.value is a floor COUNT; the metres are distanceInMeters.
                "floors_up_m": _num(_g(rec, "movement", "floorsAscended", "distanceInMeters")),
                "resting_hr": _num(_g(rec, "heartRate", "restingValue")),
                "min_hr": _num(_g(rec, "heartRate", "minValue")),
                "max_hr": _num(_g(rec, "heartRate", "maxValue")),
                "kcal_total": _num(_g(rec, "calories", "burnedTotal")),
                "kcal_active": _num(_g(rec, "calories", "burnedActive")),
                "intensity_min_moderate": _num(_g(rec, "intensityMinutes", "moderate")),
                "intensity_min_vigorous": _num(_g(rec, "intensityMinutes", "vigorous")),
                "stress_avg": _nonneg(_g(rec, "stress", "avgLevel")),
                "stress_max": _nonneg(_g(rec, "stress", "maxLevel")),
                "body_battery_min": _nonneg(_g(rec, "bodyBattery", "minValue")),
                "body_battery_max": _nonneg(_g(rec, "bodyBattery", "maxValue")),
                "body_battery_charged": _num(_g(rec, "bodyBattery", "chargedValue")),
                "body_battery_drained": _num(_g(rec, "bodyBattery", "drainedValue")),
                "respiration_avg": _num(_g(rec, "respiration", "avgValue")),
                "spo2_avg": _num(_g(rec, "pulseOx", "avgValue")),
            }
        else:  # export UDS file / unofficial user summary (same flat field names)
            yield day, {
                "steps": _num(rec.get("totalSteps")),
                "distance_m": _num(_first(rec.get("totalDistanceMeters"),
                                          rec.get("totalDistance"))),
                "floors_up_m": _num(rec.get("floorsAscendedInMeters")),
                # export UDS: restingHeartRate is a 7-day value; the day's own is currentDay...
                "resting_hr": _num(_first(rec.get("currentDayRestingHeartRate"),
                                          rec.get("restingHeartRate"))),
                "min_hr": _num(rec.get("minHeartRate")),
                "max_hr": _num(rec.get("maxHeartRate")),
                "kcal_total": _num(rec.get("totalKilocalories")),
                "kcal_active": _num(rec.get("activeKilocalories")),
                "intensity_min_moderate": _num(rec.get("moderateIntensityMinutes")),
                "intensity_min_vigorous": _num(rec.get("vigorousIntensityMinutes")),
                "stress_avg": _nonneg(_first(rec.get("averageStressLevel"),
                                             _g(rec, "allDayStress", "aggregatorList", 0,
                                                "averageStressLevel"))),
                "stress_max": _nonneg(_first(rec.get("maxStressLevel"),
                                             _g(rec, "allDayStress", "aggregatorList", 0,
                                                "maxStressLevel"))),
                "body_battery_min": _nonneg(_first(rec.get("bodyBatteryLowestValue"),
                                                   _bb_stat(rec, "LOWEST"))),
                "body_battery_max": _nonneg(_first(rec.get("bodyBatteryHighestValue"),
                                                   _bb_stat(rec, "HIGHEST"))),
                "body_battery_charged": _nonneg(_first(rec.get("bodyBatteryChargedValue"),
                                                       _g(rec, "bodyBattery", "chargedValue"))),
                "body_battery_drained": _nonneg(_first(rec.get("bodyBatteryDrainedValue"),
                                                       _g(rec, "bodyBattery", "drainedValue"))),
                "respiration_avg": _num(_first(rec.get("avgWakingRespirationValue"),
                                               _g(rec, "respiration", "avgWakingRespirationValue"))),
                "spo2_avg": _num(_first(rec.get("averageSpo2"), rec.get("averageSpo2Value"))),
            }


def daily_from_steps(payload: Any) -> Rows:
    for rec in _records(payload):
        day = _calendar_day(rec.get("calendarDate"))
        if day:
            yield day, {"steps": _num(rec.get("totalSteps")),
                        "distance_m": _num(rec.get("totalDistance"))}


def sleep_rows(payload: Any) -> Rows:
    for rec in _records(payload):
        rec = rec.get("dailySleepDTO", rec)
        day = _calendar_day(rec.get("calendarDate"))
        if not day:
            continue
        deep, light, rem = (_num(rec.get(k)) for k in
                            ("deepSleepSeconds", "lightSleepSeconds", "remSleepSeconds"))
        stages = sum(x for x in (deep, light, rem) if x is not None) or None
        yield day, {
            "sleep_start": _ms_to_iso(_first(rec.get("sleepStartTimestampGMT"))),
            "sleep_end": _ms_to_iso(_first(rec.get("sleepEndTimestampGMT"))),
            "sleep_s": _first(_num(rec.get("sleepTimeSeconds")), stages),
            "deep_s": deep, "light_s": light, "rem_s": rem,
            "awake_s": _num(rec.get("awakeSleepSeconds")),
            "score": _num(_first(_g(rec, "sleepScores", "overall", "value"),
                                 _g(rec, "sleepScores", "overallScore"))),
            "avg_spo2": _num(_first(rec.get("averageSpO2Value"),
                                    _g(rec, "spo2SleepSummary", "averageSPO2"))),
            "avg_respiration": _num(_first(rec.get("averageRespirationValue"),
                                           rec.get("averageRespiration"))),
            "avg_sleep_stress": _num(rec.get("avgSleepStress")),
            "avg_hr": _num(_first(rec.get("avgHeartRate"),
                                  _g(rec, "spo2SleepSummary", "averageHR"))),
            "awake_count": _num(rec.get("awakeCount")),
            "sleep_need_min": _num(_g(rec, "sleepNeed", "actual")),
        }


def hrv_rows(payload: Any) -> Rows:
    for rec in _records(payload):
        rec = rec if "lastNightAvg" in rec else rec.get("hrvSummary", rec)
        day = _calendar_day(rec.get("calendarDate"))
        if day and ("lastNightAvg" in rec or "weeklyAvg" in rec):
            yield day, {
                "last_night_avg": _num(rec.get("lastNightAvg")),
                "weekly_avg": _num(rec.get("weeklyAvg")),
                "baseline_low": _num(_g(rec, "baseline", "balancedLow")),
                "baseline_high": _num(_g(rec, "baseline", "balancedUpper")),
                "status": rec.get("status"),
            }


def hrv_rows_wrapped(payload: Any) -> Rows:
    """Personal API / unofficial single-day HRV: {"hrvSummary": {...}}."""
    yield from hrv_rows(_g(payload, "hrvSummary") or payload)


def health_status_rows(payload: Any) -> Rows:
    for rec in _as_list(payload):
        day = _calendar_day(_g(rec, "calendarDate"))
        if not day:
            continue
        m = {x.get("type"): x for x in rec.get("metrics", []) if isinstance(x, dict)}
        yield day, {
            "hrv": _num(_g(m, "HRV", "value")),
            "hrv_low": _num(_g(m, "HRV", "baselineLowerLimit")),
            "hrv_high": _num(_g(m, "HRV", "baselineUpperLimit")),
            "rhr": _num(_g(m, "HR", "value")),
            "rhr_low": _num(_g(m, "HR", "baselineLowerLimit")),
            "rhr_high": _num(_g(m, "HR", "baselineUpperLimit")),
            "respiration": _num(_g(m, "RESPIRATION", "value")),
            "respiration_low": _num(_g(m, "RESPIRATION", "baselineLowerLimit")),
            "respiration_high": _num(_g(m, "RESPIRATION", "baselineUpperLimit")),
            "spo2": _num(_g(m, "SPO2", "value")),
            "status_hrv": _g(m, "HRV", "status"),
            "status_rhr": _g(m, "HR", "status"),
        }


def readiness_rows(payload: Any) -> Rows:
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in _records(payload):
        day = _calendar_day(rec.get("calendarDate"))
        if day and "score" in rec:
            by_day[day].append(rec)
    for day, recs in by_day.items():
        latest = _latest(recs)
        morning = min(recs, key=_ts_key)
        yield day, {
            "score": _num(latest.get("score")),
            "level": latest.get("level"),
            "morning_score": _num(morning.get("score")),
            "sleep_factor_pct": _num(latest.get("sleepScoreFactorPercent")),
            "recovery_factor_pct": _num(latest.get("recoveryTimeFactorPercent")),
            "load_factor_pct": _num(latest.get("acwrFactorPercent")),
            "stress_history_factor_pct": _num(latest.get("stressHistoryFactorPercent")),
            "hrv_factor_pct": _num(latest.get("hrvFactorPercent")),
            "sleep_history_factor_pct": _num(latest.get("sleepHistoryFactorPercent")),
            "recovery_time_min": _num(latest.get("recoveryTime")),
            "acute_load": _num(latest.get("acuteLoad")),
            "hrv_weekly_avg": _num(latest.get("hrvWeeklyAverage")),
            "feedback": _first(latest.get("feedbackShort"), latest.get("feedbackLong")),
        }


def _grouped_latest(payload: Any, need: str) -> Iterator[tuple[str, dict[str, Any]]]:
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in _records(payload):
        day = _calendar_day(rec.get("calendarDate"))
        if day and need in rec:
            by_day[day].append(rec)
    for day, recs in by_day.items():
        yield day, _latest(recs)


def training_status_rows(payload: Any) -> Rows:
    for day, r in _grouped_latest(payload, "trainingStatus"):
        yield day, {"status": r.get("trainingStatus"), "fitness_trend": r.get("fitnessLevelTrend")}


def acute_load_rows(payload: Any) -> Rows:
    for day, r in _grouped_latest(payload, "dailyTrainingLoadAcute"):
        yield day, {
            "acute_load": _num(r.get("dailyTrainingLoadAcute")),
            "chronic_load": _num(r.get("dailyTrainingLoadChronic")),
            "acwr": _num(r.get("dailyAcuteChronicWorkloadRatio")),
            "acwr_status": r.get("acwrStatus"),
        }


def vo2max_rows(payload: Any) -> Rows:
    for rec in _records(payload):
        day = _calendar_day(rec.get("calendarDate"))
        value = _num(_first(rec.get("vo2MaxPreciseValue"), rec.get("vo2MaxValue")))
        if not day or value is None:
            continue
        sport = str(rec.get("sport") or "RUNNING").upper()
        yield day, {"vo2max_cycle" if "CYCL" in sport else "vo2max_run": value}


def race_rows(payload: Any) -> Rows:
    keys = {"t5k_s": ("raceTime5K", "time5K"), "t10k_s": ("raceTime10K", "time10K"),
            "half_s": ("raceTimeHalf", "timeHalfMarathon"),
            "marathon_s": ("raceTimeMarathon", "timeMarathon")}
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in _records(payload):
        day = _calendar_day(rec.get("calendarDate"))
        if day and any(k in rec for pair in keys.values() for k in pair):
            by_day[day].append(rec)
    for day, recs in by_day.items():
        r = _latest(recs)
        yield day, {col: _num(_first(*(r.get(k) for k in ks))) for col, ks in keys.items()}


def endurance_rows(payload: Any) -> Rows:
    for day, r in _grouped_latest(payload, "overallScore"):
        if "strengthScore" in r:
            continue
        yield day, {"endurance_score": _num(r.get("overallScore")),
                    "endurance_class": _num(r.get("classification"))}


def hill_rows(payload: Any) -> Rows:
    for day, r in _grouped_latest(payload, "strengthScore"):
        yield day, {"hill_score": _num(r.get("overallScore")),
                    "hill_strength": _num(r.get("strengthScore")),
                    "hill_endurance": _num(r.get("enduranceScore"))}


def fitness_age_rows_for(day: str, payload: Any) -> Rows:
    if not isinstance(payload, dict) or "fitnessAge" not in payload:
        return
    c = payload.get("components") or {}
    yield day, {
        "fitness_age": _num(payload.get("fitnessAge")),
        "chronological_age": _num(payload.get("chronologicalAge")),
        "achievable_age": _num(payload.get("achievableFitnessAge")),
        "rhr": _num(_g(c, "rhr", "value")),
        "vigorous_days_avg": _num(_g(c, "vigorousDaysAvg", "value")),
        "vigorous_min_avg": _num(_g(c, "vigorousMinutesAvg", "value")),
        "bmi": _num(_g(c, "bmi", "value")),
    }


# dataset -> (table, extractor). Extractors for per-day raw rows receive the payload only;
# fitness age needs the day because its payload has no date.
EXTRACTORS: dict[str, tuple[str, Callable[[Any], Rows]]] = {
    "pa_daily_summary": ("daily", daily_from_summary),
    "user_summary": ("daily", daily_from_summary),
    "ex_daily_summary": ("daily", daily_from_summary),
    "pa_steps": ("daily", daily_from_steps),
    "pa_sleep": ("sleep", sleep_rows),
    "pa_sleep_summaries": ("sleep", sleep_rows),
    "sleep": ("sleep", sleep_rows),
    "ex_sleep": ("sleep", sleep_rows),
    "pa_hrv": ("hrv", hrv_rows_wrapped),
    "pa_hrv_summaries": ("hrv", hrv_rows),
    "hrv": ("hrv", hrv_rows_wrapped),
    "ex_health_status": ("health_status", health_status_rows),
    "training_readiness": ("readiness", readiness_rows),
    "ex_training_readiness": ("readiness", readiness_rows),
    "training_status": ("training", training_status_rows),
    "ex_training_status": ("training", training_status_rows),
    "ex_acute_load": ("training", acute_load_rows),
    "pa_vo2max": ("training", vo2max_rows),
    "max_metrics": ("training", vo2max_rows),
    "ex_vo2max": ("training", vo2max_rows),
    "race_predictions": ("race_predictions", race_rows),
    "ex_race_predictions": ("race_predictions", race_rows),
    "endurance_score": ("scores", endurance_rows),
    "ex_endurance_score": ("scores", endurance_rows),
    "hill_score": ("scores", hill_rows),
    "ex_hill_score": ("scores", hill_rows),
}
FITNESS_AGE_DATASETS = {"pa_fitness_age", "fitness_age"}


# --------------------------------------------------------------------------- build
def rebuild(conn: sqlite3.Connection) -> dict[str, int]:
    """Recreate all tidy tables from raw data. Returns row counts per table."""
    cand: dict[str, dict[str, list[tuple[int, str, dict[str, Any]]]]] = {
        t: defaultdict(list) for t in TABLES
    }

    def add(table: str, source: str, rows: Rows) -> None:
        prio = PRIORITY.get(source, 9)
        for day, values in rows:
            cand[table][day].append((prio, source, values))

    for table_name in ("raw_daily", "raw_range"):
        day_col = "day" if table_name == "raw_daily" else "NULL"
        for dataset, source, payload, day in conn.execute(
            f"SELECT dataset, source, payload, {day_col} FROM {table_name} "
            "WHERE payload IS NOT NULL AND payload != 'null'"
        ):
            data = json.loads(payload)
            if dataset in FITNESS_AGE_DATASETS and day:
                add("fitness_age", source, fitness_age_rows_for(day, data))
            elif dataset in EXTRACTORS:
                table, fn = EXTRACTORS[dataset]
                add(table, source, fn(data))

    counts = {}
    for table, cols in TABLES.items():
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.execute(
            f"CREATE TABLE {table} (day TEXT PRIMARY KEY, "
            + ", ".join(cols) + ", sources TEXT)"
        )
        rows = []
        for day, entries in cand[table].items():
            entries.sort(key=lambda e: e[0])
            merged = {c: _first(*(e[2].get(c) for e in entries)) for c in cols}
            if all(v is None for v in merged.values()):
                continue
            used = sorted({e[1] for e in entries if any(e[2].get(c) is not None for c in cols)},
                          key=lambda s: PRIORITY.get(s, 9))
            rows.append((day, *merged.values(), ",".join(used)))
        conn.executemany(
            f"INSERT INTO {table} VALUES ({', '.join('?' for _ in range(len(cols) + 2))})", rows
        )
        counts[table] = len(rows)
    conn.commit()
    return counts


def main() -> None:
    from garmin_mcp import db
    from garmin_mcp.config import db_path

    conn = db.connect(db_path())
    print(json.dumps(rebuild(conn), indent=2))


if __name__ == "__main__":
    main()
