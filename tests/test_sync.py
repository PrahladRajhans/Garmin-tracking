from datetime import date, timedelta

from conftest import make_fit

from garmin_mcp import db, sync
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


def test_each_source_fetches_only_missing_activity_details(conn):
    day = date.today()
    source = FakeSource(activities=[{"activityId": 42}])
    source.activity_details = {"pa_activity": lambda _: {"summary": True}}
    _syncer(conn, source).run(day, day)
    calls = []

    def weather(_):
        calls.append("weather")
        if calls.count("weather") == 1:
            raise RuntimeError("temporary failure")
        return {}

    source.activity_details = {"splits": lambda _: calls.append("splits") or {}, "weather": weather}
    assert _syncer(conn, source).run(day, day).errors == 1
    assert _syncer(conn, source).run(day, day).errors == 0
    assert _syncer(conn, source).run(day, day).errors == 0
    assert calls == ["splits", "weather", "weather"]
    assert {row[0] for row in conn.execute("SELECT kind FROM activity_details")} == {
        "pa_activity", "splits", "weather",
    }


def test_coverage_reports_stored_data(conn):
    today = date.today()
    _syncer(conn, FakeSource()).run(today - timedelta(days=2), today)
    cov = db.coverage(conn)
    sleep = next(d for d in cov["daily"] if d["dataset"] == "sleep")
    assert sleep["days"] == 3 and sleep["last_day"] == today.isoformat()
    assert cov["last_sync"]["errors"] == 0


class RateLimitError(Exception):
    status_code = 429
    response_text = '{"count":101,"limit":100,"retryInSeconds":7}'


def test_rate_limit_waits_and_retries(conn):
    src = FakeSource()
    attempts = {"n": 0}

    def flaky(day):
        attempts["n"] += 1
        if attempts["n"] <= 2:
            raise RateLimitError()
        return {"ok": day}

    src.daily = {"sleep": flaky}
    slept = []
    today = date.today()
    r = Syncer(conn, src, delay=0, store_fit_files=False, sleep=slept.append).run(today, today)
    assert r.errors == 0 and r.rate_limit_waits == 2 and slept == [8.0, 8.0]
    assert db.has_daily(conn, "sleep", today.isoformat())


def test_gate_full_sync_after_11h_and_probe_otherwise(conn, monkeypatch, tmp_path):
    from datetime import UTC, datetime, timedelta

    from garmin_mcp import sync as s

    monkeypatch.setattr(s, "db_path", lambda: tmp_path / "test.db")
    # no previous sync -> sync
    assert s.gate(probe=list)["sync"] is True
    db.log(conn, "r1", "x", "sleep", "d", "ok")
    conn.execute("INSERT INTO meta VALUES ('last_full_sync',?)", (db.now_iso(),))
    conn.commit()
    now = datetime.now(UTC)
    assert s.gate(now=now, probe=list)["sync"] is False          # recent, nothing new
    assert s.gate(now=now, probe=lambda: [999])["sync"] is True        # new activity
    assert s.gate(now=now + timedelta(hours=12), probe=list)["sync"] is True


def test_partial_sync_is_retried_despite_recent_successful_requests(conn, tmp_path, monkeypatch):
    from garmin_mcp import sync

    monkeypatch.setattr(sync, "db_path", lambda: tmp_path / "test.db")
    monkeypatch.setattr(sync, "_personal_api", lambda: FakeSource(fail={"hrv"}))
    conn.execute("INSERT INTO meta VALUES ('last_full_sync',?)", (db.now_iso(),))
    conn.commit()
    failed = sync.run_sync(days=1, source="personal_api", delay=0)
    assert failed["full_sync_complete"] is False
    assert sync.gate(probe=list)["sync"] is True
    monkeypatch.setattr(sync, "_personal_api", FakeSource)
    ok = sync.run_sync(days=1, source="personal_api", delay=0)
    assert ok["full_sync_complete"] is True
    assert sync.gate(probe=list)["sync"] is False


def test_request_log_alone_is_not_a_completed_sync(conn, tmp_path, monkeypatch):
    from garmin_mcp import sync

    monkeypatch.setattr(sync, "db_path", lambda: tmp_path / "test.db")
    db.log(conn, "r1", "x", "sleep", "today", "ok")
    conn.commit()
    assert sync.gate(probe=list)["sync"] is True


