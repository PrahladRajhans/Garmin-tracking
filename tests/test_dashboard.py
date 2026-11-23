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
    assert "<title>Garmin Health</title>" in text
    assert "<script" not in text and "http" not in text.split("<body>")[1][:200]  # offline
    for page in ("today", "sleep", "recovery", "training", "running", "body", "patterns"):
        assert f'id="{page}"' in text and f'href="#{page}"' in text
    assert "#today:not(:target)" in text  # home hides only when another page is targeted


def test_gauge_and_charts_render():
    from garmin_mcp import running

    g = dashboard.gauge(166.6, running.GAUGES["cadence_spm"], 145, 192, marker2=163.2)
    assert g.count('class="g-') == 5 and 'class="mk2"' in g
    c = dashboard.line_chart([("2026-11-01", 50.0), ("2026-11-02", 52.0)], " ms",
                             band=(48.0, 53.0))
    assert "<path" in c and 'class="band"' in c and "<title>" in c
    assert "Not enough" in dashboard.line_chart([("2026-11-01", 1.0)])
    b = dashboard.bar_chart([("a", 1.0), ("b", 2.0)], ref=1.5, ref_label="need")
    assert b.count('class="bar') == 2 and "need" in b
    assert dashboard._clock(25.5) == "01:30"
