"""Clause-checked drafting for the Running and weekly reviews. All values are invented."""

import json
import time

import pytest

from garmin_mcp import clauses, deep_insight, narrator


def running_packet():
    pacing = ({"pace_s_per_km": 402, "hr": 147}, {"pace_s_per_km": 389, "hr": 156})
    rows = deep_insight.running_review({
        "running_block": {"recent": {"runs": 7, "days": 7}, "previous": {"runs": 10, "days": 10},
                          "median_decoupling": 6.4, "decoupling_count": 5, "latest_detail_id": 1},
        "runs": [{"activity_id": 1,
                  "comparable_effort": {"available": True, "observed_hr_range_bpm": (141, 150),
                                        "this_run": {"avg_hr_bpm": 153}},
                  "pacing": {"effort_halves": pacing},
                  "late_form": {"cadence_spm": {"early": 166, "late": 163, "matched_s": 365}},
                  "form": {"cadence_spm": {"value": 171, "matched_range": (164, 169)}}}],
    })
    return deep_insight.Insight(rows, "running_review")


def weekly_packet(change=-48):
    rows = deep_insight.sunday_review({
        "end": "2026-11-22",
        "weekly_review": {"week": {"sessions": 1}, "previous_4wk_weekly_avg": {"sessions": 2.25}},
        "sleep_review": {"windows": {7: {"nights": 5, "hours": 6.1}}, "week_change_min": change,
                         "anchor": {"spread": 130}},
    })
    return deep_insight.Insight(rows, "sunday_review")


def ids(packet):
    return {row.domain if row.domain != "sleep" else row.text.split()[0].lower(): number
            for number, row in enumerate(packet.rows, 1)}


def draft(*parts):
    return json.dumps({"parts": [{"evidence": number, "text": text} for number, text in parts]})


TRUE = {
    "consistency": "Runs fell on fewer days than in the four weeks before",
    "matched effort": "latest moving heart rate was above earlier comparable runs",
    "pacing": "the latest run was faster in its second half while pulse rose",
    "matched mechanics": "cadence was lower late than early within the latest run",
    "running form": "latest cadence was above the span of earlier comparable runs",
    "training": "The workout count was lower than the previous four weeks' weekly average",
    "sleep": "average sleep was less per night than last week",
}


def assess(packet, *parts):
    return packet.assess(draft(*parts), concise=True)


def test_two_checked_clauses_become_one_sentence_with_a_python_question():
    packet = weekly_packet()
    i = ids(packet)
    result, reason = assess(packet, (i["training"], TRUE["training"] + "."), (i["sleep"], TRUE["sleep"]))
    assert reason == "valid"
    assert result["observation"] == (f"{TRUE['training']}, while {TRUE['sleep']}.")
    assert result["evidence"] == [i["training"], i["sleep"]]
    assert result["question"] == packet._repeat_question(result["evidence"])


@pytest.mark.parametrize("domain", ["matched effort", "pacing", "matched mechanics", "running form"])
def test_every_checkable_running_reading_accepts_a_faithful_clause(domain):
    packet = running_packet()
    i = ids(packet)
    result, reason = assess(packet, (i["consistency"], TRUE["consistency"]), (i[domain], TRUE[domain]))
    assert reason == "valid", result


@pytest.mark.parametrize(("domain", "text"), [
    # Each of these kinds of statement was accepted by the live model review.
    ("training", "The workout count was higher than the previous four weeks' average"),
    ("training", "The workout count was lower than last week"),
    ("training", "Training volume was lower than the previous four weeks"),
    ("sleep", "sleep per night fell compared with the previous four weeks"),
    ("sleep", "average sleep was more per night than last week"),
    ("sleep", "average sleep was not less per night than last week"),
    ("sleep", "average sleep was less per night"),
    ("sleep", "resting pulse was lower than last week"),
])
def test_wrong_weekly_clauses_are_rejected_before_model_review(domain, text):
    packet = weekly_packet()
    i = ids(packet)
    other = "sleep" if domain == "training" else "training"
    result, reason = assess(packet, (i[domain], text), (i[other], TRUE[other]))
    assert result is None and reason in {"wrong_comparison", "unsupported_claim", "uncited_number"}


@pytest.mark.parametrize(("domain", "text"), [
    ("consistency", "Runs rose to more days than in the four weeks before"),
    ("matched effort", "latest moving heart rate was within earlier comparable runs"),
    ("matched effort", "latest moving heart rate was above last week's average"),
    ("pacing", "the latest run was slower in its second half while pulse rose"),
    ("pacing", "the latest run was faster in its second half while pulse fell"),
    ("matched mechanics", "cadence was higher late than early within the latest run"),
    ("matched mechanics", "cadence fell compared with earlier runs"),
    ("running form", "latest cadence was below the span of earlier comparable runs"),
])
def test_wrong_running_clauses_are_rejected_before_model_review(domain, text):
    packet = running_packet()
    i = ids(packet)
    other = "matched effort" if domain == "consistency" else "consistency"
    assert assess(packet, (i[other], TRUE[other]), (i[domain], text))[0] is None


