import io
import zipfile

from conftest import make_fit

from garmin_mcp import db, fit
from garmin_mcp.sources.garminconnect_source import extract_fit


def test_store_fit_streams(conn):
    db.upsert_activity(conn, {"activityId": 1, "activityType": {"typeKey": "running"}})
    counts = fit.store(conn, 1, make_fit(n=5))
    assert counts == {"records": 5, "laps": 1, "rr_intervals": 3}
    row = conn.execute("SELECT * FROM fit_records WHERE activity_id=1 ORDER BY ts").fetchone()
    assert row["heart_rate"] == 140 and row["speed"] == 3.2 and row["power"] == 260
    assert 51.3 < row["lat"] < 51.4  # semicircles converted to degrees
    assert conn.execute("SELECT sport FROM fit_sessions").fetchone()["sport"] == "running"
    assert conn.execute("SELECT fit_parsed FROM activities").fetchone()[0] == 1


def test_store_fit_is_idempotent(conn):
    db.upsert_activity(conn, {"activityId": 1})
    fit.store(conn, 1, make_fit(n=3))
    fit.store(conn, 1, make_fit(n=3))
    assert conn.execute("SELECT COUNT(*) FROM fit_records").fetchone()[0] == 3


def test_extract_fit_from_zip_and_raw():
    raw = make_fit(n=2)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("123_ACTIVITY.fit", raw)
    assert extract_fit(buf.getvalue()) == raw
    assert extract_fit(raw) == raw
    assert extract_fit(None) is None
