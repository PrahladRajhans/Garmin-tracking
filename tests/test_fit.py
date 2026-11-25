import io
import zipfile

from conftest import make_fit

from garmin_mcp import db, fit
from garmin_mcp.sources.garminconnect_source import extract_fit


def test_store_fit_streams(conn):
    db.upsert_activity(conn, {"activityId": 1, "activityType": {"typeKey": "running"}})
    counts = fit.store(conn, 1, make_fit(n=5))
    assert counts == {"records": 5, "laps": 1, "rr_intervals": 3, "lengths": 0, "sets": 0}
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


def test_running_cadence_keeps_the_fractional_half_step(conn):
    """FIT splits one-foot cadence into a whole number and a fraction; the watch averages both."""
    from datetime import UTC, datetime, timedelta

    from garmin_fit_sdk import Encoder, Profile

    from garmin_mcp import coaching, insights

    mn, t0 = Profile["mesg_num"], datetime(2026, 11, 1, 7, 0, tzinfo=UTC)
    e = Encoder()
    e.write_mesg({"mesg_num": mn["FILE_ID"], "type": "activity", "manufacturer": "garmin", "time_created": t0})
    for i in range(200):
        e.write_mesg({"mesg_num": mn["RECORD"], "timestamp": t0 + timedelta(seconds=i), "enhanced_speed": 3.0,
                      "cadence": 86, "fractional_cadence": 0.5, "distance": 3.0 * i})
    e.write_mesg({"mesg_num": mn["LAP"], "timestamp": t0 + timedelta(seconds=199), "start_time": t0,
                  "total_timer_time": 199.0, "total_distance": 597.0, "avg_cadence": 86,
                  "avg_fractional_cadence": 0.5})
    db.upsert_activity(conn, {"activityId": 1, "activityType": {"typeKey": "running"},
                              "startTimeLocal": "2026-11-01 07:00:00"})
    fit.store(conn, 1, e.close())

    assert coaching.run_metrics(conn, 1)["cadence_spm"] == 173.0
    assert coaching.activity_stream(conn, 1)["stream"][0]["cadence_spm"] == 173.0
    detail = insights.activity_detail(conn, 1)
    assert detail["laps"][0]["avg_cadence_spm"] == 173.0
    assert detail["running_form_from_fit"]["avg_cadence_spm"] == 173.0