@pytest.mark.parametrize("text", [
    "sleep was less last week than the week before",
    "sleep was less last week compared with this week",
    "compared with this week, last week had less sleep",
])
def test_the_current_reading_cannot_move_onto_the_comparison_period(text):
    packet = weekly_packet()
    i = ids(packet)
    assert assess(packet, (i["training"], TRUE["training"]), (i["sleep"], text)) == (None, "wrong_comparison")


@pytest.mark.parametrize("text", [
    "sleep per night was shorter this week than last week",
    "average nightly sleep fell compared with the week before",
])
def test_natural_week_wording_is_accepted(text):
    packet = weekly_packet()
    i = ids(packet)
    assert assess(packet, (i["training"], TRUE["training"]), (i["sleep"], text))[1] == "valid"


def test_guide_wording_passes_its_own_check():
    for packet in (running_packet(), weekly_packet(34), weekly_packet(0)):
        for number in packet.checkable:
            claim = packet.rows[number - 1].claim
            told = clauses.guide(claim)
            if claim.pace:
                text = f"pace was {claim.pace} and pulse was higher {told['period']} {told['ending']}"
            elif claim.trend:
                text = f"{told['measure']} was {told['direction']} {told['period']} {told['ending']}"
            else:
                text = "wake times varied this week"
            assert clauses.check(text, claim) is None, text


@pytest.mark.parametrize("text", [
    "sleep was shorter this week as in place of last week",
    "sleep was shorter as last week",
    "sleep was shorter this week than compared with last week",
])
def test_garbled_comparisons_are_not_published(text):
    packet = weekly_packet()
    i = ids(packet)
    result, reason = assess(packet, (i["training"], TRUE["training"]), (i["sleep"], text))
    assert result is None and reason in {"unsupported_wording", "wrong_comparison"}


def test_amounts_in_words_need_to_come_from_the_cited_reading():
    packet = weekly_packet()
    i = ids(packet)
    for text in ("average sleep was about half an hour less than last week",
                 "average sleep was an hour less per night than last week",
                 "average sleep was 48 min less than last week, about three quarters"):
        assert assess(packet, (i["training"], TRUE["training"]), (i["sleep"], text)) == (None, "uncited_number")


def test_questions_suggestions_and_same_domain_pairs_are_rejected():
    packet = weekly_packet()
    i = ids(packet)
    good = (i["training"], TRUE["training"])
    for text in ("Does sleep stay less than last week?",
                 "sleep was less than last week. Check it again on the next run",
                 "sleep was less than last week " * 5):
        assert assess(packet, good, (i["sleep"], text)) == (None, "unsupported_wording")
    assert assess(packet, (i["sleep"], TRUE["sleep"]), (i["wake"], "wake times varied")) == (
        None, "missing_citations")
    assert assess(packet, good, good) == (None, "missing_citations")
    assert packet.assess("{}", concise=True) == (None, "invalid_response")


def test_unchecked_readings_are_left_out_of_clause_drafting_but_not_selection():
    packet = running_packet()
    endurance = ids(packet)["endurance"]
    offered = packet.concise_schema["properties"]["parts"]["items"]["properties"]["evidence"]["enum"]
    assert endurance not in offered
    assert endurance not in [row["id"] for row in json.loads(packet.concise_prompt)]
    assert any(endurance in pair for pair in packet.comparison_options())


def test_drafter_is_told_each_direction_and_comparison_period():
    packet = weekly_packet()
    rows = {row["id"]: row for row in json.loads(packet.concise_prompt)}
    i = ids(packet)
    assert rows[i["training"]]["direction"] == "lower"
    assert rows[i["sleep"]]["direction"] == "shorter"
    assert rows[i["training"]]["ending"] == "than the previous four weeks' average"
    assert rows[i["sleep"]]["ending"] == "than last week"
    assert rows[i["sleep"]]["period"] == "this week"
    assert "direction" not in rows[i["wake"]]
    assert "2026" not in packet.concise_prompt


def test_other_surfaces_keep_free_observation_drafting():
    for case in ("today-written", "sleep-written", "mixed-recovery"):
        lens, rows = deep_insight.FICTIONAL_CASES[case]
        packet = deep_insight.Insight(rows, lens)
        assert packet.concise_schema["required"] == ["observation", "evidence"]
        assert packet.concise_prompt == packet.prompt


