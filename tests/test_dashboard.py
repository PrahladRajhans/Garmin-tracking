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
    assert text.count("<script>") == 1 and "<script src" not in text
    assert "View values" not in text and "Today’s readings" in text
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
    assert dashboard.line_chart([("2026-11-01", 1.0)]).count(" data-point ") == 1
    assert "No measurements" in dashboard.line_chart([("2026-11-01", None)])
    b = dashboard.bar_chart([("a", 1.0), ("b", 2.0)], ref=1.5, ref_label="need")
    assert b.count('class="bar') == 2 and "need" in b
    assert dashboard._clock(25.5) == "01:30"


def test_run_without_history_does_not_claim_normal_form_or_aerobic_base():
    from garmin_mcp import running

    advice = running.suggestions({"decoupling_pct": -10}, {})
    assert "Not enough comparable earlier runs" in advice[0]
    assert "in line with your usual" not in advice[0]


def test_empty_database_builds_honest_dashboard_without_fake_scores(conn, tmp_path):
    for normalized in (False, True):
        if normalized:
            rebuild(conn)
        path = dashboard.build(conn, tmp_path / "empty")
        text = path.read_text()
        assert "No Garmin data is available yet" in text and "data-chart=" not in text
        assert 'id="patterns"' in text and 'href="#patterns"' in text
        assert 'class="dial-num"' not in text and "planned training is fine" not in text


def test_date_charts_preserve_elapsed_time_and_have_exact_values():
    import math
    import re

    text = dashboard.line_chart([("2026-01-11", 3.), ("2026-01-01", 1.), ("2026-01-02", 2.)])
    xs = [float(x) for x in re.findall(r'<circle cx="([\d.]+)"[^>]*data-point', text)]
    assert len(xs) == 3 and math.isclose((xs[1] - xs[0]) / (xs[2] - xs[0]), 0.1)
    assert 'data-title="2026-01-02" data-value="2"' in text and "View values" not in text


def test_dashboard_inline_script_matches_document_policy():
    import base64
    import hashlib

    text = dashboard.render({"available": False, "reason": "No stored values"})
    script = text.split("<script>", 1)[1].split("</script>", 1)[0]
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    assert f"sha256-{digest}" in text


def test_missing_bar_keeps_remaining_status_colour_and_escapes_labels():
    text = dashboard.bar_chart([("missing", None), ("<unsafe>", 34.)], tones=["muted", "bad"])
    assert 'class="bar bad"' in text and 'class="bar muted"' not in text
    assert "<unsafe>" not in text and "&lt;unsafe&gt;" in text


def test_failed_atomic_write_preserves_previous_file_and_cleans_temp(tmp_path, monkeypatch):
    import pytest

    path = tmp_path / "index.html"
    path.write_text("previous complete dashboard")

    def fail(*args):
        raise OSError("replace failed")

    monkeypatch.setattr(dashboard.os, "replace", fail)
    with pytest.raises(OSError):
        dashboard._atomic_write(path, "new dashboard")
    assert path.read_text() == "previous complete dashboard"
    assert not list(tmp_path.glob(".dashboard-*"))


def test_icloud_failure_keeps_local_build(conn, tmp_path, monkeypatch):
    import pytest

    drive = tmp_path / "Library/Mobile Documents/com~apple~CloudDocs"
    drive.mkdir(parents=True)
    monkeypatch.setattr(dashboard.Path, "home", classmethod(lambda cls: tmp_path))
    real_write = dashboard._atomic_write

    def write(path, content):
        if drive in path.parents:
            raise PermissionError("iCloud unavailable")
        return real_write(path, content)

    monkeypatch.setattr(dashboard, "_atomic_write", write)
    with pytest.warns(RuntimeWarning, match="local dashboard is available"):
        path = dashboard.build(conn)
    assert path.is_file() and "No Garmin data" in path.read_text()


