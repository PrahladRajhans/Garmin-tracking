"""Allowlisted evidence and validation for a model-authored interpretation."""

import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import combinations
from pathlib import Path

from garmin_mcp import clauses
from garmin_mcp.config import data_dir

INSIGHT_CONTRACT = 5
POST_RUN_CONTRACT = 1


@dataclass(frozen=True)
class Evidence:
    domain: str
    text: str
    page: str
    previous: bool = False
    claim: clauses.Claim | None = field(default=None, compare=False)


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def evidence(data):
    if data.get("available") is False or data.get("older_snapshot") or data.get("sync_retry_required"):
        return ()
    result = []
    for key, label, unit, domain, page in (
        ("sleep_h", "Sleep duration", "h", "sleep", "sleep"),
        ("resting_hr", "Resting heart rate", "bpm", "recovery", "recovery"),
    ):
        signal = data.get("signals", {}).get(key, {})
        a, b = signal.get("recent"), signal.get("previous")
        if all(_number(v) for v in (a, b)):
            result.append(Evidence(domain, f"{label} averaged {a:.1f} {unit} "
                                   f"over {signal['recent_count']} readings this week versus "
                                   f"{b:.1f} {unit} over {signal['previous_count']} the previous week.", page))
    shortfall = data.get("sleep_shortfall") or {}
    if (prior := shortfall.get("previous_min")) is not None:
        current = shortfall["current"]["valid_nights_7d"]
        previous = shortfall["previous"]["valid_nights_7d"]
        result.append(Evidence("sleep", f'Garmin or fallback sleep targets were missed by '
                               f'{shortfall["per_night_min"]} min per usable night across {current} nights '
                               f'versus {prior} min across {previous} the prior week.', "sleep"))
    pulse = data.get("calendar", {}).get("days", {}).get(data.get("end"), {}).get("resting_pulse_check")
    if pulse and pulse["verify"] and pulse["median"] is not None:
        relation = {"lower": "below", "higher": "above", "near": "within"}[pulse["direction"]]
        history = []
        for key, scope in (("90 days", "the prior 90 days"), ("Full archive", "all earlier archive records")):
            window = pulse.get("coverage", {}).get(key, {})
            if typical := window.get("typical"):
                history.append(f'{typical[0]:g} bpm over {window["count"]} readings from {scope}')
        context = f' Other medians: {"; ".join(history)}.' if history else ""
        result.append(Evidence("recovery", f'The latest Garmin daily resting estimate was '
                               f'{pulse["value"]:g} bpm, {relation} the personal review range '
                               f'with a median of {pulse["median"]:g} bpm over {pulse["count"]} readings '
                               'in the prior 28 days. Garmin’s estimate can include sleep.' + context, "recovery"))
    hrv = data.get("hrv_context", {})
    a, b = hrv.get("rolling_7d_ms"), hrv.get("previous_average")
    if all(_number(v) for v in (a, b)):
        result.append(Evidence("recovery", f"Seven-day HRV averaged {a:g} ms versus {b:g} ms "
                               "one week earlier.", "recovery"))
    run = next(iter(data.get("runs", [])), {})
    match = run.get("comparable_effort", {})
    if run.get("date") == data.get("end") and match.get("available"):
        delta = match["difference_hr_bpm"]
        if _number(delta):
            comparison = (f"{abs(delta):g} bpm {'higher' if delta > 0 else 'lower'} than"
                          if delta else "the same as")
            result.append(Evidence("running", f"The latest run's moving heart rate was "
                                   f"{comparison} the median across "
                                   f"{len(match['matches'])} similar runs.",
                                   f"run-{run['activity_id']}-compare"))
    return tuple(result) if len({row.domain for row in result}) >= 2 else ()


def sleep_review(data):
    """Use the fresh night as the eligibility gate and allow only sleep/recovery facts."""
    end = data.get("end")
    if not end or (data.get("night") or {}).get("day") != end:
        return ()
    rows = tuple(row for row in evidence(data) if row.domain in {"sleep", "recovery"})
    return rows if {row.domain for row in rows} == {"sleep", "recovery"} else ()


DEFAULT_VOICE = ("Be a curious, plainspoken coach. Lead with the most interesting contrast. "
                 "Name the uncertainty and ask a useful question in everyday language.")
