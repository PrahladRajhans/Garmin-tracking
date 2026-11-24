import json
from datetime import UTC, datetime, timedelta

from garmin_mcp import (
    coach_loop,
    coaching,
    dashboard,
    db,
    deep_insight,
    narrator,
    running,
    running_block,
)
from garmin_mcp.normalize import rebuild


def test_block_uses_completed_weeks_and_excludes_indoor_effort(conn):
    records = [(1, "2026-04-15", "running", 5000), (2, "2026-05-06", "running", 4800),
               (3, "2026-05-13", "track_running", 4500), (4, "2026-05-20", "running", 4500),
               (5, "2026-05-21", "treadmill_running", 3000), (6, "2026-05-21", "running", None),
               (7, "2026-05-22", "running", 10000), (8, "2026-05-14", "walking", 1000)]
    conn.executemany("INSERT INTO activities(activity_id,start_time_local,type,distance_m,fit_parsed,updated_at) "
                     "VALUES (?,?,?,?,1,'')", records)
    measured = []

    def metrics(_, aid):
        measured.append(aid)
        return {"steady": True, "avg_hr": 144, "avg_speed": 2.5,
                "moving_s": 1500, "recorded_elapsed_s": 1550, "decoupling_pct": 4}

    block = running_block.collect(conn, "2026-05-21", read_metrics=metrics)
    assert len(block["weeks"]) == 13 and block["weeks"][-1]["complete"] is False
    assert block["recent"]["km"] == 9.3 and block["previous"]["km"] == 5
    assert block["recent"]["days"] == 2 and block["weeks"][-1]["runs"] == 3
    assert block["weeks"][-1]["distance_count"] == 2
    assert block["median_decoupling"] == 4
    assert set(measured) == {1, 2, 3, 4, 6}


def test_running_review_has_separate_prompt_and_only_local_link_metadata(conn):
    data = {"running_block": {"recent": {"runs": 4, "days": 3}, "previous": {"runs": 3, "days": 3},
                              "median_decoupling": 4, "decoupling_count": 3}}
    items = narrator._deep_items(conn, {"thinking": False}, data)
    assert set(items) == {"running-insight"}
    packet = items["running-insight"]
    assert packet.lens == "running_review" and "measured response on the latest run" in packet.system
    assert all(row.keys() == {"id", "domain", "reading"} for row in json.loads(packet.prompt))
    assert not deep_insight.running_review({**data, "older_snapshot": True})


def test_form_uses_measured_match_span_and_withholds_sparse_comparisons():
    measured = {"avg_speed": 3, "cadence_spm": 160, "ground_contact_ms": 275, "vertical_ratio_pct": 9}
    earlier = [{"cadence_spm": n, "ground_contact_ms": gc}
               for n, gc in ((169, 260), (170, None), (172, None))]
    form = running.form_comparison(measured, {}, earlier)
    cadence = form["cadence_spm"]
    assert cadence["matched_range"] == [169, 172] and cadence["your_usual_at_this_pace"] == 170
    assert form["ground_contact_ms"]["value"] == 275 and "vs_usual_pct" not in form["ground_contact_ms"]
    assert "shorter step" in form["vertical_ratio_pct"]["meaning"]


def test_running_links_and_calculated_readings_render(conn):
    end = datetime.now(UTC).date().isoformat()
    db.put_daily(conn, "ex_daily_summary", end, "export", {"calendarDate": end, "totalSteps": 100})
    rebuild(conn)
    conn.execute("INSERT INTO activities(activity_id,start_time_local,type,distance_m,updated_at) "
                 "VALUES (1,?,'running',5000,'')", (end,))
    html = dashboard.render(dashboard.collect(conn, end))
    assert 'href="#running-block"' in html and 'id="running-block"' in html
    assert 'id="running-efforts"' in html and "Training rhythm" in html


def test_running_chart_uses_elapsed_crossings_instead_of_nearest_sample():
    data = [{"t_s": time, "cadence_spm": cadence} for time, cadence in [(0, 162), (30, 166), (60, 169)]]
    metric = ("cadence_spm", "Cadence", "Cadence", str)
    svg = dashboard._paired_chart(data, metric, (), 30, crossings=(20, 65), elapsed_end=66)
    assert 'class="split-guides"' in svg
    assert 'x1="125.03" x2="125.03"' in svg
    assert "Km 1 · 0:20 elapsed" in svg and "Km 2 · 1:05 elapsed" in svg
    assert 'class="split-guides"' not in dashboard._paired_chart(data, metric, (), 30)


def test_run_form_compares_the_same_pace_and_uses_trace_origin(conn):
    start = datetime(2026, 11, 18, tzinfo=UTC)
    conn.executemany(
        "INSERT INTO fit_records(activity_id,ts,speed,distance,altitude,cadence,stance_time) VALUES (1,?,?,?,?,?,?)",
        [((start + timedelta(seconds=s)).isoformat(), 3.0, 3 * s if s else None, 100,
          84 if s <= 600 else 81, 240 if s <= 600 else 250) for s in range(0, 1201, 5)],
    )
    metrics = coaching.run_metrics(conn, 1)
    assert metrics["km_crossings_s"][0] == 338.33
    result = coaching.late_running_form(conn, 1, moving_s=metrics["moving_s"], elapsed_s=1200)
    assert result["cadence_spm"] == {"early": 168.0, "late": 162.0, "matched_s": 595}
    assert result["ground_contact_ms"]["late"] == 250
    assert "step_length_m" not in result

    conn.execute("UPDATE fit_records SET speed=4 WHERE ts>?", ((start + timedelta(seconds=600)).isoformat(),))
    assert coaching.late_running_form(conn, 1, moving_s=1200, elapsed_s=1200) == {}


def test_running_block_matches_next_day_knee_pause(conn):
    coach_loop.save_checkin(conn, "2026-11-23", knee=4)
    result = running_block.collect(conn, "2026-11-24")
    assert result["next"]["title"] == "Leave running out today"
    assert result["next"]["target"] == "today"