def test_temporary_dashboard_does_not_overwrite_icloud(conn, tmp_path, monkeypatch):
    drive = tmp_path / "Library/Mobile Documents/com~apple~CloudDocs/Garmin"
    drive.mkdir(parents=True)
    snapshot = drive / "dashboard.html"
    snapshot.write_text("live dashboard")
    monkeypatch.setattr(dashboard.Path, "home", classmethod(lambda cls: tmp_path))
    assert dashboard.build(conn, tmp_path / "temporary").is_file()
    assert snapshot.read_text() == "live dashboard"


def test_new_health_files_are_owner_only_on_posix(conn, tmp_path):
    import os
    import stat

    import pytest

    if os.name != "posix":
        pytest.skip("POSIX file mode check")
    path = dashboard.build(conn, tmp_path / "private-dashboard")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    database = tmp_path / "private.db"
    db.connect(database).close()
    assert stat.S_IMODE(database.stat().st_mode) == 0o600
    path.chmod(0o640)
    dashboard._atomic_write(path, "updated")
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


def test_dashboard_keeps_older_summaries_and_hides_sparse_research_cards(conn, tmp_path):
    for day in ("2026-11-23", "2026-10-25", "2026-10-24"):
        db.put_daily(conn, "ex_daily_summary", day, "export",
                     {"calendarDate": day, "totalSteps": 8000, "restingHeartRate": 46})
    conn.execute("INSERT INTO meta VALUES ('last_full_sync','2026-10-24T03:00:00+00:00')")
    conn.commit()
    rebuild(conn)
    html = dashboard.build(conn, tmp_path).read_text()
    assert 'id="day-2026-10-25"' in html and 'id="day-2026-10-24"' not in html
    assert "Sat, 24 Oct 2026" in html and "46 bpm resting" in html
    assert "Do readiness scores line up with your runs?" not in html
    assert "Last complete sync 24 Oct 2026" in html and "Code v" in html



def test_patterns_draw_only_qualifying_pairs():
    pair = {"x": "trimp", "y": "hrv", "lag_days": 1, "r": 0.45, "r_ci95": [0.1, 0.7],
            "n": 31, "slope": 0.08, "points": [("2026-11-01", 0, 0), ("2026-11-02", 1, 2),
                                            ("2026-11-03", -1, -0.1)],
            "statement": "For you, 50 TRIMP more training load is associated with an HRV change"}
    html = dashboard.page_patterns({"explore": {"pairs": [
        {**pair, "notable": True}, {**pair, "x": "bedtime_h", "notable": False}],
        "eligible": 2, "notable": 1}})
    assert html.count('data-chart="scatter"') == 2  # phone and desktop drawings of one chart
    assert "1 had enough data but showed no clear pattern." in html
    assert "TRIMP" not in html and "Bedtime" not in html


def test_today_leads_with_action_and_recovery_history_is_in_details(conn):
    from datetime import UTC, datetime

    day = datetime.now(UTC).date().isoformat()
    db.put_daily(conn, "ex_daily_summary", day, "export",
                 {"calendarDate": day, "totalSteps": 1000})
    rebuild(conn)
    d = dashboard.collect(conn, day)
    d["history"][0]["recovery"] = 49
    html = dashboard.render(d)
    today = html.split('id="today"', 1)[1].split("</article>", 1)[0]
    recovery_page = html.split('id="recovery"', 1)[1].split("</article>", 1)[0]
    assert today.index("Start gently if you feel well") < today.index("Next seven days")
    assert 'data-chart=' not in today and "Still learning" in today and "of 4" not in today
    assert '<summary>Last 14 days</summary>' in recovery_page
    assert html.split('<nav class="top"', 1)[1].split("</nav>", 1)[0].count("<a href=") == 5


def test_history_gives_an_intraday_only_record_a_real_target(conn):
    from datetime import UTC, datetime

    day = "2026-11-23"
    stamp = int(datetime(2026, 11, 23, 8, tzinfo=UTC).timestamp() * 1000)
    db.put_daily(conn, "pa_heart_rate", day, "personal_api", {"heartRateValues": [[stamp, 66]]})
    db.put_daily(conn, "ex_daily_summary", "2026-11-22", "export", {"calendarDate": "2026-11-22", "totalSteps": 100})
    rebuild(conn)
    html = dashboard.render(dashboard.collect(conn, day))
    assert f'href="#day-{day}"' in html and f'id="day-{day}"' in html
    intraday = html.split(f'id="day-{day}"', 1)[1].split("</main>", 1)[0]
    assert "Heart rate during the day" in intraday and "No usable readings" not in intraday