LENSES = {
    "daily": "Look for readings that disagree. Separate a one-day wearable reading from the longer trend.",
    "sleep": "Compare the supplied sleep measurement with a named recovery measure such as HRV or resting pulse. "
             "Keep the time windows separate.",
    "running": "Compare the matched run with the surrounding recovery signals, while noting the different windows.",
    "running_review": "Look for a contrast between running frequency and a measured response on the latest run. "
                      "Describe pulse, pace or cadence as up, down or similar in the recording. "
                      "Ask what pattern is worth checking on the next comparable run.",
    "sunday_review": "Connect the week's training frequency and sleep in plain language. Training frequency "
                     "is a count of workouts. It does not measure training volume, load, or intensity. "
                     "The dashboard displays the next plan separately.",
}


def sunday_review(data):
    end = data.get("end")
    if (not end or date.fromisoformat(end).weekday() != 6
            or data.get("older_snapshot") or data.get("sync_retry_required")):
        return ()
    review = data.get("weekly_review")
    sleep_review = data.get("sleep_review", {})
    sleep = sleep_review.get("windows", {}).get(7, {})
    if not review or sleep.get("nights", 0) < 4:
        return ()
    count = review["week"]["sessions"]
    average = (review.get("previous_4wk_weekly_avg") or {}).get("sessions")
    training = f"Recorded workout count with load data was {count} this week"
    trend = window = None
    if _number(average):
        training += f" versus {average:g} per week on average over the previous four weeks"
        trend, window = clauses.trend_of(count - average), "blocks"
    workouts = clauses.Claim("workouts", r"\b(?:workouts?|sessions?|training frequency)\b", trend, window)
    sleep_text = f'Sleep averaged {sleep["hours"]:.1f} hours across {sleep["nights"]} nights'
    change = sleep_review.get("week_change_min")
    if change:
        direction = "more" if change > 0 else "less"
        sleep_text += f", {abs(change)} min {direction} per night than last week"
    elif change == 0:
        sleep_text += ", unchanged from last week"
    anchor = sleep_review.get("anchor") or {}
    if not (_number(average) or _number(change) or anchor):
        return ()
    slept = clauses.Claim("sleep", r"\bsle(?:ep|pt)", None if change is None else clauses.trend_of(change),
                          None if change is None else "week")
    rows = [Evidence("training", training + ".", "training", claim=workouts),
            Evidence("sleep", sleep_text + ".", "sleep", claim=slept)]
    if anchor:
        rows.append(Evidence("sleep", f'Wake times varied by {anchor["spread"]} min.', "sleep",
                             claim=clauses.Claim("wake", r"\bw[ao]k")))
    return tuple(rows)


def running_review(data):
    if data.get("available") is False or data.get("older_snapshot") or data.get("sync_retry_required"):
        return ()
    block = data.get("running_block", {})
    recent, previous = block.get("recent", {}), block.get("previous", {})
    rows = []
    if recent.get("runs") and previous.get("runs"):
        rows.append(Evidence("consistency", f'Recorded runs occupied {recent["days"]} day{"" if recent["days"] == 1 else "s"} in the last four '
                             f'completed weeks versus {previous["days"]} in the four before.', "running-block",
                             claim=clauses.Claim("runs", r"\b(?:runs?|ran|running)\b",
                                                 clauses.trend_of(recent["days"] - previous["days"]), "blocks")))
    if block.get("median_decoupling") is not None:
        rows.append(Evidence("endurance", f'Median second-half change in grade-adjusted speed per heartbeat '
                             f'was {block["median_decoupling"]:+g}% decoupling across '
                             f'{block["decoupling_count"]} steady outdoor recordings. Positive means a decline.',
                             "running-efforts"))
    run = next((run for run in data.get("runs", []) if run["activity_id"] == block.get("latest_detail_id")), {})
    match = run.get("comparable_effort", {})
    if match.get("available"):
        low, high = match["observed_hr_range_bpm"]
        pulse = match["this_run"]["avg_hr_bpm"]
        relation = "below" if pulse < low else "above" if pulse > high else "within"
        rows.append(Evidence("matched effort", f'Latest run moving heart rate was {pulse:g} bpm, {relation} '
                             f'the {low:g} to {high:g} bpm span of earlier comparable runs.',
                             f'run-{run["activity_id"]}-compare',
                             claim=clauses.Claim("pulse", r"\b(?:heart rate|pulse)\b",
                                                 {"below": "down", "above": "up", "within": "same"}[relation],
                                                 "runs")))
    if halves := run.get("pacing", {}).get("effort_halves"):
        a, b = halves
        pace_a, pace_b = a["pace_s_per_km"], b["pace_s_per_km"]
        change = "slower" if pace_b > pace_a else "faster" if pace_b < pace_a else "the same"
        rows.append(Evidence("pacing", f'The latest single run was {change} in the second moving half '
                             f'({pace_a:g} to {pace_b:g} seconds per kilometre). Pulse went from '
                             f'{a["hr"]:g} to {b["hr"]:g} bpm.',
                             f'run-{run["activity_id"]}-pacing',
                             claim=clauses.Claim("pace", r"\b(?:faster|slower|quicker|slowed|sped|speed\w*|pace)\b",
                                                 clauses.trend_of(b["hr"] - a["hr"]), "halves",
                                                 change if change != "the same" else "same")))
    if measured := run.get("late_form", {}).get("cadence_spm"):
        rows.append(Evidence("matched mechanics", f'At similar pace and grade within the latest run, cadence '
                             f'was {measured["early"]:g} steps per minute early versus {measured["late"]:g} late, '
                             f'with {measured["matched_s"]} matched seconds in each half.',
                             f'run-{run["activity_id"]}-form',
                             claim=clauses.Claim("cadence", r"\bcadence\b",
                                                 clauses.trend_of(measured["late"] - measured["early"]), "halves")))
    cadence = run.get("form", {}).get("cadence_spm", {})
    if span := cadence.get("matched_range"):
        measured = cadence["value"]
        if not span[0] <= measured <= span[1]:
            rows.append(Evidence("running form", f'Latest cadence was {measured:g} steps per minute '
                                 f'against an observed matched span of {span[0]:g} to {span[1]:g}.',
                                 f'run-{run["activity_id"]}-form',
                                 claim=clauses.Claim("cadence", r"\bcadence\b",
                                                     "up" if measured > span[1] else "down", "runs")))
    return tuple(rows) if len(rows) >= 2 else ()


