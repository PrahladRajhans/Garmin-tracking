from datetime import UTC, datetime, timedelta

import pytest

from garmin_mcp import (
    coaching,
    conditions,
    dashboard,
    db,
    readiness_benchmark,
    run_evidence,
    running,
)

CLOCK = datetime(2026, 10, 1, 1, tzinfo=UTC)
LOCAL = timedelta(hours=5, minutes=30)


def seed(conn, aid, when, *, hr=150, ascent=20, speed=3, seconds=1500, kind="running", fit=True):
    db.upsert_activity(conn, {"activityId": aid, "activityType": {"typeKey": kind},
                              "startTimeLocal": (when + LOCAL).replace(tzinfo=None).isoformat(),
                              "startTimeGMT": when.isoformat(), "distance": speed * seconds,
                              "elevationGain": ascent, "duration": seconds})
    if not fit:
        return
    conn.execute("UPDATE activities SET fit_parsed=1 WHERE activity_id=?", (aid,))
    conn.executemany(
        "INSERT INTO fit_records(activity_id,ts,heart_rate,speed,distance,altitude,cadence) "
        "VALUES (?,?,?,?,?,10,84)",
        ((aid, (when + timedelta(seconds=s)).isoformat(), hr, speed, speed * s)
         for s in range(0, seconds + 1, 5)))


def test_effort_requires_past_matching_duration_pace_climb_and_hr(conn):
    for aid, when, kwargs in (
        (1, CLOCK, {"hr": 144}),
        (2, CLOCK + timedelta(days=1), {"hr": 146}),
        (3, CLOCK + timedelta(days=2, hours=-1), {"hr": 148}),
        (4, CLOCK + timedelta(days=2, hours=1), {"hr": 180}),
        (5, CLOCK - timedelta(days=2), {"speed": 3.5}),
        (6, CLOCK - timedelta(days=3), {"seconds": 2200}),
        (7, CLOCK - timedelta(days=4), {"ascent": 300}),
        (8, CLOCK - timedelta(days=5), {"hr": None}),
        (9, CLOCK - timedelta(days=6), {"kind": "treadmill_running"}),
        (10, CLOCK - timedelta(days=7), {"ascent": None}),
        (11, CLOCK - timedelta(days=181), {}),
        (12, CLOCK + timedelta(days=2), {"hr": 154}),
    ):
        seed(conn, aid, when, **kwargs)
    api = coaching.run_analysis(conn, 12)
    comparison = api["comparable_effort"]
    assert comparison == running.running_breakdown(conn, 12)["comparable_effort"]
    assert [m["activity_id"] for m in comparison["matches"]] == [3, 2, 1]
    assert [row["avg_hr_bpm"] for row in comparison["matches"]] == [148, 146, 144]
    assert comparison["median_hr_bpm"] == 146
    assert comparison["difference_hr_bpm"] == 8
    assert comparison["observed_hr_range_bpm"] == [144, 148]
    assert not api["heat_model"]["available"]
    assert "8 bpm higher" in api["facts_for_recap"][0]
    assert "Outside the observed span" in api["facts_for_recap"][1]
    assert not coaching.run_analysis(conn, 10)["comparable_effort"]["available"]


def test_pace_matched_form_gate_requires_three_values_per_metric():
    history = [(i, "2026-10-01", {"avg_speed": 3, "avg_hr": 150,
                                  "cadence_spm": 170 if i < 5 else None})
               for i in range(3, 7)]
    result = coaching.matched_pace_norms(history, 3)
    assert result == {"runs": 4, "avg_hr": 150}


