import json
import time

import pytest

from garmin_mcp import dashboard, deep_insight, narrator


@pytest.fixture
def packet():
    return deep_insight.Insight((
        deep_insight.Evidence("sleep", "Sleep duration was lower.", "sleep"),
        deep_insight.Evidence("recovery", "Resting pulse was higher.", "recovery"),
        deep_insight.Evidence("recovery", "HRV stayed near its earlier average.", "recovery"),
    ))


def test_qualitative_draft_must_cite_distinct_domains(packet):
    draft = {"observation": "Shorter nights and a higher resting pulse stand out while HRV held steady.",
             "question": "Does resting pulse settle after a longer night?",
             "evidence": [1, 2, 3]}
    assert packet.response(json.dumps(draft)) == draft
    for change in (
        {"evidence": [2, 3]}, {"evidence": [1, True]}, {"evidence": [1, 4]}, {"evidence": [1, 1, 2]},
        {"observation": "Your pulse increased because you slept less than you needed."},
        {"observation": "Your pulse went up by 4 bpm after shorter nights."},
        {"question": "Start taking a supplement to improve readings."},
        {"question": "Is the extra session the reason you're feeling more tired?"},
    ):
        assert packet.response(json.dumps({**draft, **change})) is None


def test_thinking_and_review_only_use_final_response(packet, monkeypatch):
    requests = []
    draft = {"observation": "Shorter nights and a higher resting pulse stand out while HRV held steady.",
             "question": "Does resting pulse settle after a longer night?", "evidence": [1, 2, 3]}
    verdict = {"verdict": "unsupported_claim"}

    def response(method, path, deadline, body):
        requests.append(body)
        fields = body["format"]["required"]
        payload = verdict if fields == ["verdict"] else {"comparison": 2} if fields == ["comparison"] else draft
        return {"done": True, "thinking": "This is never parsed.",
                "response": json.dumps(payload)}

    monkeypatch.setattr(narrator, "_request", response)
    profile = {"thinking": True, "controls": ["low", "medium"], "num_ctx": 4096}
    attempts = []
    result = narrator._deep_request("test:9b", profile, packet, time.monotonic() + 240, attempts=attempts)
    assert result["mode"] == "selected_comparison"
    assert result["observation"] == "Sleep duration was lower. HRV stayed near its earlier average."
    assert result["evidence"] == [1, 3]
    assert attempts == [{"mode": "thinking", "stage": "review", "outcome": "unsupported_claim"},
                        {"mode": "selected_comparison", "stage": "selection", "outcome": "grounded_selection"}]
    verdict["verdict"] = "supported"
    assert narrator._deep_request("test:9b", profile, packet, time.monotonic() + 240) == {**draft, "mode": "thinking"}
    assert [request["think"] for request in requests[:3]] == ["low", False, False]
    assert requests[0]["format"] == packet.schema
    assert requests[0]["options"]["num_predict"] == 2450
    assert all(request["model"] == "test:9b:local" for request in requests)
    assert "never parsed" not in requests[1]["prompt"]


def test_missing_cross_signal_data_hides_interpretation():
    d = {"signals": {"sleep_h": {"recent": 7, "previous": 8, "recent_count": 7, "previous_count": 7}}}
    assert not deep_insight.evidence(d)
    d["hrv_context"] = {"rolling_7d_ms": 57, "previous_average": 59}
    assert {row.domain for row in deep_insight.evidence(d)} == {"sleep", "recovery"}
    assert not deep_insight.evidence({**d, "sync_retry_required": True})


def test_running_evidence_keeps_pace_direction_and_matched_cadence_context():
    data = {"running_block": {"latest_detail_id": 1}, "runs": [{"activity_id": 1,
        "pacing": {"effort_halves": [{"pace_s_per_km": 335, "hr": 140}, {"pace_s_per_km": 347, "hr": 147}]},
        "late_form": {"cadence_spm": {"early": 172, "late": 168, "matched_s": 400}}}]}
    pace, cadence = deep_insight.running_review(data)
    assert "slower in the second moving half" in pace.text and "335 to 347" in pace.text
    assert "similar pace and grade" in cadence.text and "400 matched seconds" in cadence.text
    assert cadence.page == "run-1-form"