@dataclass(frozen=True)
class RunCheck:
    reading: Evidence
    measurements: dict
    alternative: str
    question: str
    priority: int


@dataclass(frozen=True)
class PostRunInsight:
    checks: tuple[RunCheck, ...]
    lens = "post_run"
    system = (
        "Choose the follow-up after this run. Return only the numeric check ID. "
        "First choose a cadence cue if a recorded earlier_attempt and this_run are both supplied. "
        "Without that cue, choose moving pulse when its relation is above or below, even if cadence changed. "
        "When pulse is within range or absent, prefer changed late cadence at matched pace and grade. "
        "When all options are stable, choose moving pulse if available. Do not infer causes."
    )

    @property
    def rows(self):
        return tuple(check.reading for check in self.checks)

    @property
    def prompt(self):
        return json.dumps([{"check": i, "metric": row.reading.domain, **row.measurements}
                           for i, row in enumerate(self.checks, 1)], separators=(",", ":"))

    @property
    def schema(self):
        return {"type": "object", "required": ["check"], "additionalProperties": False,
                "properties": {"check": {"type": "integer", "enum": list(range(1, len(self.checks) + 1))}}}

    def assess(self, raw):
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return None, "invalid_selection"
        if not isinstance(data, dict) or data.keys() != {"check"}:
            return None, "invalid_selection"
        choice = data["check"]
        if type(choice) is not int or not 1 <= choice <= len(self.checks):
            return None, "invalid_selection"
        if self.checks[choice - 1].priority < 2 <= max(check.priority for check in self.checks):
            return None, "low_signal_choice"
        return self.result(choice, "selected_post_run"), "grounded_selection"

    def result(self, choice, mode):
        check = self.checks[choice - 1]
        return {"observation": check.reading.text, "alternative": check.alternative,
                "question": check.question, "evidence": [choice],
                "mode": mode, "topic": check.reading.domain}


def _cadence_cue_check(data, run):
    trial = data.get("trial") or {}
    if not trial.get("active") or not run.get("date"):
        return None
    target = trial.get("trial", {}).get("target", {}).get("cadence_spm")
    if not _number(target):
        return None
    attempts = trial.get("attempts") or ()
    current = next((attempt for attempt in attempts if attempt.get("activity_id") == run["activity_id"]), {})
    before = max((attempt for attempt in reversed(attempts) if attempt.get("date") and attempt["date"] < run["date"]),
                 key=lambda attempt: attempt["date"], default={})
    result = []
    for attempt in (current, before):
        exposure = attempt.get("did_it") or {}
        near, total = exposure.get("minutes_at_target"), exposure.get("moving_minutes")
        if not (exposure.get("available") and _number(near) and _number(total) and 0 <= near <= total and total > 0):
            return None
        result.append((near, total))
    (now, now_total), (earlier, earlier_total) = result
    threshold = target - 2  # Match trials.minutes_at_cadence's recorded exposure rule.
    reading = Evidence("cadence cue", f"With the {target:g} steps/min cue, cadence reached "
                       f"{threshold:g} steps/min or more for {now:g} of {now_total:g} recorded cadence "
                       f"minutes on this run and {earlier:g} of {earlier_total:g} on the earlier attempt.",
                       f'run-{run["activity_id"]}')
    return RunCheck(reading, {"target_steps_per_min": target, "at_least_steps_per_min": threshold,
                             "minutes_above_and_recorded": {"this_run": result[0], "earlier_attempt": result[1]}},
                    "Route and effort can differ between attempts. The recorded minutes describe time at that cadence.",
                    "On a similar route at matching pace and grade, does time near the cue repeat and how does it feel?",
                    4)


