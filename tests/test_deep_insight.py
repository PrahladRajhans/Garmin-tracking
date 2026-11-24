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
        return {"done": True, "thinking": "This is never parsed.",
                "response": json.dumps(draft if len(requests) % 2 else verdict)}

    monkeypatch.setattr(narrator, "_request", response)
    profile = {"thinking": True, "controls": ["low", "medium"], "num_ctx": 4096}
    attempts = []
    assert narrator._deep_request("test:9b", profile, packet, time.monotonic() + 240, attempts=attempts) is None
    assert attempts == [{"mode": "thinking", "stage": "review", "outcome": "unsupported_claim"},
                        {"mode": "direct_revision", "stage": "review", "outcome": "unsupported_claim"}]
    verdict["verdict"] = "supported"
    assert narrator._deep_request("test:9b", profile, packet, time.monotonic() + 240) == {**draft, "mode": "thinking"}
    assert requests[0]["think"] == "low" and requests[1]["think"] is False
    assert requests[0]["format"] == packet.schema
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


def test_timed_out_thinking_can_retry_original_prose_without_skipping_review(packet, monkeypatch):
    calls = []
    answer = {"observation": "Shorter nights and a higher resting pulse stand out while HRV held steady.",
              "question": "Does resting pulse settle after a longer night?", "evidence": [1, 2, 3]}

    def request(method, path, deadline, body):
        calls.append(body)
        if len(calls) == 1:
            raise narrator.OllamaUnavailable
        return {"done": True, "response": json.dumps(answer if len(calls) == 2 else {"verdict": "supported"})}

    monkeypatch.setattr(narrator, "_request", request)
    result = narrator._deep_request("test:9b", {"num_ctx": 4096}, packet, time.monotonic() + 420)
    assert result == {**answer, "mode": "direct_retry"}
    assert [c["think"] for c in calls] == [True, False, False]


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