@pytest.mark.parametrize("case", deep_insight.FICTIONAL_POST_RUN_CASES)
def test_post_run_reference_outputs(case):
    data, expected = deep_insight.FICTIONAL_POST_RUN_CASES[case]
    result = deep_insight.post_run_fallback(data)
    if expected is None:
        assert result is None
        return
    assert result["mode"] == "rule_post_run" and result["topic"] == expected
    assert result["readings"][0]["text"] == result["observation"]
    assert result["alternative"] and result["question"].endswith("?")


def test_post_run_cue_and_matching_stay_compact_and_private():
    from copy import deepcopy

    data, _ = deep_insight.FICTIONAL_POST_RUN_CASES["post-run-cue"]
    data = deepcopy(data)
    data["trial"]["attempts"][0]["your_notes"] = {"note": "PRIVATE"}
    data["runs"][0]["name"] = "PRIVATE"
    item = deep_insight.post_run_review(data)
    packet = json.loads(item.prompt)
    assert len(packet) == 3 and "PRIVATE" not in item.prompt and "2026-11-25" not in item.prompt
    assert "activity_id" not in item.prompt and "run-101" not in item.prompt
    assert packet[0]["match"] == "pace and grade" and packet[0]["matched_seconds_per_half"] == 420
    assert packet[2]["minutes_above_and_recorded"] == {"this_run": [8, 27], "earlier_attempt": [5, 25]}
    assert packet[2]["target_steps_per_min"] == 174 and packet[2]["at_least_steps_per_min"] == 172
    assert "8 of 27" in item.assess('{"check":3}')[0]["observation"]
    assert all(item.assess(raw)[0] is None for raw in
               ('{"check":true}', '{"check":0}', '{"check":4}', '{"check":2,"observation":"new claim"}'))
    data["trial"]["attempts"][0]["date"] = "2026-11-26"
    assert len(deep_insight.post_run_review(data).checks) == 2
    assert deep_insight.post_run_review({**data, "sync_retry_required": True}) is None


def test_post_run_requests_one_non_thinking_choice_and_caches_exact_reading(conn, monkeypatch):
    data, _ = deep_insight.FICTIONAL_POST_RUN_CASES["post-run-outlier"]
    narrator.configure(conn, True, "test:4b", True)
    monkeypatch.setattr(narrator, "items", lambda _: {})
    monkeypatch.setattr(narrator, "_cloud_disabled", lambda _: True)
    monkeypatch.setattr(narrator, "_warm", lambda *_: None)
    monkeypatch.setattr(narrator, "_model_profile",
                        lambda *_: {"thinking": True, "text_generation": True, "num_ctx": 4096})
    calls = []

    def request(method, path, deadline, body):
        calls.append(body)
        assert body["think"] is False and body["format"]["required"] == ["check"]
        return {"done": True, "response": '{"check":2}'}

    monkeypatch.setattr(narrator, "_request", request)
    assert narrator.generate(conn, data, time.monotonic() + 60)
    summaries, pending = narrator.cached(conn, data)
    assert not pending and len(calls) == 1
    result = summaries["post-run-insight-101"]
    assert result["mode"] == "selected_post_run" and result["topic"] == "moving pulse"
    assert result["readings"][0]["page"] == "run-101-compare"
    assert result["observation"] == result["readings"][0]["text"]


def test_post_run_rejects_stable_choice_beside_a_measured_cadence_change():
    data, _ = deep_insight.FICTIONAL_POST_RUN_CASES["post-run-form"]
    item = deep_insight.post_run_review(data)
    assert item.assess('{"check":2}') == (None, "low_signal_choice")
    assert deep_insight.post_run_fallback(data)["topic"] == "late cadence"


def test_sunday_review_keeps_plan_and_links_checked_evidence(conn):
    data = {"end": "2026-11-22",
            "weekly_review": {"week": {"sessions": 3}},
            "sleep_review": {"windows": {7: {"nights": 5, "hours": 7.2}}, "week_change_min": -21},
            "brief": {"week_ahead": {"plan": "Repeat the easy run.", "basis": "Based on recent sessions."}}}
    facts = deep_insight.sunday_review(data)
    assert {row.domain for row in facts} == {"sleep", "training"}
    assert "21 min less" in dashboard._sunday_story(data)
    data["weekly_review"]["previous_4wk_weekly_avg"] = {"sessions": 2}
    assert "3 this week versus 2" in deep_insight.sunday_review(data)[0].text
    assert "sunday-insight" in narrator._deep_items(conn, {"thinking": False}, data)
    data["narration"] = {"sunday-insight": {
        "observation": "The log shows several workouts alongside shorter nights.",
        "question": "Does that pattern repeat next week?",
        "readings": [{"page": row.page, "text": row.text} for row in facts],
    }}
    html = dashboard._sunday_story(data)
    assert all(s in html for s in ("Local AI review", "Repeat the easy run.", 'href="#sleep"', 'href="#training"'))
    assert not dashboard._sunday_story({**data, "end": "2026-11-23"})
    assert not dashboard._sunday_story({**data, "sync_retry_required": True})