def post_run_review(data):
    """Build up to three compact, qualified checks for the newest detailed run."""
    if data.get("available") is False or data.get("older_snapshot") or data.get("sync_retry_required"):
        return None
    run = next(iter(data.get("runs", ())), None)
    if not run:
        return None
    aid = run["activity_id"]
    checks = []
    cadence = (run.get("late_form") or {}).get("cadence_spm") or {}
    early, late, matched = (cadence.get(key) for key in ("early", "late", "matched_s"))
    if all(_number(value) and value > 0 for value in (early, late, matched)):
        reading = Evidence("late cadence", f"At similar pace and grade, cadence averaged {early:g} steps/min "
                           f"early and {late:g} late across {matched:g} matched seconds in each half.",
                           f"run-{aid}-form")
        changed = abs(late - early) >= 3
        checks.append(RunCheck(reading, {"steps_per_min": {"early": early, "late": late},
                                        "matched_seconds_per_half": matched, "match": "pace and grade",
                                        "changed": changed},
                               "Surface and wind can still differ between the matched sections.",
                               "Does the early-to-late cadence difference repeat at matching pace and grade?",
                               2 if changed else 0))
    match = run.get("comparable_effort") or {}
    if match.get("available"):
        low, high = match["observed_hr_range_bpm"]
        current = match["this_run"]["avg_hr_bpm"]
        count = len(match["matches"])
        if count and all(_number(value) for value in (low, high, current)):
            relation = "below" if current < low else "above" if current > high else "within"
            reading = Evidence("moving pulse", f"Moving heart rate was {current:g} bpm, {relation} the "
                               f"{low:g} to {high:g} bpm span of {count} earlier runs at similar pace, "
                               f"duration and climbing per kilometre.", f"run-{aid}-compare")
            checks.append(RunCheck(reading, {"moving_bpm": current, "earlier_span_bpm": [low, high],
                                            "earlier_runs": count, "relation": relation,
                                            "match": "pace, duration and climbing per kilometre"},
                                   "Weather or wrist-sensor fit could affect the recorded pulse.",
                                   f"On another comparable run, does moving pulse land {relation} "
                                   "your earlier range again?", 3 if relation != "within" else 1))
    if cue := _cadence_cue_check(data, run):
        checks.append(cue)
    return PostRunInsight(tuple(checks)) if checks else None


def post_run_fallback(data):
    item = post_run_review(data)
    if not item:
        return None
    choice, check = max(enumerate(item.checks, 1), key=lambda entry: entry[1].priority)
    return {**item.result(choice, "rule_post_run"),
            "readings": [{"page": check.reading.page, "text": check.reading.text, "previous": False}]}


def _fictional_post_run(pulse, late, *, cue=False):
    day = "2026-11-25"
    data = {"end": day, "runs": [{"activity_id": 101, "date": day}]}
    run = data["runs"][0]
    if pulse is not None:
        run["comparable_effort"] = {"available": True, "observed_hr_range_bpm": [137, 145],
                                    "difference_hr_bpm": pulse - 141,
                                    "this_run": {"avg_hr_bpm": pulse}, "matches": [{}, {}, {}]}
    if late is not None:
        run["late_form"] = {"cadence_spm": {"early": 172, "late": late, "matched_s": 420}}
    if cue:
        data["trial"] = {"active": True, "trial": {"target": {"cadence_spm": 174}},
                         "attempts": [{"activity_id": 83, "date": "2026-11-22",
                                       "did_it": {"available": True, "minutes_at_target": 5, "moving_minutes": 25}},
                                      {"activity_id": 101, "date": day,
                                       "did_it": {"available": True, "minutes_at_target": 8, "moving_minutes": 27}}]}
    return data


FICTIONAL_POST_RUN_CASES = {
    "post-run-cue": (_fictional_post_run(152, 166, cue=True), "cadence cue"),
    "post-run-outlier": (_fictional_post_run(152, 169), "moving pulse"),
    "post-run-form": (_fictional_post_run(141, 165), "late cadence"),
    "post-run-thin": (_fictional_post_run(None, None), None),
}


def _style_path(conn):
    database = conn.execute("PRAGMA database_list").fetchone()[2]
    return (Path(database).parent if database else data_dir()) / "narrator-prompt.json"