@pytest.mark.parametrize("case", ["running-block", "sunday-review"])
def test_fictional_cases_use_clause_drafting_end_to_end(case, monkeypatch):
    lens, rows = deep_insight.FICTIONAL_CASES[case]
    packet = deep_insight.Insight(rows, lens)
    i = ids(packet)
    parts = (((i["consistency"], "Runs covered more days than in the four weeks before"),
              (i["matched effort"], "latest moving heart rate was within earlier comparable runs"))
             if case == "running-block" else
             ((i["training"], "The workout count was higher than the previous four weeks' average"),
              (i["sleep"], TRUE["sleep"])))
    sent = []

    def request(method, path, deadline, body):
        sent.append(body)
        verdict = body["format"]["required"] == ["verdict"]
        return {"done": True, "response": '{"verdict":"supported"}' if verdict else draft(*parts)}

    monkeypatch.setattr(narrator, "_request", request)
    result = narrator._deep_request("test:4b", {"num_ctx": 4096}, packet, time.monotonic() + 240,
                                    think_first=False)
    assert result["mode"] == "direct"
    assert sent[0]["format"] == packet.concise_schema and sent[0]["prompt"] == packet.concise_prompt
    assert sent[0]["options"]["num_predict"] == 160
    assert json.loads(sent[1]["prompt"])["draft"]["observation"] == result["observation"]


def test_repeat_questions_do_not_assume_the_result():
    packet = running_packet()
    i = ids(packet)
    for pair in packet.comparison_options():
        assert "same range" not in packet._repeat_question(list(pair))
    assert packet._repeat_question([i["consistency"], i["matched effort"]]) == (
        "Where does moving pulse fall against your earlier range on another run at a similar pace?")


@pytest.mark.parametrize(("failure", "reason"), [
    (ConnectionRefusedError(), "unreachable"),
    (TimeoutError(), "timed_out"),
    (500, "server_error"),
    ({"done": True, "done_reason": "length", "response": "x"}, "reply_truncated"),
])
def test_an_incomplete_pass_records_why(conn, monkeypatch, failure, reason):
    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            if isinstance(failure, BaseException):
                raise failure

        def getresponse(self):
            status = failure if isinstance(failure, int) else 200
            body = json.dumps(failure).encode()
            return type("Reply", (), {"status": status, "read": lambda self, _: body})()

        def close(self):
            pass

    lens, rows = deep_insight.FICTIONAL_CASES["sunday-review"]
    narrator.configure(conn, True, "test:4b")
    monkeypatch.setattr(narrator.http.client, "HTTPConnection", Client)
    monkeypatch.setattr(narrator, "items", lambda _: {})
    monkeypatch.setattr(narrator, "_deep_items", lambda *_: {"sunday-insight": deep_insight.Insight(rows, lens)})
    monkeypatch.setattr(narrator, "_cloud_disabled", lambda _: True)
    monkeypatch.setattr(narrator, "_warm", lambda *_: None)
    monkeypatch.setattr(narrator, "_model_profile",
                        lambda *_: {"thinking": False, "text_generation": True, "num_ctx": 2048})
    assert not narrator.generate(conn, {}, time.monotonic() + 500)
    state = narrator._worker_status(conn, "test:4b")
    assert state["outcome"] == "incomplete" and state["incomplete_reasons"] == {reason: 1}
    monkeypatch.setattr(narrator, "_deep_request", lambda *args, **kwargs: None)
    narrator.generate(conn, {}, time.monotonic() + 500)
    assert "incomplete_reasons" not in narrator._worker_status(conn, "test:4b")


def test_a_recent_average_can_be_named_after_the_comparison_word():
    packet = weekly_packet()
    i = ids(packet)
    text = "Fewer workouts were recorded this week than the recent four-week average"
    assert assess(packet, (i["training"], text), (i["sleep"], TRUE["sleep"]))[1] == "valid"


def test_a_clause_cannot_add_an_unchecked_claim_about_another_measure():
    packet = running_packet()
    i = ids(packet)
    good = (i["consistency"], TRUE["consistency"])
    for text in ("latest pulse was higher and faster than earlier comparable runs",
                 "latest pulse was higher than earlier comparable runs with slower pace"):
        assert assess(packet, good, (i["matched effort"], text)) == (None, "wrong_comparison")
    kept = "latest pulse was higher at a similar pace than earlier comparable runs"
    assert assess(packet, good, (i["matched effort"], kept))[1] == "valid"


def test_one_comparison_is_not_called_a_trend():
    packet = weekly_packet()
    i = ids(packet)
    text = "sleep was shorter this week than last week in a downward trend"
    assert assess(packet, (i["training"], TRUE["training"]), (i["sleep"], text)) == (None, "unsupported_claim")
    lens, rows = deep_insight.FICTIONAL_CASES["sleep-written"]
    free = {"evidence": [1, 2], "observation": "Average sleep rose this week while HRV showed a downward trend."}
    assert deep_insight.Insight(rows, lens).assess(json.dumps(free), concise=True) == (None, "unsupported_claim")


def test_a_single_running_day_reads_as_singular():
    rows = deep_insight.running_review({
        "running_block": {"recent": {"runs": 1, "days": 1}, "previous": {"runs": 3, "days": 3},
                          "median_decoupling": 2.0, "decoupling_count": 3},
    })
    assert "occupied 1 day in the last four" in rows[0].text and "versus 3 in" in rows[0].text
