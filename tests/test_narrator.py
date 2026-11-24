import json
import time
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import make_fit

from garmin_mcp import dashboard, db, fit, narrator, trials
from garmin_mcp.normalize import rebuild

FACTS = {"Sleep hours": 5.7, "Cadence": 172, "Pace": "5:20", "Heart rate change": -2}


def _answer(*selection):
    return 200, {"done": True, "response": json.dumps({"selection": selection})}


@pytest.mark.parametrize("text", [
    "You slept 6 hours.",
    "Cadence was 5:172.",
    "Heart rate rose by 2 bpm.",
    "You slept six hours.",
    "You slept 5.7 hours. " + "Rest " * 57,
    "Cadence was recorded. Sleep was recorded. Pace was recorded. Heart rate was recorded.",
    "I can DIAGNOSE what is wrong.",
    "This points to disease.",
    "Your Injury-Risk has increased.",
    "Improvement is guaranteed.",
    "You should run today.",
    "A number was 5e20.",
    "You slept 5.700000000000000000000000000001 hours.",
    "<script>alert(172)</script>",
])
def test_validator_rejects_unprovided_numbers_length_and_banned_language(text):
    assert narrator.validate(text, FACTS) is None


def test_validator_keeps_formatted_numbers_and_complete_pace():
    text = "You slept 5.70 h. Your pace averaged 5:20 and cadence was 172 steps per minute."
    assert narrator.validate(text, FACTS) == text
    assert narrator.validate("Heart rate changed by −2 bpm.", FACTS)
    assert narrator.validate("Your score is 85/100.", {"Score": "85/100"})
    assert narrator.validate("Your score is 85/100.", {"Score": 85, "Scale": 100}) is None


@pytest.mark.parametrize("text", [
    "You are fully recovered. Go run hard today.",
    "Your recovery was 46 bpm.",
    "Your Garmin readiness score is 46.",
    "Garmin recorded a readiness score of 52. Have a hard session.",
])
def test_checked_sentences_reject_wrong_units_and_unsourced_advice(text):
    facts = {"recovery percent": 46, "Garmin readiness score": 52}
    assert not narrator._grounded(text, facts)
    assert narrator._grounded("Recovery is 46 %. Your Garmin readiness score is 52.", facts)
    assert narrator._grounded("Recovery is 46%. Your recovery score is 46%.", facts) == \
        "Recovery is 46%."


def test_provider_text_in_numeric_fields_is_not_included(conn, collected):
    collected["night"]["overall"] = "Provider text that should stay out of the prompt"
    packet = narrator.items(collected)["sleep"]
    assert packet.facts == {"sleep duration hours": 5.7}


@pytest.fixture
def collected(conn):
    day = datetime.now(UTC).date().isoformat()
    db.put_daily(conn, "ex_daily_summary", day, "export", {"calendarDate": day, "totalSteps": 300})
    db.upsert_activity(conn, {
        "activityId": 818283, "activityType": {"typeKey": "running"},
        "startTimeLocal": f"{day} 07:00:00", "duration": 1800,
        "distance": 5700, "averageHR": 150, "activityName": "Private name",
    })
    fit.store(conn, 818283, make_fit(n=150))
    conn.commit()
    rebuild(conn)
    trials.start(conn, "cadence", title="Private experiment title", target_spm=175)
    conn.execute("INSERT INTO sleep(day,sleep_s,score) VALUES (?,?,?)", (day, 20520, 77))
    conn.commit()
    data = dashboard.collect(conn)
    data.update(older_snapshot=False, night={"day": day, "overall": 77}, night_summary=(5.7, 77))
    data["scores"]["recovery"].update(pct=46, label="moderate", garmin_readiness=52)
    return data


@pytest.fixture
def http_fake(monkeypatch):
    calls = []
    answers = []

    class HTTP:
        def __init__(self, host, port, timeout):
            assert (host, port) == ("127.0.0.1", 11434)
            assert 0 < timeout <= 35

        def request(self, method, path, body, headers):
            assert headers["Host"] == "localhost:11434"
            assert "Authorization" not in headers
            calls.append((method, path, json.loads(body) if body else None))

        def getresponse(self):
            _, path, body = calls[-1]
            if path == "/api/show":
                result = (200, {"capabilities": ["completion"], "model_info": {"qwen.context_length": 32768}})
            elif path == "/api/generate" and body["prompt"] == "":
                result = (200, {"done": True})
            else:
                result = answers.pop(0)
            if isinstance(result, Exception):
                raise result
            self.status, self.body = result
            return self

        def read(self, _limit):
            if callable(self.body):
                self.body = self.body()
            return json.dumps(self.body).encode()

        def close(self):
            pass

    monkeypatch.setattr(narrator.http.client, "HTTPConnection", HTTP)
    return calls, answers


