import json
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import make_fit

from garmin_mcp import dashboard, db, fit, narrator, trials
from garmin_mcp.normalize import rebuild

FACTS = {"Sleep hours": 5.7, "Cadence": 172, "Pace": "5:20", "Heart rate change": -2}


def _answer(*sentences):
    return 200, {"done": True, "response": json.dumps({"sentences": sentences})}


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
    assert not narrator._grounded("Recovery is 46%. Your recovery score is 46%.", facts)


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
            assert 0 < timeout <= 20

        def request(self, method, path, body, headers):
            assert headers["Host"] == "localhost:11434"
            assert "Authorization" not in headers
            calls.append((method, path, json.loads(body) if body else None))

        def getresponse(self):
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
    texts = ["Recovery is 46%.", "You slept 5.7 h.", "The cadence target is 175 steps per minute.",
             "The run was 5.7 km."]
    answers.extend([(200, {"cloud": {"disabled": True}}), *(_answer(t) for t in texts)])
    assert narrator.generate(conn, collected, time.monotonic() + 10)
    assert [call[:2] for call in calls] == [
        ("GET", "/api/status"), *[("POST", "/api/generate")] * 4]
    inputs = [json.loads(body["prompt"]) for _, _, body in calls[1:]]
    assert [item["item"] for item in inputs] == ["today", "last night's sleep", "active experiment",
                                                 "run"]
    assert all(body["model"] == "qwen2.5:3b-instruct:local" and body["stream"] is False
               for _, _, body in calls[1:])
    assert "The run was 5.7 km." in calls[-1][2]["format"]["properties"]["sentences"]["items"]["enum"]
    assert all(value not in str(calls) for value in ("818283", "Private name", "Private experiment"))
    summaries, pending = narrator.cached(conn, collected)
    assert not pending and [s["text"] for s in summaries.values()] == texts
    calls.clear()
    assert not narrator.generate(conn, collected, time.monotonic() + 10)
    assert calls == []
    collected["runs"][0]["km"] = 5.8
    answers.extend([(200, {"cloud": {"disabled": True}}), _answer("The run was 99 km.")])
    assert not narrator.generate(conn, collected, time.monotonic() + 10)
    assert len(calls) == 2
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


def test_total_budget_cuts_off_slow_response(conn, collected, http_fake):
    def slow():
        time.sleep(2)
        return _answer("Recovery is 46%.")[1]

    calls, answers = http_fake
    narrator.configure(conn, enable=True)
    answers.extend([(200, {"cloud": {"disabled": True}}), (200, slow)])
    started = time.monotonic()
    assert not narrator.generate(conn, collected, started + 0.05)
    assert time.monotonic() - started < 1
    assert len(calls) == 2


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
    path = dashboard.build(conn, tmp_path, queue_narration=True)
    assert len(queued) == 1
    answers.extend([(200, {"cloud": {"disabled": True}}), *(_answer(t) for t in [
                            "Recovery is 46%.", "You slept 5.7 h.",
                            "The cadence target is 175 steps per minute.",
                        "The run was 5.7 km."])])
    narrator._worker(*queued[0])
    html = path.read_text()
    assert html.count("AI summary · facts checked") == html.count("Show the facts") == 4
    assert html.index("Next seven days") < html.index("Recovery is 46%.")
    assert "Recovery percent: 46" in html
    assert "The run was 5.7 km." in html and "Distance km: 5.7" in html
    assert "What to try next" in html
    before = len(calls)
    dashboard.build(conn, tmp_path, queue_narration=True)
    assert len(queued) == 1 and len(calls) == before
    # The old worker can't overwrite a newly rendered snapshot.
    narrator._worker(*queued[0])
    assert len(calls) == before
    monkeypatch.setattr(dashboard, "_snapshot_paths", lambda _dir: (path, None))
    narrator.update_settings(conn, enable=False, model=None)
    assert "AI summary" not in path.read_text() and "Next seven days" in path.read_text()
