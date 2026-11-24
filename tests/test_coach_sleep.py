from datetime import UTC, datetime

from garmin_mcp import coach_review, dashboard, narrator, sleep_review
from garmin_mcp.normalize import rebuild


def test_guidance_compares_published_snapshots_without_regressing(conn):
    easy = {"title": "Keep it easy", "detail": "", "target": "training"}
    rest = {"title": "Rest today", "detail": "Recovery is low.", "target": "recovery"}
    assert coach_review.guidance(conn, "2026-11-20", easy, save=True) is None
    change = coach_review.guidance(conn, "2026-11-21", rest, save=True)
    assert change["previous"]["title"] == "Keep it easy"
    assert coach_review.guidance(conn, "2026-11-21", rest) == change
    assert coach_review.guidance(conn, "2026-11-19", easy, save=True) is None
    assert coach_review.guidance(conn, "2026-11-22", rest, save=True) is None


def test_sleep_coverage_and_clock_wrapping(conn):
    rebuild(conn)
    for index in range(1, 8):
        stamp = f"2026-11-{index:02d}"
        end = f"{stamp}T{['23:55:00', '00:05:00'][index % 2]}"
        conn.execute("INSERT INTO sleep(day,sleep_s,score,sleep_end) VALUES (?,?,?,?)",
                     (stamp, 21600 if index != 1 else 3600, 80, end))
    review = sleep_review.collect(conn, "2026-11-07", UTC, 8)
    assert review["windows"][7]["nights"] == 6
    assert review["windows"][365]["hours"] == 6
    assert review["anchor"] == {"wake": "00:00", "spread": 5, "nights": 6}
    assert review["windows"][7]["chart"][0] == ("2026-11-01", None)


def test_recorded_stages_leave_unrecorded_time_blank():
    start = datetime(2026, 11, 1, 1, tzinfo=UTC)
    end = start.replace(hour=5)
    light = {"startGMT": "2026-11-01T01:00:00", "endGMT": "2026-11-01T02:00:00",
             "activityLevel": 1}
    rem = {"startGMT": "2026-11-01T03:00:00", "endGMT": "2026-11-01T04:00:00", "activityLevel": 2}
    assert sleep_review._timeline([rem, light], start, end) == [(0, 0.25, "light"), (0.5, 0.25, "rem")]
    assert sleep_review._timeline([light, {**light, "activityLevel": 2}], start, end) == []


def test_post_run_investigation_is_gated_by_actual_matched_span():
    comparison = {"available": True, "observed_hr_range_bpm": [130, 145],
                  "this_run": {"avg_hr_bpm": 152}}
    choices = coach_review.run_questions({"comparable_effort": comparison})
    item = narrator.Item("choose a next check", {"difference bpm": 12}, choices)
    assert item.response('{"choice":2}') == 2
    assert item.response('{"choice":3}') is None
    assert "repeats" in coach_review.after_run(comparison)
    comparison["this_run"]["avg_hr_bpm"] = 145
    assert not coach_review.run_questions({"comparable_effort": comparison})
    assert "no reason to change" in coach_review.after_run(comparison)


def test_chart_needs_no_visible_interaction_instructions():
    html = dashboard.bar_chart([("2026-11-01", 4)])
    assert '<figcaption class="chart-readout"><strong></strong><span></span>' in html
    assert "hover" not in html.lower()


def test_bedtime_plan_holds_after_most_nights_missed_the_prior_step(conn):
    rebuild(conn)
    for day in range(9, 23):
        date = f"2026-11-{day:02d}"
        conn.execute("INSERT INTO sleep(day,sleep_s,sleep_start,sleep_end) VALUES (?,?,?,?)",
                     (date, 25200, f"{date}T02:30:00", f"{date}T09:30:00"))
    anchor = sleep_review.collect(conn, "2026-11-23", UTC, 8)["anchor"]
    assert anchor["wake"] == "09:30"
    assert anchor["bedtime"] == "02:30" and anchor["held"]
    conn.execute("UPDATE sleep SET sleep_start=replace(sleep_start, '02:30', '02:15') "
                 "WHERE day >= '2026-11-16'")
    anchor = sleep_review.collect(conn, "2026-11-23", UTC, 8)["anchor"]
    assert anchor["bedtime"] == "02:00" and not anchor["held"]
