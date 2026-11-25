import json
from datetime import date
from pathlib import Path

import pytest

from garmin_mcp import dashboard, dashboard_history, db, normalize, owner_acceptance


def test_owner_report_matches_only_dated_values_and_keeps_archive_read_only(conn, monkeypatch):
    for year in range(2023, 2027):
        for month in range(1, 13):
            if (year, month) > (2026, 11):
                break
            day = f"{year}-{month:02}-01"
            db.put_daily(conn, "ex_daily_summary", day, "export", {"calendarDate": day, "totalSteps": 100})
    day = "2026-11-02"
    db.put_daily(conn, "ex_daily_summary", day, "export",
                 {"calendarDate": day, "restingHeartRate": 44, "totalSteps": 100})
    db.put_daily(conn, "user_summary", day, "connect", {"calendarDate": day, "currentDayRestingHeartRate": 45})
    db.put_range(conn, "pa_daily_summary", day, day, "personal_api",
                 [{"calendarDate": day, "heartRate": {"restingValue": 44, "maxValue": 177}}])
    normalize.rebuild(conn)

    calls = []

    def request(method, path, _deadline, body=None):
        calls.append((method, path, body))
        return {"/api/status": {"cloud": {"disabled": True}},
                "/api/tags": {"models": [{"name": owner_acceptance.narrator.DEFAULT_MODEL}]},
                "/api/show": {"capabilities": ["completion", "thinking"]}}[path]

    monkeypatch.setattr(owner_acceptance.narrator, "_request", request)
    path = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    before = path.read_bytes()
    report = owner_acceptance.report(path, date.fromisoformat(day))
    assert path.read_bytes() == before
    assert report["pulse"] == {"normalized_available": True, "normalized_matches_expected": True,
                               "dated_sources_checked": ["pa_daily_summary", "user_summary"],
                               "dated_sources_matching": ["pa_daily_summary"],
                               "dated_sources_disagree": True}
    assert report["recent_36_calendar_months"]["recorded_daily_months"] == 36
    assert report["ollama"]["service"] == "ready" and report["ollama"]["supports_thinking"]
    assert [call[1] for call in calls] == ["/api/status", "/api/tags", "/api/show"]
    assert calls[-1][-1] == {"model": owner_acceptance.narrator.DEFAULT_MODEL + ":local"}
    rendered = json.dumps(report)
    assert day not in rendered and str(path) not in rendered and "177" not in rendered


def test_missing_archive_does_not_contact_ollama(tmp_path, monkeypatch):
    def fail(*args):
        raise AssertionError("Ollama must not be called for a missing archive")

    monkeypatch.setattr(owner_acceptance.narrator, "_request", fail)
    report = owner_acceptance.report(tmp_path / "missing.db", date(2026, 11, 2))
    assert report["archive_available"] is False


def test_failed_replay_returns_a_shareable_status(conn, monkeypatch):
    normalize.rebuild(conn)
    path = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    monkeypatch.setattr(owner_acceptance, "_ollama_check", lambda _: {})

    def failed_replay(_):
        raise OSError(f"Failed to read {path}")

    monkeypatch.setattr(owner_acceptance, "replay_dashboard", failed_replay)
    report = owner_acceptance.report(path, date(2026, 11, 2), replay=True)
    assert report["archive_available"] and not report["dashboard_replay"]["ok"]
    assert not report["pulse"]["normalized_available"]
    assert str(path) not in json.dumps(report)


@pytest.mark.parametrize("daily_day", [None, "2026-10-19"])
def test_archive_coverage_uses_sleep_and_hrv_after_the_last_daily_record(conn, daily_day):
    normalize.rebuild(conn)
    if daily_day:
        conn.execute("INSERT INTO daily(day,steps) VALUES (?,100)", (daily_day,))
    conn.execute("INSERT INTO sleep(day,sleep_s) VALUES ('2026-11-02',25200)")
    conn.execute("INSERT INTO hrv(day,last_night_avg) VALUES ('2026-12-02',50)")
    conn.execute("INSERT INTO sleep(day,sleep_s) VALUES ('2023-12-02',25200)")

    coverage = owner_acceptance._archive_coverage(conn)

    assert coverage["recorded_daily_months"] == int(daily_day is not None)
    assert coverage["signal_days"]["sleep_h"] == 1  # the December 2023 reading is outside 36 months
    assert coverage["signal_days"]["hrv"] == 1


def test_dashboard_and_acceptance_share_dated_resting_pulse_and_conflicts(conn):
    day = "2026-11-02"
    for bpm, first in ((44, "2026-11-01"), (47, day)):
        db.put_range(conn, "pa_daily_summary", first, day, "personal_api",
                     [{"calendarDate": day, "heartRate": {"restingValue": bpm}}])
    db.put_daily(conn, "ex_daily_summary", day, "export",
                 {"calendarDate": day, "restingHeartRate": 44})
    normalize.rebuild(conn)
    value = conn.execute("SELECT resting_hr FROM daily WHERE day=?", (day,)).fetchone()[0]
    rows = {day: {"daily": {"resting_hr": value}}}

    checks = dashboard_history.resting_pulse_checks(conn, rows, day, day, None, {})
    html = dashboard._resting_pulse_card(checks[day])
    assert "Garmin Personal API" in html and "44 bpm, 47 bpm" in html
    assert "different estimates" in html and "Garmin export" not in html
    report = owner_acceptance._pulse_check(conn, date.fromisoformat(day), 44)
    assert report["dated_sources_checked"] == ["pa_daily_summary"]
    assert report["dated_sources_matching"] == [] and report["dated_sources_disagree"]
