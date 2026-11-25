import json
from datetime import date
from pathlib import Path

from garmin_mcp import db, normalize, owner_acceptance


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
    assert report["pulse"] == {"normalized_matches_expected": True,
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