def test_opt_in_result_is_cached_with_python_readings(conn, monkeypatch, packet):
    narrator.configure(conn, True, "test:9b", True)
    monkeypatch.setattr(deep_insight, "evidence", lambda _: packet.rows)
    monkeypatch.setattr(narrator, "items", lambda _: {})
    monkeypatch.setattr(narrator, "_cloud_disabled", lambda _: True)
    monkeypatch.setattr(narrator, "_model_profile", lambda *_: {"thinking": True, "text_generation": True})
    monkeypatch.setattr(narrator, "_warm", lambda *_: None)
    draft = {"observation": "Shorter nights and a higher resting pulse stand out while HRV held steady.",
             "question": "Does resting pulse settle after a longer night?", "evidence": [1, 2]}
    monkeypatch.setattr(narrator, "_deep_request", lambda *_, **__: draft)
    assert narrator.cached(conn, {}) == ({}, True)
    assert narrator.generate(conn, {}, time.monotonic() + 10)
    summaries, pending = narrator.cached(conn, {})
    assert not pending and summaries["deep-insight"]["observation"] == draft["observation"]
    assert summaries["deep-insight"]["readings"][0]["text"] == packet.rows[0].text
    narrator.configure(conn, thinking=False)
    assert narrator.cached(conn, {}) == ({}, False)


def test_completion_only_model_resolves_pending_daily_review(conn, monkeypatch, packet):
    narrator.configure(conn, True, "test:7b", True)
    monkeypatch.setattr(deep_insight, "evidence", lambda _: packet.rows)
    monkeypatch.setattr(narrator, "items", lambda _: {})
    monkeypatch.setattr(narrator, "_cloud_disabled", lambda _: True)
    monkeypatch.setattr(narrator, "_model_profile", lambda *_: {"thinking": False, "text_generation": True})
    monkeypatch.setattr(narrator, "_warm", lambda *_: None)

    def review(*_, think_first, attempts, **__):
        assert think_first is False
        attempts.append({"mode": "direct", "stage": "review", "outcome": "supported"})
        return {"observation": "Shorter nights and a higher resting pulse stand out while HRV held steady.",
                "question": "Does that pattern recur after another shorter night?", "evidence": [1, 2],
                "mode": "direct"}

    monkeypatch.setattr(narrator, "_deep_request", review)
    assert narrator.generate(conn, {}, time.monotonic() + 10)
    saved, pending = narrator.cached(conn, {})
    assert saved["deep-insight"]["mode"] == "direct" and not pending
    attempts = narrator._worker_status(conn, "test:7b")["insights"]
    assert attempts["deep-insight"][0]["outcome"] == "supported"


def test_timed_out_thinking_keeps_time_for_the_checked_comparison(packet, monkeypatch):
    calls = []
    total_deadline = time.monotonic() + 120

    def request(method, path, deadline, body):
        calls.append(body)
        if len(calls) == 1:
            assert deadline <= total_deadline - narrator.INSIGHT_SELECTION_SECONDS
            raise TimeoutError("thinking took too long")
        assert deadline <= total_deadline
        return {"done": True, "response": '{"comparison":1}'}

    monkeypatch.setattr(narrator, "_request", request)
    result = narrator._deep_request("test:9b", {"num_ctx": 4096}, packet, total_deadline)
    assert result["observation"] == "Sleep duration was lower. Resting pulse was higher."
    assert result["evidence"] == [1, 2] and result["mode"] == "selected_comparison"
    assert [c["think"] for c in calls] == [True, False]


def test_selection_cannot_choose_previous_rows_or_write_new_claims(packet):
    earlier = deep_insight.Evidence("running", "Earlier moving pulse was 162 bpm.", "running", previous=True)
    item = deep_insight.Insight(packet.rows + (earlier,))
    options = item.comparison_options()
    assert options == ((1, 2), (1, 3))
    for raw in ('{"comparison":true}', '{"comparison":0}', '{"comparison":3}', '{"comparison":1.0}',
                '{"comparison":1,"observation":"invented claims"}', '[]', 'not JSON'):
        assert item.selected_comparison(raw, options) is None
    assert item.selected_comparison('{"comparison":2}', options)["evidence"] == [1, 3]


