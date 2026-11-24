import json
from datetime import date
from zoneinfo import ZoneInfo

import pytest

from garmin_mcp import trials


def test_start_validates_and_replaces(conn):
    with pytest.raises(ValueError):
        trials.start(conn, "cadence")  # no runs to base a target on
    with pytest.raises(ValueError):
        trials.start(conn, "cadence", target_spm=230)
    with pytest.raises(ValueError):
        trials.start(conn, "custom")  # needs a title
    first = trials.start(conn, "cadence", target_spm=175)
    assert first["target"] == {"cadence_spm": 175}
    second = trials.start(conn, "custom", title="Lights out by 01:00")
    rows = [tuple(r) for r in conn.execute("SELECT id, status FROM coach_trials ORDER BY id")]
    assert rows == [(first["trial_id"], "closed"), (second["trial_id"], "active")]
    assert trials.status(conn)["trial"]["title"] == "Lights out by 01:00"


def test_log_scales_and_requires_trial(conn):
    with pytest.raises(ValueError):
        trials.log(conn, knee_during=2)  # no active trial
    trials.start(conn, "custom", title="x")
    with pytest.raises(ValueError):
        trials.log(conn, knee_during=11)
    with pytest.raises(ValueError):
        trials.log(conn, felt=0)
    out = trials.log(conn, knee_during=1, knee_next_morning=0, felt=4, effort=3, note="ok")
    assert out["activity_id"] is None  # no runs yet


def test_garmin_feel_all_payload_shapes(conn):
    trials.ensure(conn)
    for aid, summary in ((1, {"summaryDTO": {"workoutFeel": 75, "workoutRpe": 40}}),
                         (2, {"_export": {"workoutFeel": 100, "workoutRpe": 30}}),
                         (3, {"workoutFeel": 33, "workoutRpe": 500})):
        conn.execute("INSERT INTO activities(activity_id, type, start_time_local, summary, "
                     "updated_at) VALUES (?,?,?,?,?)", (aid, "running", "2026-11-01 07:00:00",
                                                        json.dumps(summary), "x"))
    assert trials.garmin_feel(conn, 1) == {"felt": "strong", "effort_1_10": 4}
    assert trials.garmin_feel(conn, 2) == {"felt": "very strong", "effort_1_10": 3}
    assert trials.garmin_feel(conn, 3) == {}  # unknown codes are ignored, not guessed


def test_change_verdicts_respect_noise():
    hr = trials._change("avg_hr", 150, [155, 156, 157], "bpm", "lower")
    assert hr["verdict"] == "better" and hr["change"] == -6
    same = trials._change("avg_hr", 155, [154, 156], "bpm", "lower")
    assert same["verdict"] == "about the same"
    ef = trials._change("efficiency_factor", 1.10, [1.0, 1.0], "", "higher")
    assert ef["verdict"] == "better" and ef["change_pct"] == 10.0
    cad = trials._change("cadence_spm", 170, [162, 163], "steps/min", "neutral", 0)
    assert cad["verdict"] == "higher"
    assert trials._change("avg_hr", None, [150], "bpm", "lower") is None


def test_next_step_puts_knee_safety_first():
    trial = {"target": {"cadence_spm": 175}}
    sore = [{"your_notes": {"knee_next_morning": 5}, "did_it": {"available": True,
                                                                "minutes_at_target": 6}}]
    assert "Stop the trial" in trials._next(trial, sore)
    missing = [{"your_notes": {}, "did_it": {"available": True, "minutes_at_target": 6}}]
    assert "morning" in trials._next(trial, missing)
    few = [{"your_notes": {"knee_next_morning": 0},
            "did_it": {"available": True, "minutes_at_target": 1}}]
    assert "one-minute blocks" in trials._next(trial, few)
    assert trials._next(trial, []) == "Try it on your next easy run."


def test_summary_and_verdict_wording():
    attempt = {"did_it": {"available": True, "minutes_at_target": 5.0, "moving_minutes": 30.0},
               "garmin_feel": {"felt": "strong", "effort_1_10": 4},
               "your_notes": {"knee_during": 1, "knee_next_morning": 0},
               "changes": [{"metric": "avg_hr", "change": -4.0, "unit": "bpm",
                            "verdict": "better"}]}
    text = trials._sentence(attempt, 175)
    assert text.startswith("5 of 30 minutes at or near 175 steps/min")
    assert "felt strong" in text and "heart rate -4 bpm" in text
    assert trials._verdict([attempt]).startswith("Early")
    three = [dict(attempt, changes=[{"metric": "efficiency_factor", "change_pct": 1.0}])] * 3
    assert "about the same" in trials._verdict(three)
    mixed = [three[0], {**attempt, "changes": []}, {**attempt, "changes": []}]
    assert "1 comparable pace-and-pulse" in trials._verdict(mixed)
    assert "about the same" not in trials._verdict(mixed)


def test_historical_trial_excludes_later_runs_and_notes(conn, monkeypatch):
    from garmin_mcp import coaching

    trial = trials.start(conn, "custom", title="Try a new cue")["trial_id"]
    conn.execute("UPDATE coach_trials SET created=?, status='closed', closed=? WHERE id=?",
                 ("2026-11-18T12:00:00+00:00", "2026-11-22T12:00:00+00:00", trial))
    conn.executemany("INSERT INTO activities(activity_id,type,start_time_local,fit_parsed,"
                     "updated_at) VALUES (?,'running',?,1,'x')",
                     [(1, "2026-11-19 07:00:00"), (2, "2026-11-20 07:00:00")])
    conn.executemany("INSERT INTO coach_trial_logs(trial_id,activity_id,logged,knee_next_morning) "
                     "VALUES (?,1,?,?)",
                     [(trial, "2026-11-19T03:00:00+00:00", 1),
                      (trial, "2026-11-19T19:00:00+00:00", 6)])
    monkeypatch.setattr(coaching, "run_metrics", lambda *_: {"avg_speed": 3.0})

    zone = ZoneInfo("Asia/Kolkata")
    assert not trials.status(conn, through=(date(2026, 11, 17), zone))["active"]
    result = trials.status(conn, through=(date(2026, 11, 19), zone))
    assert result["active"] and result["trial"]["closed"] is None
    assert [a["activity_id"] for a in result["attempts"]] == [1]
    assert result["attempts"][0]["your_notes"]["knee_next_morning"] == 1
    assert not trials.status(conn, through=(date(2026, 11, 23), zone))["active"]
