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
    assert "View values" not in text and "What stands out" in text
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

    advice = running.suggestions({"decoupling_pct": -10}, {}, None)
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
        path = dashboard.build(conn, tmp_path / "local")
    assert path.is_file() and "No Garmin data" in path.read_text()


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
