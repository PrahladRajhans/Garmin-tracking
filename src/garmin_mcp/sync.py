"""Incremental sync: Garmin -> SQLite.

Rules:
- Days already stored are skipped, except the most recent `refresh_days`, which Garmin keeps
  updating (sleep lands next morning, HRV status finalises, etc.).
- Every call is independent: one failing endpoint never stops the run. After
  `max_consecutive_errors` failures in a row (usually expired auth), the run aborts early.
- A small delay between calls keeps request rates polite.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
import uuid
from contextlib import closing
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from garmin_mcp import db, fit
from garmin_mcp.client import today
from garmin_mcp.config import db_path, fit_dir
from garmin_mcp.sources.base import DataSource


@dataclass
class SyncResult:
    run_id: str
    fetched: int = 0
    skipped: int = 0
    errors: int = 0
    new_activities: int = 0
    aborted: str | None = None
    rate_limit_waits: int = 0
    error_samples: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class _Abort(Exception):
    pass


class _RateLimited(Exception):
    def __init__(self, seconds: float) -> None:
        super().__init__(seconds)
        self.seconds = seconds


def _retry_after(exc: Exception) -> float | None:
    """Seconds to wait if `exc` is an HTTP 429 rate-limit error, else None.

    Garmin's Personal API allows ~100 requests per window and returns
    {"retryInSeconds": N} in the 429 body. Other sources may only set status_code.
    """
    status = getattr(exc, "status_code", None) or getattr(
        getattr(exc, "response", None), "status_code", None
    )
    if status != 429 and "429" not in str(exc)[:200]:
        return None
    text = getattr(exc, "response_text", "") or str(exc)
    match = re.search(r'"retryInSeconds"\s*:\s*(\d+)', text)
    return float(match.group(1)) + 1 if match else 30.0


class Syncer:
    def __init__(
        self,
        conn: sqlite3.Connection,
        source: DataSource,
        *,
        delay: float = 0.4,
        refresh_days: int = 2,
        max_consecutive_errors: int = 8,
        store_fit_files: bool = True,
        max_rate_limit_waits: int = 200,
        sleep=time.sleep,
    ) -> None:
        self.conn = conn
        self.source = source
        self.delay = delay
        self.refresh_days = refresh_days
        self.max_consecutive_errors = max_consecutive_errors
        self.store_fit_files = store_fit_files
        self.result = SyncResult(run_id=uuid.uuid4().hex[:12])
        self._consecutive = 0
        self._sleep = sleep
        self._rate_waits_left = max_rate_limit_waits

    # -- helpers -------------------------------------------------------------
    def _call(self, dataset: str, key: str, fn, *args) -> tuple[bool, Any]:
        while True:
            try:
                return self._call_once(dataset, key, fn, *args)
            except _RateLimited as rl:
                if self._rate_waits_left <= 0:
                    raise _Abort(f"rate limit: gave up after repeated waits ({dataset})") from rl
                self._rate_waits_left -= 1
                self.result.rate_limit_waits += 1
                self._sleep(rl.seconds)

    def _call_once(self, dataset: str, key: str, fn, *args) -> tuple[bool, Any]:
        try:
            payload = fn(*args)
        except Exception as exc:
            wait = _retry_after(exc)
            if wait is not None:
                raise _RateLimited(wait) from exc
            self.result.errors += 1
            self._consecutive += 1
            msg = f"{dataset}[{key}]: {type(exc).__name__}: {exc}"[:300]
            if len(self.result.error_samples) < 10:
                self.result.error_samples.append(msg)
            db.log(self.conn, self.result.run_id, self.source.name, dataset, key, "error", msg)
            self.conn.commit()
            if self._consecutive >= self.max_consecutive_errors:
                raise _Abort(f"{self._consecutive} consecutive errors; last: {msg}") from exc
            return False, None
        finally:
            if self.delay:
                self._sleep(self.delay)
        self._consecutive = 0
        self.result.fetched += 1
        db.log(self.conn, self.result.run_id, self.source.name, dataset, key, "ok")
        return True, payload

    # -- phases --------------------------------------------------------------
    def sync_daily(self, start: date, end: date) -> None:
        fresh_from = today() - timedelta(days=self.refresh_days)
        day = start
        while day <= end:
            key = day.isoformat()
            for dataset, fn in self.source.daily.items():
                if day < fresh_from and db.has_daily(self.conn, dataset, key):
                    self.result.skipped += 1
                    continue
                ok, payload = self._call(dataset, key, fn, key)
                if ok:
                    db.put_daily(self.conn, dataset, key, self.source.name, payload)
            self.conn.commit()
            day += timedelta(days=1)

    def sync_ranges(self, start: date, end: date) -> None:
        for s, e in _chunks(start, end, self.source.range_chunk_days):
            for dataset, fn in self.source.ranges.items():
                ok, payload = self._call(dataset, f"{s}..{e}", fn, s, e)
                if ok:
                    db.put_range(self.conn, dataset, s, e, self.source.name, payload)
            self.conn.commit()

    def sync_activities(self, start: date, end: date) -> None:
        ok, items = self._call(
            "activities", f"{start}..{end}", self.source.list_activities,
            start.isoformat(), end.isoformat(),
        )
        if not ok:
            return
        for item in items or []:
            if "activityId" not in item:
                continue
            existing = self.conn.execute(
                "SELECT fit_parsed FROM activities WHERE activity_id=?",
                (int(item["activityId"]),),
            ).fetchone()
            activity_id = db.upsert_activity(self.conn, item)
            if existing is None:
                self.result.new_activities += 1
            if self.source.activity_details:
                self._fetch_details(activity_id)
            if not existing or not existing["fit_parsed"]:
                self._fetch_fit(activity_id)
            self.conn.commit()

    def _fetch_details(self, activity_id: int) -> None:
        stored = {row[0] for row in self.conn.execute(
            "SELECT kind FROM activity_details WHERE activity_id=?", (activity_id,),
        )}
        all_ok = True
        for kind, fn in self.source.activity_details.items():
            if kind in stored:
                continue
            ok, payload = self._call(f"activity.{kind}", str(activity_id), fn, activity_id)
            all_ok &= ok
            if ok:
                db.put_activity_detail(self.conn, activity_id, kind, payload)
        if all_ok:
            self.conn.execute(
                "UPDATE activities SET details_fetched=1 WHERE activity_id=? AND details_fetched=0",
                (activity_id,),
            )

    def _fetch_fit(self, activity_id: int) -> None:
        ok, data = self._call("activity.fit", str(activity_id), self.source.download_fit,
                              activity_id)
        if not ok or not data:
            return
        try:
            path = fit.retain_file(fit_dir(), activity_id, data) if self.store_fit_files else None
            fit.store(self.conn, activity_id, data, path=path)
        except Exception as exc:  # noqa: BLE001 - corrupt/unsupported file: log, keep going
            db.log(self.conn, self.result.run_id, self.source.name, "activity.fit_parse",
                   str(activity_id), "error", f"{type(exc).__name__}: {exc}"[:300])
            self.result.errors += 1

    def run(self, start: date, end: date) -> SyncResult:
        try:
            self.sync_activities(start, end)
            self.sync_daily(start, end)
            self.sync_ranges(start, end)
        except _Abort as exc:
            self.result.aborted = str(exc)
        self.conn.commit()
        return self.result


def _chunks(start: date, end: date, size: int | None) -> list[tuple[str, str]]:
    if size is None:
        return [(start.isoformat(), end.isoformat())]
    if size < 1:
        raise ValueError("Range chunk size must be positive.")
    out, cur = [], start
    while cur <= end:
        stop = min(cur + timedelta(days=size - 1), end)
        out.append((cur.isoformat(), stop.isoformat()))
        cur = stop + timedelta(days=1)
    return out


def _garminconnect(extras_only: bool) -> DataSource:
    from garmin_mcp.client import get_client
    from garmin_mcp.sources.garminconnect_source import GarminConnectSource

    return GarminConnectSource(get_client(), extras_only=extras_only)


def _personal_api() -> DataSource:
    from garmin_mcp.sources.personal_api import PersonalAPISource

    return PersonalAPISource()


SOURCE_CHOICES = ["both", "personal_api", "garminconnect"]


def run_sync(days: int = 7, since: str | None = None, source: str = "both",
             delay: float = 0.4) -> dict[str, Any]:
    """Sync one or both sources. In "both" mode the official API runs first and the
    unofficial source only adds what the official one lacks; a failure in one source is
    reported and never blocks the other."""
    database = db_path()
    if str(database) == ":memory:":
        return _run_sync(database, days, since, source, delay)

    database = Path(database).resolve()
    lock_path = database.with_name(database.name + ".sync.lock")
    lock_path.touch(mode=0o600, exist_ok=True)
    # Lock a separate empty SQLite file across the entire run. The archive itself
    # can commit partial results and remain readable while a Garmin call is pending.
    with closing(sqlite3.connect(lock_path, timeout=0)) as lock:
        try:
            lock.execute("BEGIN EXCLUSIVE")
        except sqlite3.OperationalError as exc:
            if exc.sqlite_errorcode != sqlite3.SQLITE_BUSY:
                raise
            return {"sources": {}, "full_sync_complete": False, "sync_in_progress": True}
        return _run_sync(database, days, since, source, delay)


def _run_sync(database: Path, days: int, since: str | None, source: str, delay: float) -> dict[str, Any]:
    plan: list[tuple[str, Any]] = {
        "both": [("personal_api", _personal_api), ("garminconnect", lambda: _garminconnect(True))],
        "personal_api": [("personal_api", _personal_api)],
        "garminconnect": [("garminconnect", lambda: _garminconnect(False))],
    }[source]
    out: dict[str, Any] = {"sources": {}}
    conn = db.connect(database)
    try:
        from garmin_mcp import athlete

        seeded = athlete.seed_from_file(conn)
        if seeded:
            out["settings_seeded"] = seeded
        end = today()
        start = date.fromisoformat(since) if since else end - timedelta(days=days - 1)
        if days < 1 or start > end:
            raise ValueError("Sync needs a positive day count and a start date no later than today.")
        out.update(start=start.isoformat(), end=end.isoformat())
        conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES ('sync_retry_required','1')")
        conn.commit()
        for name, factory in plan:
            try:
                src = factory()
            except Exception as exc:  # noqa: BLE001 - missing key / login: report, continue
                out["sources"][name] = {"skipped": f"{type(exc).__name__}: {exc}"[:300]}
                continue
            out["sources"][name] = Syncer(conn, src, delay=delay).run(start, end).as_dict()
        from garmin_mcp.normalize import rebuild

        out["tidy_tables"] = rebuild(conn)
        try:  # opt-in only; never blocks or fails a sync
            from garmin_mcp import weather_fetch

            out["weather"] = weather_fetch.fill_recent(conn)
        except Exception as exc:  # noqa: BLE001
            out["weather"] = {"error": f"{type(exc).__name__}"}
        complete = all("run_id" in r and not r.get("errors") and not r.get("aborted")
                       for r in out["sources"].values())
        complete = complete and not out["tidy_tables"].get("loads_error")
        out["full_sync_complete"] = complete
        if complete:
            conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES ('last_full_sync',?)",
                         (db.now_iso(),))
            conn.execute("DELETE FROM meta WHERE key='sync_retry_required'")
            conn.commit()
        out.update(_rebuild_dashboard(conn))
    finally:
        conn.close()
    return out


def _rebuild_dashboard(conn) -> dict[str, Any]:
    """Retry local rendering independently of Garmin fetches."""
    from garmin_mcp import dashboard
    from garmin_mcp.publish import publish_if_enabled

    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES ('dashboard_rebuild_pending','1')")
    conn.commit()
    try:
        path = dashboard.build(conn)
    except Exception as exc:  # noqa: BLE001 - a render failure must leave the database usable
        return {"dashboard_error": f"{type(exc).__name__}: {exc}"[:200]}
    conn.execute("DELETE FROM meta WHERE key='dashboard_rebuild_pending'")
    conn.commit()
    try:
        result = publish_if_enabled(path)
    except Exception as exc:  # noqa: BLE001 - a publishing failure must preserve the local build
        result = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:200]}
    return {"dashboard": str(path), "dashboard_publish": result}


def _refresh_dashboard_if_needed() -> dict[str, Any]:
    from garmin_mcp import dashboard, narrator
    from garmin_mcp.publish import publish_if_enabled

    conn = db.connect(db_path())
    try:
        pending = conn.execute(
            "SELECT 1 FROM meta WHERE key='dashboard_rebuild_pending'").fetchone()
        if pending or dashboard.needs_rebuild():
            return _rebuild_dashboard(conn)
        if narrator._sync_in_progress(conn):
            return {}
        path, _ = dashboard._snapshot_paths()
        if narrator.settings(conn)["enabled"] and (snapshot := dashboard._snapshot_id(path)):
            narrator.start_worker(conn, path, snapshot)
        result = publish_if_enabled(path)
        return {"dashboard_publish": result} if result["status"] in {"published", "error"} else {}
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Garmin data into the local database.")
    parser.add_argument("--days", type=int, default=7, help="days back from today (default 7)")
    parser.add_argument("--since", help="start date YYYY-MM-DD (overrides --days)")
    parser.add_argument("--source", default="both", choices=SOURCE_CHOICES,
                        help="both (default): official API + unofficial extras")
    parser.add_argument("--delay", type=float, default=0.4, help="seconds between API calls")
    parser.add_argument("--coverage", action="store_true", help="print stored-data coverage only")
    parser.add_argument("--force", action="store_true",
                        help="always do a full sync (skip the twice-a-day gate)")
    parser.add_argument("--no-update", action="store_true",
                        help="skip the automatic code update from GitHub main")
    args = parser.parse_args()
    if not args.no_update and not args.coverage:
        from garmin_mcp import autoupdate

        info = autoupdate.update()  # re-executes on new code if it changed
        print(json.dumps({"auto_update": info}))
        if info.get("requires_repair"):
            raise SystemExit(1)
    if args.coverage:
        conn = db.connect(db_path())
        print(json.dumps(db.coverage(conn), indent=2))
        return
    if not args.force and not args.since:
        decision = gate(source=args.source)
        print(json.dumps({"gate": decision}))
        if not decision["sync"]:
            result = _refresh_dashboard_if_needed()
            if result:
                print(json.dumps(result))
            return
    print(json.dumps(run_sync(args.days, args.since, args.source, args.delay), indent=2))


FULL_SYNC_EVERY_H = 11.0


def gate(now: datetime | None = None, probe=None, *, source: str = "both") -> dict[str, Any]:
    """Decide whether a scheduled run should do a full sync.

    You sync your phone ~twice a day, so: full sync when the last successful one is >= 11 h old;
    otherwise a single cheap probe of today's activity list using the selected source, and a
    sync only if it shows an activity we don't have yet. `refresh_data` and `--force` bypass this.
    """
    from datetime import UTC

    now = now or datetime.now(UTC)
    conn = db.connect(db_path())
    try:
        retry = conn.execute("SELECT value FROM meta WHERE key='sync_retry_required'").fetchone()
        if retry:
            return {"sync": True, "reason": "previous full sync did not complete"}
        row = conn.execute("SELECT value FROM meta WHERE key='last_full_sync'").fetchone()
        try:
            last = datetime.fromisoformat(row[0]) if row and row[0] else None
            if last is not None and (last.tzinfo is None or last > now):
                last = None
        except ValueError:
            last = None
        if last is None or (now - last).total_seconds() >= FULL_SYNC_EVERY_H * 3600:
            return {"sync": True, "reason": "last full sync >= 11 h ago" if last else
                    "no previous sync"}
        try:
            ids = probe() if probe is not None else _probe_today(source)
        except Exception as exc:  # noqa: BLE001 - probe failure: wait for the 11 h sync
            return {"sync": False, "reason": f"probe failed ({type(exc).__name__}); waiting"}
        known = {r[0] for r in conn.execute("SELECT activity_id FROM activities")}
        new = [i for i in ids if i not in known]
        return {"sync": bool(new), "reason": f"{len(new)} new activities" if new else
                f"nothing new; last full sync {(now - last).total_seconds() / 3600:.1f} h ago"}
    finally:
        conn.close()


def _probe_today(source: str = "both") -> list[int]:
    src = _garminconnect(False) if source == "garminconnect" else _personal_api()
    day = today().isoformat()
    return [int(a["activityId"]) for a in src.list_activities(day, day) if "activityId" in a]


if __name__ == "__main__":
    main()
