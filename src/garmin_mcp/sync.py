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
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from garmin_mcp import db, fit
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
        fresh_from = date.today() - timedelta(days=self.refresh_days)
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
                "SELECT details_fetched, fit_parsed FROM activities WHERE activity_id=?",
                (int(item["activityId"]),),
            ).fetchone()
            activity_id = db.upsert_activity(self.conn, item)
            if existing is None:
                self.result.new_activities += 1
            if not existing or not existing["details_fetched"]:
                self._fetch_details(activity_id)
            if not existing or not existing["fit_parsed"]:
                self._fetch_fit(activity_id)
            self.conn.commit()

    def _fetch_details(self, activity_id: int) -> None:
        all_ok = True
        for kind, fn in self.source.activity_details.items():
            ok, payload = self._call(f"activity.{kind}", str(activity_id), fn, activity_id)
            all_ok &= ok
            if ok:
                db.put_activity_detail(self.conn, activity_id, kind, payload)
        if all_ok:
            self.conn.execute(
                "UPDATE activities SET details_fetched=1 WHERE activity_id=?", (activity_id,)
            )

    def _fetch_fit(self, activity_id: int) -> None:
        ok, data = self._call("activity.fit", str(activity_id), self.source.download_fit,
                              activity_id)
        if not ok or not data:
            return
        path = None
        if self.store_fit_files:
            path = fit_dir() / f"{activity_id}.fit"
            path.write_bytes(data)
            self.conn.execute(
                "UPDATE activities SET fit_path=? WHERE activity_id=?", (str(path), activity_id)
            )
        try:
            fit.store(self.conn, activity_id, data)
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
    if not size:
        return [(start.isoformat(), end.isoformat())]
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
    end = date.today()
    start = date.fromisoformat(since) if since else end - timedelta(days=days - 1)
    plan: list[tuple[str, Any]] = {
        "both": [("personal_api", _personal_api), ("garminconnect", lambda: _garminconnect(True))],
        "personal_api": [("personal_api", _personal_api)],
        "garminconnect": [("garminconnect", lambda: _garminconnect(False))],
    }[source]
    out: dict[str, Any] = {"start": start.isoformat(), "end": end.isoformat(), "sources": {}}
    conn = db.connect(db_path())
    try:
        for name, factory in plan:
            try:
                src = factory()
            except Exception as exc:  # noqa: BLE001 - missing key / login: report, continue
                out["sources"][name] = {"skipped": f"{type(exc).__name__}: {exc}"[:300]}
                continue
            out["sources"][name] = Syncer(conn, src, delay=delay).run(start, end).as_dict()
        from garmin_mcp.normalize import rebuild

        out["tidy_tables"] = rebuild(conn)
    finally:
        conn.close()
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Garmin data into the local database.")
    parser.add_argument("--days", type=int, default=7, help="days back from today (default 7)")
    parser.add_argument("--since", help="start date YYYY-MM-DD (overrides --days)")
    parser.add_argument("--source", default="both", choices=SOURCE_CHOICES,
                        help="both (default): official API + unofficial extras")
    parser.add_argument("--delay", type=float, default=0.4, help="seconds between API calls")
    parser.add_argument("--coverage", action="store_true", help="print stored-data coverage only")
    args = parser.parse_args()
    if args.coverage:
        conn = db.connect(db_path())
        print(json.dumps(db.coverage(conn), indent=2))
        return
    print(json.dumps(run_sync(args.days, args.since, args.source, args.delay), indent=2))


if __name__ == "__main__":
    main()
