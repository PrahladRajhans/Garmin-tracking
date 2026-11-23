from datetime import date, timedelta

from conftest import make_fit

from garmin_mcp import db
from garmin_mcp.sources.base import DataSource
from garmin_mcp.sync import Syncer


class FakeSource(DataSource):
    name = "fake"

    def __init__(self, fail=(), activities=None):
        super().__init__()
        self.calls = []
        self.fail = set(fail)

        def daily_fn(name):
            def fn(day):
                self.calls.append((name, day))
                if name in self.fail:
                    raise RuntimeError("boom")
                return {"day": day, "v": 1}
            return fn

        self.daily = {"sleep": daily_fn("sleep"), "hrv": daily_fn("hrv")}
        self.ranges = {"race_predictions": lambda s, e: {"s": s, "e": e}}
        self.activity_details = {"splits": lambda a: {"laps": [a]}}
        self._activities = activities or []

    def list_activities(self, start, end):
        return self._activities

    def download_fit(self, activity_id):
        return make_fit(n=4)


def _syncer(conn, src):
    return Syncer(conn, src, delay=0, store_fit_files=False)


def test_daily_skips_stored_old_days_but_refreshes_recent(conn):
    today = date.today()
    start = today - timedelta(days=5)
    src = FakeSource()
    _syncer(conn, src).run(start, today)
    assert len(src.calls) == 12  # 6 days x 2 datasets
    src.calls.clear()
    result = _syncer(conn, src).run(start, today)
    refetched = {d for _, d in src.calls}
    assert refetched == {(today - timedelta(days=i)).isoformat() for i in range(3)}
    assert result.skipped == 6


def test_failing_dataset_does_not_block_others(conn):
    today = date.today()
    result = _syncer(conn, FakeSource(fail={"hrv"})).run(today - timedelta(days=1), today)
    assert result.errors == 2 and result.aborted is None
    assert db.has_daily(conn, "sleep", today.isoformat())
    assert not db.has_daily(conn, "hrv", today.isoformat())
    errs = conn.execute("SELECT COUNT(*) FROM sync_log WHERE status='error'").fetchone()[0]
    assert errs == 2


def test_aborts_after_consecutive_errors(conn):
    today = date.today()
    s = Syncer(conn, FakeSource(fail={"sleep", "hrv"}), delay=0, max_consecutive_errors=3)
    result = s.run(today - timedelta(days=10), today)
    assert result.aborted and "3 consecutive errors" in result.aborted


def test_activities_details_and_fit_fetched_once(conn):
    acts = [{"activityId": 42, "activityName": "Easy run", "activityType": {"typeKey": "running"},
             "startTimeLocal": "2026-11-20 07:00:00", "distance": 8000.0, "duration": 2700.0,
             "averageHR": 142, "aerobicTrainingEffect": 2.8}]
    today = date.today()
    r1 = _syncer(conn, FakeSource(activities=acts)).run(today, today)
    assert r1.new_activities == 1
    row = conn.execute("SELECT * FROM activities WHERE activity_id=42").fetchone()
    assert row["type"] == "running" and row["distance_m"] == 8000.0 and row["aerobic_te"] == 2.8
    assert row["details_fetched"] == 1 and row["fit_parsed"] == 1
    assert conn.execute("SELECT COUNT(*) FROM fit_records").fetchone()[0] == 4
    r2 = _syncer(conn, FakeSource(activities=acts)).run(today, today)
    assert r2.new_activities == 0
    n_fit_calls = conn.execute(
        "SELECT COUNT(*) FROM sync_log WHERE dataset='activity.fit'").fetchone()[0]
    assert n_fit_calls == 1


def test_coverage_reports_stored_data(conn):
    today = date.today()
    _syncer(conn, FakeSource()).run(today - timedelta(days=2), today)
    cov = db.coverage(conn)
    sleep = next(d for d in cov["daily"] if d["dataset"] == "sleep")
    assert sleep["days"] == 3 and sleep["last_day"] == today.isoformat()
    assert cov["last_sync"]["errors"] == 0
