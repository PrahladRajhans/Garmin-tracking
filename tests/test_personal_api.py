from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from conftest import make_fit

from garmin_mcp.sources.personal_api import PersonalAPISource
from garmin_mcp.sync import Syncer, _chunks


class Unauthorized(Exception):
    status_code = 401


class FakeClient:
    """Mimics garmin_personal_api.GarminPersonalApiClient's method surface."""

    def __init__(self, n_activities=0, expire_once=False):
        self.token = "t0"
        self.n = n_activities
        self.expire_once = expire_once
        self.range_calls = []

    def update_bearer_token(self, t):
        self.token = t

    def _day(self, *a):
        if self.expire_once and self.token == "t0":
            raise Unauthorized()
        return {"args": [str(x) for x in a]}

    get_daily_summaries = get_daily_sleep = get_daily_hrv = _day
    get_daily_heart_rate = get_daily_spo2 = get_fitness_age = _day

    def _range(self, s, e):
        self.range_calls.append((s, e))
        return {"s": s, "e": e}

    get_daily_body_battery = get_daily_stress = get_daily_steps = _range
    get_daily_hydration = get_daily_vo2_max = get_weight_measurements = _range
    get_daily_hrv_summaries = get_daily_sleep_summaries = _range

    def get_activity(self, a):
        return {"activityId": a}

    def search_activities(self, start, limit, start_date, end_date):
        ids = list(range(1, self.n + 1))[start:start + limit]
        return [{"activityId": i, "activityType": {"typeKey": "running"}} for i in ids]

    def download_activity(self, a):
        return make_fit(n=3)


class FakeAuth:
    def __init__(self):
        self.calls = 0

    def obtain_token(self, key, force_refresh=False):
        self.calls += 1
        return SimpleNamespace(access_token=f"t{self.calls}")


def test_chunks_respect_history_caps():
    c = _chunks(date(2026, 1, 1), date(2026, 3, 1), 28)
    assert c[0] == ("2026-01-01", "2026-01-28")
    assert c[-1][1] == "2026-03-01" and len(c) == 3
    assert _chunks(date(2026, 1, 1), date(2026, 1, 5), None) == [("2026-01-01", "2026-01-05")]


def test_sync_with_personal_api(conn):
    client = FakeClient(n_activities=150)  # forces pagination (page size 100)
    src = PersonalAPISource("k", client=client, authenticator=FakeAuth())
    today = date.today()
    r = Syncer(conn, src, delay=0, store_fit_files=False).run(today - timedelta(days=40), today)
    assert r.errors == 0 and r.new_activities == 150
    assert conn.execute("SELECT COUNT(*) FROM raw_daily WHERE dataset='pa_hrv'").fetchone()[0] == 41
    spans = {(s, e) for s, e in client.range_calls}
    assert all((date.fromisoformat(e) - date.fromisoformat(s)).days < 28 for s, e in spans)
    assert conn.execute("SELECT COUNT(*) FROM activities WHERE fit_parsed=1").fetchone()[0] == 150


def test_expired_token_is_refreshed_once(conn):
    auth = FakeAuth()
    client = FakeClient(expire_once=True)
    src = PersonalAPISource("k", client=client, authenticator=auth)
    today = date.today()
    r = Syncer(conn, src, delay=0, store_fit_files=False).run(today, today)
    assert r.errors == 0 and auth.calls == 1 and client.token == "t1"


def test_empty_optional_env_key_uses_the_sdk_file_resolver(monkeypatch):
    import garmin_personal_api

    seen = []

    def resolve(key, *, env):
        seen.append((key, env))
        return "fixture-key"

    monkeypatch.setenv("GARMIN_PERSONAL_API_KEY", "  ")
    monkeypatch.setattr(garmin_personal_api, "resolve_api_key", resolve)
    monkeypatch.setattr(garmin_personal_api, "GarminPersonalApiClient", lambda _: FakeClient())
    PersonalAPISource(authenticator=FakeAuth())
    assert seen == [(None, {})]

@pytest.mark.parametrize("size", [0, -1])
def test_invalid_chunks_fail_instead_of_looping(size):
    with pytest.raises(ValueError, match="positive"):
        _chunks(date(2026, 1, 1), date(2026, 2, 1), size)


def test_repeated_activity_page_is_rejected():
    client = FakeClient(n_activities=100)
    page = client.search_activities(0, 100, "2026-01-01", "2026-02-01")
    client.search_activities = lambda **kwargs: page
    src = PersonalAPISource("k", client=client)
    with pytest.raises(RuntimeError, match="repeated"):
        src.list_activities("2026-01-01", "2026-02-01")


def test_unexpected_activity_response_marks_sync_incomplete(conn):
    client = FakeClient()
    client.search_activities = lambda **_: {"unexpected": []}
    source = PersonalAPISource("k", client=client)
    day = date.today()
    result = Syncer(conn, source, delay=0, store_fit_files=False).run(day, day)
    assert result.errors == 1
    assert any("unexpected response" in message for message in result.error_samples)


def test_never_ending_pagination_has_a_hard_limit(monkeypatch):
    from garmin_mcp.sources import personal_api

    monkeypatch.setattr(personal_api, "MAX_ACTIVITY_PAGES", 2)
    src = PersonalAPISource("k", client=FakeClient(n_activities=300))
    with pytest.raises(RuntimeError, match="request limit"):
        src.list_activities("2026-01-01", "2026-02-01")