def test_abstention_is_not_replaced_with_a_comparison(packet, monkeypatch):
    calls = []

    def request(*args):
        calls.append(args)
        return {"done": True, "response": '{"observation":"","question":"","evidence":[]}'}

    monkeypatch.setattr(narrator, "_request", request)
    assert narrator._deep_request("test:9b", {"num_ctx": 4096}, packet, time.monotonic() + 120) is None
    assert len(calls) == 1


def test_selection_from_stale_snapshot_is_not_returned(packet, monkeypatch):
    fresh = True

    def request(*args):
        nonlocal fresh
        fresh = False
        return {"done": True, "response": '{"comparison":1}'}

    monkeypatch.setattr(narrator, "_request", request)
    with pytest.raises(narrator.OllamaUnavailable):
        narrator._deep_request("test:4b", {"num_ctx": 4096}, packet, time.monotonic() + 60,
                               still_current=lambda: fresh, selection_only=True)


def test_worker_caches_selected_readings_after_a_truncated_thinking_draft(conn, monkeypatch):
    lens, readings = deep_insight.FICTIONAL_CASES["dated-health"]
    item = deep_insight.Insight(readings, lens)
    narrator.configure(conn, True, "test:4b", True)
    monkeypatch.setattr(narrator, "items", lambda _: {})
    monkeypatch.setattr(narrator, "_deep_items", lambda *_: {"deep-insight": item})
    monkeypatch.setattr(narrator, "_cloud_disabled", lambda _: True)
    monkeypatch.setattr(narrator, "_warm", lambda *_: None)
    monkeypatch.setattr(narrator, "_model_profile",
                        lambda *_: {"thinking": True, "text_generation": True, "num_ctx": 4096})

    def request(method, path, deadline, body):
        if body["think"]:
            return {"done": True, "done_reason": "length", "response": "unfinished prose"}
        assert "unfinished prose" not in body["prompt"]
        assert "2026-11-25" not in body["prompt"]
        return {"done": True, "response": '{"comparison":1}'}

    monkeypatch.setattr(narrator, "_request", request)
    data = {"end": "2026-11-25"}
    assert narrator.generate(conn, data, time.monotonic() + 120)
    summaries, pending = narrator.cached(conn, data)
    result = summaries["deep-insight"]
    assert not pending and result["mode"] == "selected_comparison"
    assert result["observation"] == " ".join(row.text for row in readings)
    assert [row["page"] for row in result["readings"]] == ["sleep", "recovery"]
    assert "unfinished prose" not in json.dumps(summaries)


def test_invalid_draft_gets_one_correction_and_full_review(packet, monkeypatch):
    calls = []
    answer = {"observation": "Shorter nights and a higher resting pulse stand out while HRV held steady.",
              "question": "Do those readings change direction after longer nights?", "evidence": [1, 2, 3]}
    replies = iter([{**answer, "evidence": [2, 3]}, answer, {"verdict": "supported"}])

    def request(method, path, deadline, body):
        calls.append(body)
        return {"done": True, "response": json.dumps(next(replies))}

    monkeypatch.setattr(narrator, "_request", request)
    attempts = []
    result = narrator._deep_request("test:4b", {"num_ctx": 4096}, packet, time.monotonic() + 240,
                                    think_first=False, attempts=attempts)
    assert result == {**answer, "mode": "direct_revision"}
    assert [stage["outcome"] for stage in attempts] == ["missing_citations", "supported"]
    assert [stage["stage"] for stage in attempts] == ["draft", "review"]
    assert "Cite two current domains" in calls[1]["system"]
    assert json.loads(calls[2]["prompt"])["draft"] == answer


def test_review_can_keep_a_supported_observation_with_a_grounded_question(monkeypatch):
    lens, readings = deep_insight.FICTIONAL_CASES["running-block"]
    packet = deep_insight.Insight(readings, lens)
    observation = "You ran on more days, and your latest moving pulse was within its earlier range."
    draft = {"observation": observation, "question": "Did you feel tired because you ran more?",
             "evidence": [1, 2]}
    responses = iter([draft, {"verdict": "supported"}])
    reviewed = []

    def request(method, path, deadline, body):
        reviewed.append(body)
        return {"done": True, "response": json.dumps(next(responses))}

    monkeypatch.setattr(narrator, "_request", request)
    attempts = []
    result = narrator._deep_request("test:4b", {"num_ctx": 4096}, packet, time.monotonic() + 240,
                                    think_first=False, attempts=attempts)
    assert result["observation"] == observation
    assert result["question"] == "Does moving pulse stay in the same range on another run at a similar pace?"
    assert json.loads(reviewed[1]["prompt"])["draft"]["question"] == result["question"]
    assert attempts[0]["question_reframed"] and attempts[0]["outcome"] == "supported"
    unsafe = {**draft, "observation": "You ran on more days, so you felt tired in your latest run."}
    assert packet.assess(json.dumps(unsafe), repair_question=True) == (None, "unsupported_claim")