def writing_style(conn, lens):
    """Read optional style text. Return the built-in profile on malformed input."""
    source = _style_path(conn)
    profile = {}
    status = "built-in"
    try:
        with source.open("rb") as f:
            raw = f.read(8193)
        value = json.loads(raw) if len(raw) <= 8192 else None
        if not isinstance(value, dict) or value.keys() - {"voice", "lenses"}:
            raise ValueError
        custom = value.get("lenses", {})
        if not isinstance(custom, dict) or custom.keys() - LENSES.keys():
            raise ValueError
        parts = [*custom.values(), value.get("voice", DEFAULT_VOICE)]
        if not all(isinstance(v, str) and 0 < len(v.strip()) <= 800
                   and not any(unicodedata.category(c).startswith("C") for c in v) for v in parts):
            raise ValueError
        profile = value
        status = "custom"
    except FileNotFoundError:
        pass
    except (OSError, ValueError):
        status = "invalid; built-in used"
    lenses = profile.get("lenses", {})
    focus = lenses.get("daily", LENSES["daily"])
    if lens != "daily":
        focus = f"{focus} {lenses.get(lens, LENSES[lens])}"
    return profile.get("voice", DEFAULT_VOICE), focus, status


def remembered(conn, end):
    if not end:
        return ()
    first = (date.fromisoformat(end) - timedelta(days=14)).isoformat()
    stored = conn.execute("SELECT evidence FROM coach_insight_memory WHERE day>=? AND day<? "
                          "ORDER BY day DESC LIMIT 1", (first, end)).fetchone()
    if stored is None:
        return ()
    return tuple(Evidence(row["domain"], "Earlier reviewed snapshot: " + row["text"],
                          row["page"], previous=True) for row in json.loads(stored[0]))


def remember(conn, day, rows):
    if not day:
        return
    retained = [{"domain": row.domain, "text": row.text, "page": row.page}
                for row in rows if not row.previous and row.page in {"sleep", "recovery"}][:2]
    if not retained:
        return
    conn.execute("INSERT OR IGNORE INTO coach_insight_memory VALUES (?,?)", (day, json.dumps(retained)))
    first = (date.fromisoformat(day) - timedelta(days=14)).isoformat()
    conn.execute("DELETE FROM coach_insight_memory WHERE day<?", (first,))


FICTIONAL_CASES = {
    "today-written": (
        "running", evidence({
            "end": "2026-11-25",
            "signals": {"resting_hr": {"recent": 53, "previous": 53, "recent_count": 7, "previous_count": 7}},
            "runs": [{"activity_id": 101, "date": "2026-11-25", "comparable_effort": {
                "available": True, "difference_hr_bpm": 7, "matches": [{}, {}, {}, {}]},
            }],
        }),
    ),
    "sleep-written": (
        "sleep", sleep_review({
            "end": "2026-11-25", "night": {"day": "2026-11-25"},
            "signals": {"sleep_h": {"recent": 7.8, "previous": 6.6, "recent_count": 6, "previous_count": 7}},
            "hrv_context": {"rolling_7d_ms": 45, "previous_average": 48},
        }),
    ),
    "dated-health": (
        "sleep", evidence({
            "end": "2026-11-25",
            "sleep_shortfall": {"per_night_min": 42, "previous_min": 60,
                                "current": {"valid_nights_7d": 6},
                                "previous": {"valid_nights_7d": 7}},
            "calendar": {"days": {"2026-11-25": {"resting_pulse_check": {
                "verify": True, "value": 44, "median": 53, "count": 16, "direction": "lower",
                "coverage": {"90 days": {"typical": (54, 50, 58), "count": 72}},
            }}}},
        }),
    ),
    "sunday-review": (
        "sunday_review", sunday_review({
            "end": "2026-11-22",
            "weekly_review": {"week": {"sessions": 3}, "previous_4wk_weekly_avg": {"sessions": 2}},
            "sleep_review": {"windows": {7: {"nights": 5, "hours": 7.2}}, "week_change_min": -21},
        }),
    ),
    "running-block": (
        "running_review", running_review({
            "running_block": {"recent": {"runs": 8, "days": 8}, "previous": {"runs": 5, "days": 5},
                              "latest_detail_id": 1},
            "runs": [{"activity_id": 1,
                      "comparable_effort": {"available": True, "observed_hr_range_bpm": (138, 145),
                                            "this_run": {"avg_hr_bpm": 142}},
                      "pacing": {"effort_halves": ({"pace_s_per_km": 320, "hr": 140},
                                                   {"pace_s_per_km": 331, "hr": 144})},
                      "late_form": {"cadence_spm": {"early": 170, "late": 167, "matched_s": 410}}}],
        }),
    ),
    "mixed-recovery": (
        "sleep", (
            Evidence("sleep", "Sleep averaged 6.2 h versus 7.1 h.", "sleep"),
            Evidence("recovery", "Resting pulse rose from 55 to 59 bpm.", "recovery"),
            Evidence("recovery", "Seven-day HRV held at 51 ms.", "recovery"),
        ),
    ),
    "run-exception": (
        "running", (
            Evidence("running", "Moving pulse was 7 bpm higher than across 4 matched runs.", "running"),
            Evidence("recovery", "Resting pulse averaged 53 bpm in both weeks.", "recovery"),
            Evidence("sleep", "Sleep averaged 7.2 h versus 7.1 h.", "sleep"),
        ),
    ),
    "longer-sleep": (
        "sleep", (
            Evidence("sleep", "Sleep averaged 7.8 h versus 6.6 h.", "sleep"),
            Evidence("recovery", "Resting pulse averaged 56 bpm in both weeks.", "recovery"),
            Evidence("recovery", "Seven-day HRV fell from 48 to 45 ms.", "recovery"),
        ),
    ),
}


