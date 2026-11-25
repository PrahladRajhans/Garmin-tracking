"""Read-only aggregate evidence about the archive and the current FIT references."""

import sqlite3
import stat
from contextlib import closing
from datetime import date
from pathlib import Path

from garmin_mcp import engine, wellness_timeline


def _fit_inventory(conn):
    counts = dict.fromkeys(("activities", "decoded", "no_file_reference", "present",
                            "missing", "unavailable_or_empty"), 0)
    for stored_path, decoded in conn.execute("SELECT fit_path,fit_parsed FROM activities"):
        counts["activities"] += 1
        counts["decoded"] += int(bool(decoded))
        if not stored_path:
            counts["no_file_reference"] += 1
            continue
        try:
            info = Path(stored_path).stat()
        except FileNotFoundError:
            counts["missing"] += 1
        except (OSError, TypeError, ValueError):
            counts["unavailable_or_empty"] += 1
        else:
            key = "present" if stat.S_ISREG(info.st_mode) and info.st_size > 0 else "unavailable_or_empty"
            counts[key] += 1
    return counts


def _wellness_coverage(conn):
    zone = engine._tz(conn)
    usable = {key: [] for key in wellness_timeline.METRICS}
    stored = 0
    for day, payload in wellness_timeline.archived_days(conn):
        stored += 1
        for key in wellness_timeline.samples(payload, day, zone):
            usable[key].append(day)
    coverage = {}
    for key, days in usable.items():
        dates = [date.fromisoformat(day) for day in days]
        coverage[key] = {"usable_days": len(dates), "first_day": days[0] if days else None,
                         "last_day": days[-1] if days else None,
                         "gaps_between_usable_days": (dates[-1] - dates[0]).days + 1 - len(dates)
                         if days else None}
    return {"stored_connect_stress_days": stored, **coverage}


def audit(path):
    """Report coverage without migration, downloads, record values, or filesystem paths."""
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            if [row[0] for row in conn.execute("PRAGMA quick_check(1)")] != ["ok"]:
                return {"ok": False, "reason": "SQLite quick check failed."}
            available = {row[0] for row in conn.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
            if not {"raw_daily", "activities", "meta"} <= available:
                return {"ok": False, "reason": "This database has no Garmin Tracking archive schema."}
            fit = _fit_inventory(conn)
            return {"ok": not (fit["missing"] or fit["unavailable_or_empty"]),
                    "sqlite_quick_check": "passed", "fit_references": fit,
                    "wellness_timelines": _wellness_coverage(conn)}
    except sqlite3.DatabaseError:
        return {"ok": False, "reason": "Could not read the expected Garmin Tracking archive schema."}