def test_opt_in_cache_and_input_boundaries(conn, collected, http_fake, monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "https://outside.invalid")
    monkeypatch.setenv("OLLAMA_HOST", "https://outside.invalid")
    monkeypatch.setenv("OLLAMA_API_KEY", "dummy-secret")
    calls, answers = http_fake
    assert narrator.settings(conn) == {"enabled": False, "model": narrator.DEFAULT_MODEL}
    assert not narrator.generate(conn, collected, time.monotonic() + 10)
    assert calls == []
    narrator.configure(conn, enable=True)
    texts = ["Recovery is 46%.", "You slept 5.7 h.",
             "The weekly count of workouts with load data was 1.",
             "The cadence target is 175 steps per minute.",
             "The run was 5.7 km."]
    answers.extend([(200, {"cloud": {"disabled": True}}), *(_answer(i) for i in (2, 3, 1, 3, 2))])
    assert narrator.generate(conn, collected, time.monotonic() + 10)
    assert [call[:2] for call in calls] == [
        ("GET", "/api/status"), ("POST", "/api/show"), *[("POST", "/api/generate")] * 6]
    inputs = [json.loads(body["prompt"]) for _, _, body in calls[3:]]
    assert [item["item"] for item in inputs] == ["today", "last night's sleep", "seven-day training review",
                                                 "active experiment", "run"]
    assert all(body["model"] == "qwen3.5:4b:local" and body["stream"] is False
               for _, _, body in calls[3:])
    assert "The run was 5.7 km." in calls[-1][2]["system"]
    assert 2 in calls[-1][2]["format"]["properties"]["selection"]["items"]["enum"]
    assert all(value not in str(calls) for value in ("818283", "Private name", "Private experiment"))
    summaries, pending = narrator.cached(conn, collected)
    assert not pending and [s["text"] for s in summaries.values()] == texts
    calls.clear()
    assert not narrator.generate(conn, collected, time.monotonic() + 10)
    assert calls == []
    collected["runs"][0]["km"] = 5.8
    answers.extend([(200, {"cloud": {"disabled": True}}), _answer(99)])
    assert not narrator.generate(conn, collected, time.monotonic() + 10)
    assert len(calls) == 4
    summaries, pending = narrator.cached(conn, collected)
    assert "run-818283" not in summaries and not pending  # rejects are cached too


@pytest.mark.parametrize("status", [
    ConnectionRefusedError(),
    (200, {"cloud": {"disabled": False}}),
    (200, {"cloud": {"disabled": "true"}}),
    (404, {}),
    (307, {"Location": "https://outside.invalid"}),
])
def test_unverified_local_service_never_receives_facts(conn, collected, http_fake, status):
    calls, answers = http_fake
    narrator.configure(conn, enable=True)
    answers.append(status)
    assert not narrator.generate(conn, collected, time.monotonic() + 10)
    assert calls == [("GET", "/api/status", None)]
    assert narrator.cached(conn, collected) == ({}, True)


@pytest.mark.parametrize("model", [
    "gemma4:cloud", "qwen:7b-cloud", "qwen:3b:local", "ollama.com/model",
    "https://outside.invalid", "  ", "name\nother",
])
def test_settings_reject_cloud_or_external_model(conn, model):
    with pytest.raises(ValueError, match="downloaded local"):
        narrator.configure(conn, enable=True, model=model)
    assert not narrator.settings(conn)["enabled"]


@pytest.mark.parametrize(("legacy", "expected", "rebuild_needed"), [
    ("qwen2.5:3b-instruct", "qwen3.5:4b", True),
    ("qwen3.5:9b", "qwen3.5:9b", False),
])
def test_default_model_upgrade_only_changes_the_former_default(conn, legacy, expected, rebuild_needed):
    path = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    state = {"enabled": True, "thinking": True, "thinking_minutes": 5, "model": legacy}
    with conn:
        conn.execute("DELETE FROM meta WHERE key='narrator_qwen35_default'")
        conn.execute("INSERT INTO meta VALUES ('ai_narrator', ?)", (json.dumps(state),))

    with closing(db.connect(path)) as upgraded:
        assert narrator.settings(upgraded) == {**state, "model": expected}
        pending = upgraded.execute("SELECT 1 FROM meta WHERE key='dashboard_rebuild_pending'").fetchone()
        assert bool(pending) is rebuild_needed
        narrator.configure(upgraded, model="qwen2.5:3b-instruct")

    with closing(db.connect(path)) as reopened:
        assert narrator.settings(reopened)["model"] == "qwen2.5:3b-instruct"