SYSTEM = (
    "Review the athlete's log. Briefly choose the strongest comparison between two current signals. "
    "Return a short observation about what stands out, a neutral question that could check whether it "
    "repeats, and an evidence array of 2 or 3 IDs that cover every claim. Prefer ordinary language "
    "without numbers. When a number matters, copy its value, metric and time window together. "
    "Keep counts, duration, load and intensity distinct. Treat a single workout as one example. "
    "For the question, ask whether the measured pattern repeats in the next comparable record. "
    "Earlier rows are context only and can overlap current windows. Stay with what was measured. "
    "Avoid causes, diagnoses, how the athlete felt, calculated ratios, advice and forecasts. "
    "Use at least two current domains. If nothing useful stands out, return empty strings and an empty list."
)
CONCISE_SYSTEM = (
    "Write one short observation using two different current evidence domains. "
    "Use the measured names, such as moving heart rate or HRV, rather than a broad fitness or recovery label. "
    "Give the direction and comparison window for each measurement. "
    "Use plain language and omit numbers unless useful. Avoid causes, advice and forecasts. "
    "Return only the observation and the two cited evidence IDs."
)
PARTS_SYSTEM = (
    "Write two short clauses about two readings from different domains, one reading per clause. "
    "Build each clause from its reading's own fields, in this order: measure, was, direction, period, "
    "ending. Copy ending whole. The direction belongs to period, never to the ending. Never borrow the "
    "other reading's fields. When a reading has no direction, state only what was measured. Use plain "
    "everyday words, under twenty words per clause, with no figures or amounts. No causes, advice, "
    "questions or forecasts. Do not start with while, and or but. Return each clause with its evidence ID. The program joins them and adds the question."
)
REVIEW_REASONS = ("supported", "wrong_comparison", "unsupported_claim", "advice_or_prediction")
REVIEW = (
    "Compare each factual statement in the proposed observation and any premise in its question "
    "with the cited readings. Choose one verdict. Use supported for an accurate observation and "
    "a neutral question about checking or repeating measured signals. Allow everyday paraphrases. "
    "Use wrong_comparison if a direction, metric, value or time window changed. Use unsupported_claim "
    "for a new fact, feeling, cause, ratio or broad recovery claim inferred from one reading. "
    "Use advice_or_prediction for a target, prescription, "
    "diagnosis or forecast. Check questions too. 'Did shorter sleep make you feel tired?' invents "
    "a cause and a feeling. 'Does sleep stay shorter in another week with more recorded workouts?' checks a repeat."
)
SELECT_COMPARISON = (
    "Choose the numbered comparison that is most useful to check again. Favor meaningful measured "
    "differences or a measured change alongside a steady reading. The program will display both "
    "source readings and their time windows exactly as given. Return only the comparison ID."
)
_EXCLUDED = re.compile(
    r"[<>#`*\[\]{}]|\b(?:because|caused?|due to|leads? to|will|guarantee\w*|must|should|"
    r"correlat\w*|prescri\w*|diagnos\w*|diseases?|medicat\w*|symptoms?|treat\w*|injur\w*)\b", re.IGNORECASE)
_UNMEASURED = re.compile(r"\b(?:feel(?:s|ing)?|felt|tired(?:ness)?|fatigu\w*|"
                         r"reason\s+(?:for|why|you)|explain(?:s|ed)?\s+why|"
                         r"recovery\s+(?:metrics?|markers?|status|scores?|improved|worsened)|"
                         r"fitness\s+(?:improved|worsened)|"
                         r"twice|doubl(?:e[ds]?|ing)|tripl(?:e[ds]?|ing)|halv(?:e[ds]?|ing))\b", re.IGNORECASE)


