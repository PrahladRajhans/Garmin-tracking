"""Small movements are not findings, and the biggest recorded changes are not skipped."""

import pytest

from garmin_mcp import clauses, deep_insight


def _health(sleep=(7.0, 7.2), pulse=(50.3, 50.0), hrv=(60, 61), shortfall=(40, 41)):
    end = "2026-11-25"
    signals = {key: {"recent": a, "previous": b, "recent_count": 7, "previous_count": 7}
               for key, (a, b) in (("sleep_h", sleep), ("resting_hr", pulse))}
    return {"end": end, "signals": signals, "hrv_context": {"rolling_7d_ms": hrv[0], "previous_average": hrv[1]},
            "sleep_shortfall": {"per_night_min": shortfall[0], "previous_min": shortfall[1],
                                "current": {"valid_nights_7d": 7}, "previous": {"valid_nights_7d": 7}}}


def test_small_weekly_movements_read_as_about_the_same():
    rows = deep_insight.evidence(_health())
    assert [row.claim.trend for row in rows] == ["same"] * 4
    rows = deep_insight.evidence(_health(sleep=(6.0, 7.4), pulse=(55, 50), hrv=(52, 61), shortfall=(90, 40)))
    assert [row.claim.trend for row in rows] == ["down", "up", "up", "down"]  # sleep, pulse, shortfall, HRV


@pytest.mark.parametrize("metric, right, wrong", [
    ("resting", "Resting heart rate was higher this week than last week",
     "Resting heart rate was lower this week than last week"),
    ("hrv", "Heart rate variability was lower this week than last week",
     "Heart rate variability was higher this week than last week"),
    ("shortfall", "Sleep shortfall was larger this week than last week",
     "Sleep shortfall was smaller this week than last week"),
])
def test_weekly_health_clauses_must_match_their_direction(metric, right, wrong):
    rows = deep_insight.evidence(_health(pulse=(55, 50), hrv=(52, 61), shortfall=(90, 40)))
    claim = next(row.claim for row in rows if row.claim.metric == metric)
    assert clauses.check(right + ".", claim) is None
    assert clauses.check(wrong + ".", claim) == "wrong_comparison"


def test_a_clause_about_another_measure_is_rejected():
    rows = deep_insight.evidence(_health(sleep=(6.0, 7.4), shortfall=(90, 40)))
    sleep = next(row.claim for row in rows if row.claim.metric == "sleep")
    assert clauses.check("Sleep shortfall was shorter this week than last week", sleep) == "wrong_comparison"


def test_fallback_pairs_include_the_changed_readings():
    packet = deep_insight.Insight(deep_insight.evidence(_health(shortfall=(90, 40), hrv=(52, 61))))
    changed = {i for i, row in enumerate(packet.rows, 1) if deep_insight.changed(row)}
    assert len(changed) == 2
    assert packet.comparison_options() == (tuple(sorted(changed)),)


def test_a_draft_cannot_pass_over_the_only_changes():
    packet = deep_insight.Insight(deep_insight.evidence(_health(shortfall=(90, 40))))
    quiet = {"parts": [{"evidence": 1, "text": "Sleep per night was the same this week as last week"},
                       {"evidence": 2, "text": "Resting heart rate was the same this week as last week"}]}
    assert packet._assess_parts(quiet) == (None, "low_signal_choice")


def test_post_run_does_not_ask_about_a_difference_inside_the_noise_band():
    data = deep_insight._fictional_post_run(None, 171)  # 172 early, 171 late
    question = deep_insight.post_run_review(data).checks[0].question
    assert "difference" not in question and "steady" in question
    data = deep_insight._fictional_post_run(None, 165)
    assert "difference" in deep_insight.post_run_review(data).checks[0].question


def test_post_run_skips_an_old_run():
    data = deep_insight._fictional_post_run(152, 165)
    assert deep_insight.post_run_review({**data, "end": "2026-12-09"}) is not None  # 14 days later
    assert deep_insight.post_run_review({**data, "end": "2026-12-10"}) is None