def test_total_budget_cuts_off_slow_response(conn, collected, http_fake):
    def slow():
        time.sleep(2)
        return _answer(2)[1]

    calls, answers = http_fake
    narrator.configure(conn, enable=True)
    answers.extend([(200, {"cloud": {"disabled": True}}), (200, slow)])
    started = time.monotonic()
    assert not narrator.generate(conn, collected, started + 0.05)
    assert time.monotonic() - started < 1
    assert len(calls) == 4


def test_snapshot_first_and_background_enrichment(conn, collected, http_fake, tmp_path, monkeypatch):
    calls, answers = http_fake
    monkeypatch.setattr(dashboard, "collect", lambda _: collected.copy())
    queued = []

    def queue(connection, path, snapshot):
        assert "Next seven days" in path.read_text() and "AI summary" not in path.read_text()
        assert calls == []
        queued.append((Path(connection.execute("PRAGMA database_list").fetchone()[2]),
                       path.parent, snapshot))

    monkeypatch.setattr(narrator, "start_worker", queue)
    narrator.configure(conn, enable=True)
    path = dashboard.build(conn, tmp_path)
    assert len(queued) == 1
    answers.extend([(200, {"cloud": {"disabled": True}}), *(_answer(i) for i in (2, 3, 1, 3, 2))])
    narrator._worker(*queued[0])
    html = path.read_text()
    assert html.count("AI summary · facts checked") == html.count("Show the facts") == 6
    assert html.index("Next seven days") < html.index("Recovery is 46%.")
    assert "Recovery percent: 46" in html
    assert "The run was 5.7 km." in html and "Distance km: 5.7" in html
    assert "What to try next" in html
    assert "last accepted" in html
    before = len(calls)
    dashboard.build(conn, tmp_path, queue_narration=True)
    assert len(queued) == 1 and len(calls) == before
    # The old worker can't overwrite a newly rendered snapshot.
    narrator._worker(*queued[0])
    assert len(calls) == before


def test_render_status_changes_when_cloud_gate_blocks_worker(conn, collected, http_fake, tmp_path, monkeypatch):
    _, answers = http_fake
    monkeypatch.setattr(dashboard, "collect", lambda _: collected.copy())
    queue = []
    monkeypatch.setattr(narrator, "start_worker", lambda _, path, snapshot: queue.append((path.parent, snapshot)))
    narrator.configure(conn, enable=True)
    path = dashboard.build(conn, tmp_path)
    assert "waiting for review" in path.read_text()
    answers.append((200, {"cloud": {"disabled": False}}))
    narrator._worker(Path(conn.execute("PRAGMA database_list").fetchone()[2]), *queue[0])
    assert "waiting for confirmation that Ollama cloud is off" in path.read_text()
    monkeypatch.setattr(dashboard, "_snapshot_paths", lambda _dir: (path, None))
    narrator.update_settings(conn, enable=False, model=None)
    assert "AI summary" not in path.read_text() and "Next seven days" in path.read_text()

def test_workout_packet_and_page_use_only_recorded_facts(collected):
    workout = {"id": 567, "name": "Private cycling route", "type": "cycling",
               "start": "2026-11-23 08:00:00", "duration": "1:10:29",
               "distance_km": 19.8, "avg_hr": 128}
    collected["workouts"] = [workout]
    day = workout["start"][:10]
    collected["calendar"]["days"].setdefault(day, {}).setdefault("activities", []).append(workout)
    if day not in collected["calendar"]["detail_days"]:
        collected["calendar"]["detail_days"].append(day)
    item = narrator.items(collected)["workout-567"]
    assert item.facts == {"workout duration": "1:10:29", "workout distance km": 19.8,
                          "average heart rate bpm": 128}
    assert "Private cycling route" not in item.prompt and "567" not in item.prompt
    text = "The workout lasted 1:10:29. You covered 19.8 km in this workout."
    assert item.response('{"selection":[1,4]}') == text
    assert item.response('{"selection":[0,4]}') is None
    html = dashboard.render({**collected, "narration": {"workout-567": {"text": text,
                                                                       "facts": item.facts}}})
    assert 'href="#workout-567"' in html and 'id="workout-567"' in html
    assert "AI summary · facts checked" in html and 'id="run-818283-pacing"' in html
    assert 'class="page" id="run-818283-pacing"' not in html