def test_specific_numbers_can_be_used_with_their_cited_readings():
    packet = deep_insight.Insight((
        deep_insight.Evidence("sleep", "Sleep averaged 6.2 h versus 7.1 h.", "sleep"),
        deep_insight.Evidence("recovery", "Resting pulse rose from 55 to 59 bpm.", "recovery"),
        deep_insight.Evidence("recovery", "Seven-day HRV held at 51 ms.", "recovery"),
    ))
    result = {"observation": "Sleep fell to 6.2 h while resting pulse rose to 59 bpm.",
              "question": "Does pulse return to its earlier range after longer sleep?",
              "evidence": [1, 2]}
    assert packet.response(json.dumps(result)) == result
    result["observation"] = "Sleep fell to 6.2 h while resting pulse rose to 51 bpm."
    assert packet.response(json.dumps(result)) is None


def test_style_overrides_are_local_and_invalid_text_uses_built_in(conn):
    path = deep_insight._style_path(conn)
    original = deep_insight.writing_style(conn, "sleep")
    path.write_text(json.dumps({"voice": "Be terse, warm and precise.",
                                "lenses": {"daily": "Start with a signal.", "sleep": "Explain a contrast."}}))
    active = deep_insight.writing_style(conn, "sleep")
    assert active == ("Be terse, warm and precise.", "Start with a signal. Explain a contrast.", "custom")
    path.write_text('{"voice":128}')
    fallback = deep_insight.writing_style(conn, "sleep")
    assert fallback[:2] == original[:2] and fallback[2].startswith("invalid")


def test_previous_evidence_is_bounded_and_cannot_replace_current_domains(conn, packet):
    deep_insight.remember(conn, "2026-11-15", packet.rows)
    earlier = deep_insight.remembered(conn, "2026-11-16")
    assert len(earlier) == 2 and all(row.previous for row in earlier)
    assert not deep_insight.remembered(conn, "2026-11-15")
    assert not deep_insight.remembered(conn, "2026-12-05")
    item = deep_insight.Insight(packet.rows + earlier)
    draft = {"observation": "Shorter nights and a higher resting pulse stand out while HRV held steady.",
             "question": "Does resting pulse settle after a longer night?", "evidence": [1, 5]}
    assert item.response(json.dumps(draft)) is None


def test_thinking_budget_is_explicit_and_survives_model_change(conn, packet):
    before = narrator.settings(conn)
    assert narrator._thinking_seconds(before) == 600
    narrator.configure(conn, thinking=True, thinking_minutes=5)
    assert narrator._deep_key(packet, narrator.settings(conn)) != narrator._deep_key(packet, before)
    state = narrator.configure(conn, model="nimble-v3:9b-q4_K_M")
    assert state["thinking"] is True and narrator._thinking_seconds(state) == 300
    with pytest.raises(ValueError, match="1 to 30"):
        narrator.configure(conn, thinking_minutes=31)


def test_daily_evidence_names_garmin_estimate_with_explicit_dated_baseline():
    from garmin_mcp.deep_insight import evidence

    day = "2026-11-25"
    check = {"value": 44, "median": 53, "direction": "lower", "verify": True, "count": 16}
    data = {
        "end": day,
        "calendar": {"days": {day: {"resting_pulse_check": check}}},
        "sleep_shortfall": {"per_night_min": 42, "previous_min": 60,
                            "current": {"valid_nights_7d": 6}, "previous": {"valid_nights_7d": 7}},
    }
    sleep, pulse = evidence(data)
    assert sleep.page == "sleep" and "42 min per usable night across 6 nights" in sleep.text
    assert pulse.page == "recovery" and "44 bpm, below the personal review range" in pulse.text
    assert evidence({**data, "older_snapshot": True}) == ()
    check["median"] = None
    assert evidence(data) == ()
