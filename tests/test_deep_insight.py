import json
import time

import pytest

from garmin_mcp import deep_insight, narrator


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
    ):
        assert packet.response(json.dumps({**draft, **change})) is None


def test_thinking_and_review_only_use_final_response(packet, monkeypatch):
    requests = []
    draft = {"observation": "Shorter nights and a higher resting pulse stand out while HRV held steady.",
             "question": "Does resting pulse settle after a longer night?", "evidence": [1, 2, 3]}
    verdict = {"publish": False}

    def response(method, path, deadline, body):
        requests.append(body)
        return {"done": True, "thinking": "This is never parsed.",
                "response": json.dumps(draft if len(requests) % 2 else verdict)}

    monkeypatch.setattr(narrator, "_request", response)
    profile = {"thinking": True, "controls": ["low", "medium"], "num_ctx": 4096}
    assert narrator._deep_request("test:9b", profile, packet, time.monotonic() + 240) is None
    verdict["publish"] = True
    assert narrator._deep_request("test:9b", profile, packet, time.monotonic() + 240) == {**draft, "mode": "thinking"}
    assert requests[0]["think"] == "low" and requests[1]["think"] is False
    assert all(request["model"] == "test:9b:local" for request in requests)
    assert "never parsed" not in requests[1]["prompt"]


def test_missing_cross_signal_data_hides_interpretation():
    d = {"signals": {"sleep_h": {"recent": 7, "previous": 8, "recent_count": 7, "previous_count": 7}}}
    assert not deep_insight.evidence(d)
    d["hrv_context"] = {"rolling_7d_ms": 57, "previous_average": 59}
    assert {row.domain for row in deep_insight.evidence(d)} == {"sleep", "recovery"}
    assert not deep_insight.evidence({**d, "sync_retry_required": True})


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


def test_timed_out_thinking_can_retry_original_prose_without_skipping_review(packet, monkeypatch):
    calls = []
    answer = {"observation": "Shorter nights and a higher resting pulse stand out while HRV held steady.",
              "question": "Does resting pulse settle after a longer night?", "evidence": [1, 2, 3]}

    def request(method, path, deadline, body):
        calls.append(body)
        if len(calls) == 1:
            raise narrator.OllamaUnavailable
        return {"done": True, "response": json.dumps(answer if len(calls) == 2 else {"publish": True})}

    monkeypatch.setattr(narrator, "_request", request)
    result = narrator._deep_request("test:9b", {"num_ctx": 4096}, packet, time.monotonic() + 420)
    assert result == {**answer, "mode": "direct_retry"}
    assert [c["think"] for c in calls] == [True, False, False]


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