def test_model_prioritizes_only_eligible_followups(conn, collected, monkeypatch):
    focus = collected["brief"]["focus"]
    focus.update(target="recovery", findings=[
        {"title": "Check resting heart rate", "detail": "Resting pulse averaged higher.",
         "target": "recovery"},
        {"title": "Make room for more sleep", "detail": "Sleep averaged below your goal.", "target": "sleep",
         "basis": "Six recorded nights compared with your usual sleep."},
        {"title": "Check watch fit", "detail": "An overnight reading was below your range.",
         "target": "recovery"},
    ])
    item = narrator.items(collected)["focus"]
    assert item.response('{"choice":2}') == 2
    for raw in ('{"choice":4}', '{"choice":true}', '{"choice":2,"text":"extra"}', '<?untrusted>'):
        assert item.response(raw) is None
    narrator.configure(conn, enable=True)
    monkeypatch.setattr(narrator, "items", lambda _: {"focus": item})
    monkeypatch.setattr(narrator, "_request", lambda method, *_: {"cloud": {"disabled": True}}
                        if method == "GET" else {"done": True, "response": '{"choice":2}'})
    assert narrator.generate(conn, collected, time.monotonic() + 10)
    summaries, pending = narrator.cached(conn, collected)
    original_title = focus["title"]
    collected["trial"] = None
    collected["runs"][0]["cadence_experiment"] = {"suggestion": "Try shorter steps.", "check": "Check pace."}
    today = dashboard.page_today({**collected, "narration": summaries})
    assert not pending and original_title in today
    assert today.index("AI-prioritized follow-up") < today.index("Make room for more sleep")
    assert today.index("Make room for more sleep") < today.index("Check resting heart rate")
    assert "Check watch fit" in today and "Try shorter steps." in today
    assert 'href="#sleep"' in today


def test_diagnostics_distinguish_cache_from_file(conn, collected, http_fake, tmp_path, monkeypatch):
    calls, answers = http_fake
    monkeypatch.setattr(dashboard, "collect", lambda _: collected.copy())
    monkeypatch.setattr(dashboard, "_snapshot_paths", lambda *_: (tmp_path / "index.html", None))
    narrator.configure(conn, enable=True)
    answers.extend([(200, {"cloud": {"disabled": True}}),
                    (200, {"models": [{"name": narrator.DEFAULT_MODEL}]})] * 2)
    status = narrator.check(conn)
    assert status["ollama"] == "ready" and not status["cache_matches_dashboard"]
    assert status["coverage"]["today"] == {"pending": 1, "ready": 0, "rejected": 0}
    dashboard.build(conn, queue_narration=False)
    assert narrator.check(conn)["cache_matches_dashboard"]
    assert all(path in {"/api/status", "/api/tags", "/api/show"} for _, path, _ in calls)


def test_diagnostics_report_decision_only_models(conn, monkeypatch):
    model = "nimble-v3:9b-q4_K_M"
    narrator.configure(conn, model=model)
    responses = {
        "/api/status": {"cloud": {"disabled": True}},
        "/api/tags": {"models": [{"name": model}]},
        "/api/show": {"capabilities": ["decision"]},
    }
    monkeypatch.setattr(narrator, "_request", lambda _, path, *_args: responses[path])
    status = narrator.check(conn)
    assert status["ollama"] == "model_does_not_support_text_generation"
    assert status["model_profile"]["text_generation"] is False


def test_cited_voice_accepts_composition_and_rejects_unsupported_meaning():
    item = narrator.Item("sleep", {"sleep duration hours": 5.7, "Garmin sleep score": 75})
    fallback = "You slept 5.7 hours."
    text = "You slept 5.70 hours, while Garmin recorded a sleep score of 75."
    assert item.response(json.dumps({"selection": [1], "voice": [{"text": text, "facts": [1, 4]}]})) == text
    for invented, ids in (
        ("You slept 5.7 hours because you trained too late.", [1]),
        ("You should run for 5.7 hours.", [1]),
        ("You slept 5.7 hours and Garmin recorded a sleep score of 75.", [1]),
        ("You slept 6 hours.", [1]),
    ):
        assert item.response(json.dumps({"selection": [1], "voice": [{"text": invented, "facts": ids}]})) == fallback


def test_thinking_setup_requests_final_answer_only(monkeypatch):
    requests = []

    def request(_, path, deadline, body):
        requests.append((path, body))
        if path == "/api/show":
            return {"capabilities": ["thinking"], "model_info": {"qwen.context_length": 1024}}
        return {"done": True, "thinking": "Something unchecked", "response": '{"selection":[1]}'}

    monkeypatch.setattr(narrator, "_request", request)
    model = "qwen3.5:4b"
    deadline = time.monotonic() + 10
    profile = narrator._model_profile(model, deadline)
    narrator._warm(model, profile, deadline)
    assert requests[1][1]["prompt"] == ""
    item = narrator.Item("measured sleep", {"sleep duration hours": 6})
    assert narrator._infer(model, profile, item, deadline) == ("You slept 6 hours.", "accepted")
    assert requests[-1][1]["think"] is False
    assert requests[-1][1]["options"]["num_ctx"] == 1024
