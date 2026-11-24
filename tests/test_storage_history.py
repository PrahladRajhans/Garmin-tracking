import json

import pytest
from conftest import make_fit

from garmin_mcp import db, fit


def test_changed_garmin_payloads_keep_the_previous_readings(conn):
    day = "2026-11-24"
    first = {"reading": 1}
    second = {"reading": 2}
    summary = {"activityId": 9, "distance": 1000}
    for payload in (first, first, second):
        db.put_daily(conn, "sleep", day, "export", payload)
        db.put_range(conn, "trend", day, day, "garmin", payload)
        db.put_activity_detail(conn, 9, "split", payload)
        db.upsert_activity(conn, {**summary, **payload})
    history = {row["kind"]: json.loads(row["payload"])
               for row in conn.execute("SELECT kind, payload FROM raw_payload_history")}
    assert history == {"daily": first, "range": first, "detail": first, "summary": {**summary, **first}}
    assert db.coverage(conn)["raw_revisions"] == dict.fromkeys(history, 1)
    assert json.loads(conn.execute("SELECT payload FROM raw_daily").fetchone()[0]) == second


def test_fit_retries_preserve_original_bytes_and_previous_rows(conn, tmp_path, monkeypatch):
    activity_id = db.upsert_activity(conn, {"activityId": 9})
    original, replacement = make_fit(), make_fit(n=10)
    first_path = fit.retain_file(tmp_path, activity_id, original)
    revised_path = fit.retain_file(tmp_path, activity_id, replacement)
    assert first_path != revised_path and first_path.read_bytes() == original
    assert fit.retain_file(tmp_path, activity_id, replacement) == revised_path
    fit.store(conn, activity_id, original)

    def incomplete(database, aid, messages):
        database.execute("DELETE FROM fit_records WHERE activity_id=?", (aid,))
        raise ValueError("incomplete revision")

    monkeypatch.setattr(fit, "_store_messages", incomplete)
    with pytest.raises(ValueError, match="incomplete revision"):
        fit.store(conn, activity_id, replacement)
    assert conn.execute("SELECT COUNT(*) FROM fit_records").fetchone()[0] == 5
