from conftest import make_fit

from garmin_mcp import dashboard, db
from garmin_mcp.normalize import rebuild


def test_dashboard_builds_on_small_database(conn, tmp_path):
    db.put_daily(conn, "ex_daily_summary", "2026-11-20", "export",
                 {"calendarDate": "2026-11-20", "totalSteps": 8000, "restingHeartRate": 46})
    db.upsert_activity(conn, {"activityId": 1, "activityType": {"typeKey": "running"},
                              "startTimeLocal": "2026-11-20 07:00:00", "duration": 1800.0,
                              "distance": 5000.0, "averageHR": 150})
    from garmin_mcp import fit

    fit.store(conn, 1, make_fit(n=30))
    conn.commit()
    rebuild(conn)
    path = dashboard.build(conn, tmp_path)
    text = path.read_text()
    assert "<title>Garmin Health Dashboard</title>" in text
    assert "cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1" in text
    assert "const D=" in text and "Associations are not causes" in text