def _plain(value, min_words, max_words):
    if not isinstance(value, str) or len(value) > 500:
        return None
    text = unicodedata.normalize("NFKC", value).strip()
    if (not min_words <= len(text.split()) <= max_words or _EXCLUDED.search(text)
            or any(unicodedata.category(char).startswith("C") for char in text)):
        return None
    return text


@dataclass(frozen=True)
class Insight:
    rows: tuple[Evidence, ...]
    lens: str = "daily"
    voice: str = DEFAULT_VOICE
    focus: str = LENSES["daily"]

    @property
    def system(self):
        return f"{SYSTEM} Voice: {self.voice} Focus: {self.focus}"

    @property
    def checkable(self):
        """IDs of current readings that a single clause can be verified against."""
        return tuple(i for i, row in enumerate(self.rows, 1) if row.claim and not row.previous)

    @property
    def by_parts(self):
        return len({self.rows[i - 1].domain for i in self.checkable}) >= 2

    @property
    def concise_system(self):
        voice = f" Voice: {self.voice}" if self.voice != DEFAULT_VOICE else ""
        if self.by_parts:
            # The built-in running lens asks for a question, which this schema has no place for.
            focus = self.focus.replace(" Ask what pattern is worth checking on the next comparable run.", "")
            return f"{PARTS_SYSTEM}{voice} Focus: {focus}"
        return f"{CONCISE_SYSTEM}{voice} Focus: {self.focus}"

    @property
    def concise_prompt(self):
        if not self.by_parts:
            return self.prompt
        return json.dumps([{"id": i, "domain": self.rows[i - 1].domain, "reading": self.rows[i - 1].text,
                            **clauses.guide(self.rows[i - 1].claim)} for i in self.checkable],
                          ensure_ascii=False, separators=(",", ":"))

    @property
    def prompt(self):
        return json.dumps(self.prompt_readings(), ensure_ascii=False, separators=(",", ":"))

    def prompt_readings(self, *, include_previous=True):
        return [{"id": i, "domain": row.domain, "reading": row.text,
                 **({"earlier_context": True} if row.previous else {})}
                for i, row in enumerate(self.rows, 1) if include_previous or not row.previous]

    @property
    def schema(self):
        return {"type": "object", "additionalProperties": False,
                "required": ["observation", "question", "evidence"], "properties": {
                    "observation": {"type": "string"}, "question": {"type": "string"},
                    "evidence": {"type": "array", "maxItems": 3, "items": {
                        "type": "integer", "enum": list(range(1, len(self.rows) + 1))}}}}

    @property
    def concise_schema(self):
        if self.by_parts:
            part = {"type": "object", "additionalProperties": False, "required": ["evidence", "text"],
                    "properties": {"evidence": {"type": "integer", "enum": list(self.checkable)},
                                   "text": {"type": "string"}}}
            return {"type": "object", "additionalProperties": False, "required": ["parts"],
                    "properties": {"parts": {"type": "array", "minItems": 2, "maxItems": 2, "items": part}}}
        schema = self.schema
        schema["required"].remove("question")
        del schema["properties"]["question"]
        schema["properties"]["evidence"].update(minItems=2, maxItems=2)
        return schema

    def response(self, raw):
        return self.assess(raw)[0]

    def comparison_options(self):
        """Offer only pairs of current, distinct evidence categories."""
        return tuple((i, j) for i, j in combinations(range(1, len(self.rows) + 1), 2)
                     if not self.rows[i - 1].previous and not self.rows[j - 1].previous
                     and self.rows[i - 1].domain != self.rows[j - 1].domain)

    def selected_comparison(self, raw, options):
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return None
        if not isinstance(data, dict) or data.keys() != {"comparison"}:
            return None
        choice = data["comparison"]
        if type(choice) is not int or not 1 <= choice <= len(options):
            return None
        ids = list(options[choice - 1])
        return {"observation": " ".join(self.rows[i - 1].text for i in ids),
                "question": self._repeat_question(ids), "evidence": ids,
                "mode": "selected_comparison"}

    def _repeat_question(self, ids):
        domains = {self.rows[i - 1].domain for i in ids if not self.rows[i - 1].previous}
        if self.lens == "sunday_review":
            return "Do this week's workout count and sleep pattern recur next week?"
        if self.lens == "running_review":
            for domain, question in (
                ("matched mechanics", "Does cadence change similarly on another run at comparable pace and grade?"),
                ("pacing", "Do pace and pulse follow the same pattern on your next comparable run?"),
                ("matched effort", ("Where does moving pulse fall against your earlier range on another run at "
                                    "a similar pace?")),
                ("running form", "Does a run at a similar pace show the same cadence pattern?"),
            ):
                if domain in domains:
                    return question
            return "Does the same pattern recur in the next comparable training block?"
        if {"sleep", "recovery"} <= domains:
            return "Do sleep and recovery readings show the same pattern in the next comparable period?"
        if "running" in domains:
            return "Do another matched run and its surrounding readings show the same pattern?"
        return "Does this pattern repeat in the next comparable set of readings?"

    def assess(self, raw, *, repair_question=False, concise=False):
        if isinstance(raw, str):
            fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw.strip(), re.DOTALL)
            if fenced:
                raw = fenced[1]
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return None, "invalid_response"
        if concise and self.by_parts:
            return self._assess_parts(data)
        keys = {"observation", "evidence"} if concise else {"observation", "question", "evidence"}
        if not isinstance(data, dict) or data.keys() != keys:
            return None, "invalid_response"
        empty = {"observation": "", "evidence": [], **({"question": ""} if not concise else {})}
        if data == empty:
            return None, "abstained"
        ids = data["evidence"]
        if (not isinstance(ids, list) or not 2 <= len(ids) <= (2 if concise else 3)
                or not all(type(i) is int and 1 <= i <= len(self.rows) for i in ids)
                or len(set(ids)) != len(ids)
                or len({self.rows[i - 1].domain for i in ids if not self.rows[i - 1].previous}) < 2):
            return None, "missing_citations"
        observation = _plain(data["observation"], 9, 55)
        if not observation:
            return None, "unsupported_wording"
        # Every reading compares at most two periods, which cannot show a trend.
        if _UNMEASURED.search(observation) or re.search(r"\btrend\w*\b", observation, re.IGNORECASE):
            return None, "unsupported_claim"
        pattern = r"[+−-]?\d+(?:[.:/]\d+)*"
        allowed = {n for i in ids for n in re.findall(pattern, self.rows[i - 1].text)}
        if (not set(re.findall(pattern, observation)) <= allowed
                or clauses.loose_amount(observation, " ".join(self.rows[i - 1].text for i in ids))):
            return None, "uncited_number"
        if concise:
            return {"observation": observation, "question": self._repeat_question(ids),
                    "evidence": ids}, "valid"
        question = _plain(data["question"], 5, 24)
        if (not question or question.count("?") != 1 or not question.endswith("?")
                or _UNMEASURED.search(question) or re.search(pattern, question)):
            if not repair_question:
                return None, "unsupported_question"
            return {"observation": observation, "question": self._repeat_question(ids),
                    "evidence": ids}, "question_reframed"
        return {"observation": observation, "question": question, "evidence": ids}, "valid"

    def _assess_parts(self, data):
        """Check each clause against its own reading, then join the two."""
        parts = data.get("parts") if isinstance(data, dict) and data.keys() == {"parts"} else None
        if (not isinstance(parts, list) or len(parts) != 2
                or not all(isinstance(part, dict) and part.keys() == {"evidence", "text"} for part in parts)):
            return None, "invalid_response"
        ids = [part["evidence"] for part in parts]
        if (not all(type(i) is int and i in self.checkable for i in ids)
                or len({self.rows[i - 1].domain for i in ids}) < 2):
            return None, "missing_citations"
        written = []
        for number, part in zip(ids, parts, strict=True):
            text = _plain(part["text"], 4, 24)
            text = re.sub(r"^(?:while|and|but|meanwhile|whereas),?\s+", "", text or "", flags=re.IGNORECASE)
            text = text.rstrip(" .,;")
            if not text or re.search(r"[?!;]|\.(?!\d)", text):
                return None, "unsupported_wording"
            if _UNMEASURED.search(text):
                return None, "unsupported_claim"
            row = self.rows[number - 1]
            pattern = r"\d+(?:[.:/]\d+)*"
            if (not set(re.findall(pattern, text)) <= set(re.findall(pattern, row.text))
                    or clauses.uncited_quantity(text, row.text)):
                return None, "uncited_number"
            if reason := clauses.check(text, row.claim):
                return None, reason
            written.append(text)
        first, second = written
        second = second[0].lower() + second[1:] if second[1:2].islower() or second[1:2] == " " else second
        observation = _plain(f"{first[0].upper()}{first[1:]}, while {second}.", 9, 55)
        if not observation:
            return None, "unsupported_wording"
        return {"observation": observation, "question": self._repeat_question(ids), "evidence": ids}, "valid"