def test_readiness_benchmark_uses_pre_run_scores_and_one_pair_per_date(conn, monkeypatch):
    for i in range(24):
        when = CLOCK + timedelta(days=i)
        day = when.date().isoformat()
        seed(conn, i + 1, when, fit=False)
        conn.execute("UPDATE activities SET fit_parsed=1 WHERE activity_id=?", (i + 1,))
        before = timedelta(hours=-1) if i < 20 else timedelta(hours=1)
        db.put_daily(conn, "training_readiness", day, "garminconnect", [
            {"calendarDate": day, "timestamp": (when + before).isoformat(), "score": 50 + i},
            {"calendarDate": day, "timestamp": (when + timedelta(hours=4)).isoformat(),
             "score": 10}])

    when = CLOCK + timedelta(minutes=15)
    seed(conn, 25, when, fit=False)
    conn.execute("UPDATE activities SET fit_parsed=1 WHERE activity_id=25")
    db.put_daily(conn, "ex_training_readiness", "2026-10-01", "export", [
        {"calendarDate": 20261001, "timestamp": (CLOCK - timedelta(hours=1)).isoformat(),
         "score": 2},
        {"calendarDate": 20261001, "timestamp": "2026-10-01", "score": 1}])

    def matched(c, aid, metrics, reader):
        return {"available": True, "difference_hr_bpm": -aid, "matches": [1, 2, 3]}

    monkeypatch.setattr(run_evidence, "matched_effort", matched)
    result = readiness_benchmark.benchmark(conn, "2026-10-24", read_metrics=lambda c, aid: {"id": aid})
    assert result["available"] and result["spearman_rho"] == -1
    assert result["paired_days"] == 20
    assert result["pairs"][0]["readiness_score"] == 50
    assert result["pairs"][0]["activity_id"] == 1
    assert result["pairs"][-1]["readiness_score"] == 69
    assert result["pairs"][-1]["activity_id"] == 20
    limited = readiness_benchmark.benchmark(conn, "2026-10-19", read_metrics=lambda c, aid: {"id": aid})
    assert not limited["available"] and limited["paired_days"] == 19


def test_local_conditions_preserve_zero_coverage_gaps_and_units(conn, tmp_path):
    seed(conn, 1, CLOCK)
    db.put_activity_detail(conn, 1, "weather", {"temp": 77, "relativeHumidity": 60,
                                                "windSpeed": 18, "issueLocation": "Private"})
    csv = tmp_path / "conditions.csv"
    header = "start_utc,end_utc,source,kind,temperature_c,precipitation_mm,aqi,aqi_standard\n"
    csv.write_text(header + "2026-10-01T06:30:00+05:30,2026-10-01T01:10:00Z,Station A,"
                   "observation,28,0,0,IN-CPCB\n"
                   "2026-10-01T01:20:00Z,2026-10-01T02:00:00Z,Model B,model,29,,91,US-EPA\n")
    assert conditions.import_windows(conn, 1, csv) == 2
    context = conditions.for_activity(conn, 1)
    assert context["garmin_snapshot"] == {
        "temperature_c": 25, "humidity_pct": 60, "source": "Garmin saved weather",
        "reference_time": ""}
    stream = coaching.activity_stream(conn, 1, 60)
    joined = conditions.for_samples(stream["start_utc"], stream["stream"], context)
    assert (joined[0]["aqi"], joined[540]["precipitation_mm"]) == (0, 0)
    assert 600 not in joined and 1140 not in joined and joined[1200]["aqi"] == 91
    run = running.running_breakdown(conn, 1)
    html = dashboard.page_run_trace({**run, "trace": stream, "date": CLOCK.date().isoformat(),
                                     "km": 4.5})
    assert "AQI 0 (India CPCB)" in html and "AQI 91 (US EPA)" in html
    assert "0 mm precipitation" in html and "Private" not in html
    csv.write_text(header + "2026-10-01T01:00:00,2026-10-01T01:10:00Z,Station A,"
                   "observation,,,100,IN-CPCB\n")
    with pytest.raises(ValueError, match="explicit UTC offset"):
        conditions.import_windows(conn, 1, csv)
    assert conditions.for_activity(conn, 1) == context


def test_efficiency_trend_needs_distinct_days_and_ignores_test_name(conn):
    for aid, offset in enumerate(range(3), 1):
        seed(conn, aid, CLOCK + timedelta(minutes=offset * 50))
    seed(conn, 4, CLOCK + timedelta(days=1), seconds=600)
    conn.execute("UPDATE activities SET name='Calibration test' WHERE activity_id=4")
    check = running.test_runs(conn)
    assert not check["available"]
    assert {r["activity_id"] for r in check["runs"]} == {1, 2, 3}
    for i in range(2):
        seed(conn, 5 + i, CLOCK + timedelta(days=2 + i))
    result = running.test_runs(conn)
    assert result["available"] and result["ef_change_per_90d_pct"] == 0