def test_derived_load_failure_keeps_sync_pending(conn, tmp_path, monkeypatch):
    from garmin_mcp import normalize, sync

    monkeypatch.setattr(sync, "db_path", lambda: tmp_path / "test.db")
    monkeypatch.setattr(sync, "_personal_api", FakeSource)
    monkeypatch.setattr(normalize, "rebuild", lambda c: {"loads_error": "failed"})
    result = sync.run_sync(days=1, source="personal_api", delay=0)
    assert result["full_sync_complete"] is False
    assert sync.gate(probe=list)["sync"] is True


def test_sync_and_probe_use_athlete_local_today(conn, tmp_path, monkeypatch):
    from garmin_mcp import sync

    local_day = date(2026, 11, 24)
    monkeypatch.setattr(sync, "db_path", lambda: tmp_path / "test.db")
    monkeypatch.setattr(sync, "today", lambda: local_day)
    src = FakeSource()
    monkeypatch.setattr(sync, "_personal_api", lambda: src)
    result = sync.run_sync(days=1, source="personal_api", delay=0)
    assert result["start"] == result["end"] == local_day.isoformat()
    assert {d for _, d in src.calls} == {local_day.isoformat()}
    spans = []
    src.list_activities = lambda s, e: spans.append((s, e)) or []
    assert sync._probe_today() == []
    assert spans == [(local_day.isoformat(), local_day.isoformat())]


def test_current_garmin_download_gate_can_refresh_old_html(monkeypatch, tmp_path, capsys):
    import sys

    from garmin_mcp import dashboard

    monkeypatch.setenv("GARMIN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GARMIN_DASHBOARD_PUBLISH", "")
    monkeypatch.setattr(sys, "argv", ["garmin-mcp-sync", "--no-update"])
    monkeypatch.setattr(sync, "gate", lambda: {"sync": False})
    drive = tmp_path / "Library/Mobile Documents/com~apple~CloudDocs"
    drive.mkdir(parents=True)
    monkeypatch.setattr(dashboard.Path, "home", classmethod(lambda cls: tmp_path))
    target = tmp_path / "dashboard" / "index.html"
    target.parent.mkdir()
    target.write_text(f'<meta name="garmin-dashboard" content="{dashboard.__version__}/old">')
    sync.main()
    assert "Dashboard built" in target.read_text() and not dashboard.needs_rebuild()
    assert (drive / "Garmin" / "dashboard.html").read_text() == target.read_text()
    assert "dashboard" in capsys.readouterr().out
    before = target.read_text()
    sync.main()
    assert target.read_text() == before


def test_failed_dashboard_build_retries_even_if_the_next_fetch_is_skipped(monkeypatch, tmp_path):
    from garmin_mcp import dashboard

    monkeypatch.setenv("GARMIN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GARMIN_DASHBOARD_PUBLISH", "")
    conn = db.connect(tmp_path / "garmin.db")
    dashboard.build(conn)
    build = dashboard.build

    def failed(_conn, **_options):
        raise RuntimeError("bad renderer")

    monkeypatch.setattr(dashboard, "build", failed)
    assert "dashboard_error" in sync._rebuild_dashboard(conn)
    assert conn.execute("SELECT 1 FROM meta WHERE key='dashboard_rebuild_pending'").fetchone()
    monkeypatch.setattr(dashboard, "build", build)
    assert "dashboard" in sync._refresh_dashboard_if_needed()
    assert not conn.execute("SELECT 1 FROM meta WHERE key='dashboard_rebuild_pending'").fetchone()
    conn.close()


def test_skipped_fetch_retries_narration_without_replacing_the_snapshot(monkeypatch, tmp_path):
    from garmin_mcp import dashboard, narrator

    monkeypatch.setenv("GARMIN_DATA_DIR", str(tmp_path))
    queued = []
    monkeypatch.setattr(narrator, "start_worker",
                        lambda _, path, stamp: queued.append((path, stamp)))
    conn = db.connect(tmp_path / "garmin.db")
    narrator.configure(conn, enable=True)
    path = dashboard.build(conn)
    with conn:
        conn.execute("DELETE FROM meta WHERE key='dashboard_rebuild_pending'")
    previous = dashboard._snapshot_id(path)
    assert sync._refresh_dashboard_if_needed() == {}
    assert queued == [(path, previous)]
    assert dashboard._snapshot_id(path) == previous
    conn.close()