def test_workout_pace_stays_visible_when_secondary_readings_are_missing():
    rows = [{"t_s": 0, "pace": 340, "hr": 140}, {"t_s": 10, "pace": 330},
            {"t_s": 20, "pace": 345, "hr": 141}, {"t_s": 30, "pace": 337, "hr": 142}]
    chart = dashboard._paired_chart(
        rows, ("pace", "Pace", "Pace (min/km)", lambda v: str(v)),
        (("hr", "Heart rate", "Heart rate (bpm)", lambda v: f"{v} bpm"),
         ("altitude_m", "Elevation", "Elevation (m)", str)), 10,
        faster_at_top=True)
    assert chart.count("data-point ") == 4
    assert 'class="chart-interaction chart-dense"' in chart
    assert 'data-overlay-track="hr"' in chart and 'data-overlay-track="altitude_m"' not in chart
    assert "null" in chart and "data-open-height" not in chart
    assert "Pace (min/km)" in chart and "Heart rate (bpm)" in chart
    assert "Compare with" in chart and "Change from run median" not in chart


def test_charts_use_recorded_bands_and_label_color_status():
    assert dashboard._trace_rating("cadence_spm", 153, ()) == (
        "orange", "Garmin band: below average")
    assert dashboard._trace_rating("hr", 120, [120, 140, 160]) == (
        "green", "Recorded heart-rate band 2")
    assert dashboard._trace_rating("hr", 120, ()) is None
    assert dashboard._hr_zone_bounds("[140, 120]") == []
    line = dashboard.line_chart([("a", 4), ("b", 7), ("c", 10)], band=(5, 9), rate_range=True)
    assert all(label in line for label in ("below usual", "within usual range", "above usual"))
    bars = dashboard.bar_chart([("a", 5), ("b", 8)], ref=8, rate_goal=True)
    assert "below goal" in bars and "met goal" in bars


def test_archive_replay_validates_months_without_saving_or_editing_source(conn):
    from pathlib import Path

    from garmin_mcp import db, normalize, verify

    for day in ("2026-01-03", "2026-02-04"):
        db.put_daily(conn, "ex_daily_summary", day, "export",
                     {"calendarDate": day, "totalSteps": 5000})
    conn.commit()
    normalize.rebuild(conn)
    conn.commit()
    path = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    before = path.read_bytes()
    report = verify.replay_dashboard(path)
    assert report["ok"] and report["months_sampled"] == 2
    assert path.read_bytes() == before
    assert not (path.parent / "dashboard").exists()


def test_overlay_separates_series_style_from_reference_bands():
    chart = dashboard._paired_chart(
        [{"t_s": i * 5, "pace": 330 + i, "cadence_spm": value, "power_w": 0}
         for i, value in enumerate((150, 160, 170, 170))],
        ("pace", "Pace", "Pace (min/km)", str),
        (("cadence_spm", "Cadence", "Cadence (steps/min)", str),
         ("power_w", "Power", "Power (W)", str)), 5,
    )
    for colour in ("green", "orange", "red"):
        assert f"zone-line zone-{colour} overlay-line" in chart
    assert 'data-overlay-track="power_w"' in chart
    assert 'class="ln s2 overlay-line"' in chart
    assert "Dashed · right axis" in chart and "Garmin reference bands" in chart


def test_sparse_absolute_scatter_keeps_single_run_and_clear_units():
    chart = dashboard.scatter([("2026-11-24", 340, 149)], "Pace", "Pulse", None,
                              absolute_x=True, absolute_y=True, x_unit="min/km",
                              y_unit="bpm", x_format=dashboard._run_pace, dense=True)
    assert "pt-sparse" in chart and "Pace: 5:40 min/km" in chart
