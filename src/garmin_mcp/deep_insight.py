"""Allowlisted evidence and validation for a model-authored interpretation."""

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from garmin_mcp.config import data_dir

INSIGHT_CONTRACT = 2


@dataclass(frozen=True)
class Evidence:
    domain: str
    text: str
    page: str
    previous: bool = False


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
            result.append(Evidence("running", f"The latest run's moving heart rate differed by "
                                   f"{delta:+g} bpm from the median across "
                                   f"{len(match['matches'])} similar runs.",
                                   f"run-{run['activity_id']}-compare"))
    return tuple(result) if len({row.domain for row in result}) >= 2 else ()


DEFAULT_VOICE = ("Be a curious, plainspoken coach. Lead with the most interesting contrast. "
                 "Name the uncertainty and ask a useful question in everyday language.")
LENSES = {
    "daily": "Look for readings that disagree, and distinguish an exception from a trend.",
    "sleep": "Pay attention to the relationship between sleep and recovery readings.",
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
    if _number(average):
        training += f" versus {average:g} per week on average over the previous four weeks"
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
    rows = [Evidence("training", training + ".", "training"), Evidence("sleep", sleep_text + ".", "sleep")]
    if anchor:
        rows.append(Evidence("sleep", f'Wake times varied by {anchor["spread"]} min.', "sleep"))
    return tuple(rows)


def running_review(data):
    if data.get("available") is False or data.get("older_snapshot") or data.get("sync_retry_required"):
        return ()
    block = data.get("running_block", {})
    recent, previous = block.get("recent", {}), block.get("previous", {})
    rows = []
    if recent.get("runs") and previous.get("runs"):
        rows.append(Evidence("consistency", f'Recorded runs occupied {recent["days"]} days in the last four '
                             f'completed weeks versus {previous["days"]} in the four before.', "running-block"))
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
                             f'run-{run["activity_id"]}-compare'))
    if halves := run.get("pacing", {}).get("effort_halves"):
        a, b = halves
        pace_a, pace_b = a["pace_s_per_km"], b["pace_s_per_km"]
        change = "slower" if pace_b > pace_a else "faster" if pace_b < pace_a else "the same"
        rows.append(Evidence("pacing", f'The latest single run was {change} in the second moving half '
                             f'({pace_a:g} to {pace_b:g} seconds per kilometre). Pulse went from '
                             f'{a["hr"]:g} to {b["hr"]:g} bpm.',
                             f'run-{run["activity_id"]}-pacing'))
    if measured := run.get("late_form", {}).get("cadence_spm"):
        rows.append(Evidence("matched mechanics", f'At similar pace and grade within the latest run, cadence '
                             f'was {measured["early"]:g} steps per minute early versus {measured["late"]:g} late, '
                             f'with {measured["matched_s"]} matched seconds in each half.',
                             f'run-{run["activity_id"]}-form'))
    cadence = run.get("form", {}).get("cadence_spm", {})
    if span := cadence.get("matched_range"):
        measured = cadence["value"]
        if not span[0] <= measured <= span[1]:
            rows.append(Evidence("running form", f'Latest cadence was {measured:g} steps per minute '
                                 f'against an observed matched span of {span[0]:g} to {span[1]:g}.',
                                 f'run-{run["activity_id"]}-form'))
    return tuple(rows) if len(rows) >= 2 else ()


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
    "sunday-review": (
        "sunday_review", (
            Evidence("training", "Recorded workout count with load data was 3 this week versus 2 per week "
                     "on average over the previous four weeks.", "training"),
            Evidence("sleep", "Sleep averaged 7.2 hours across 5 nights, 21 min less per night than last week.",
                     "sleep"),
        ),
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


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


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
REVIEW_REASONS = ("supported", "wrong_comparison", "unsupported_claim", "advice_or_prediction")
REVIEW = (
    "Compare each factual statement in the proposed observation and any premise in its question "
    "with the cited readings. Choose one verdict. Use supported for an accurate observation and "
    "a neutral question about checking or repeating measured signals. Allow everyday paraphrases. "
    "Use wrong_comparison if a direction, metric, value or time window changed. Use unsupported_claim "
    "for a new fact, feeling, cause or ratio. Use advice_or_prediction for a target, prescription, "
    "diagnosis or forecast. Check questions too. 'Did shorter sleep make you feel tired?' invents "
    "a cause and a feeling. 'Does sleep stay shorter in another week with more recorded workouts?' checks a repeat."
)
_EXCLUDED = re.compile(
    r"[<>#`*\[\]{}]|\b(?:because|caused?|due to|leads? to|will|guarantee\w*|must|should|"
    r"correlat\w*|prescri\w*|diagnos\w*|diseases?|medicat\w*|symptoms?|treat\w*|injur\w*)\b", re.IGNORECASE)
_UNMEASURED = re.compile(r"\b(?:feel(?:s|ing)?|felt|tired(?:ness)?|fatigu\w*|"
                         r"reason\s+(?:for|why|you)|explain(?:s|ed)?\s+why|"
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
    def prompt(self):
        return json.dumps([{"id": i, "domain": r.domain, "reading": r.text,
                            **({"earlier_context": True} if r.previous else {})}
                           for i, r in enumerate(self.rows, 1)], ensure_ascii=False, separators=(",", ":"))

    @property
    def schema(self):
        return {"type": "object", "additionalProperties": False,
                "required": ["observation", "question", "evidence"], "properties": {
                    "observation": {"type": "string"}, "question": {"type": "string"},
                    "evidence": {"type": "array", "maxItems": 3, "items": {
                        "type": "integer", "enum": list(range(1, len(self.rows) + 1))}}}}

    def response(self, raw):
        return self.assess(raw)[0]

    def _repeat_question(self, ids):
        domains = {self.rows[i - 1].domain for i in ids if not self.rows[i - 1].previous}
        if self.lens == "sunday_review":
            return "Do this week's workout count and sleep pattern recur next week?"
        if self.lens == "running_review":
            for domain, question in (
                ("matched mechanics", "Does cadence change similarly on another run at comparable pace and grade?"),
                ("pacing", "Do pace and pulse follow the same pattern on your next comparable run?"),
                ("matched effort", "Does moving pulse stay in the same range on another run at a similar pace?"),
                ("running form", "Does a run at a similar pace show the same cadence pattern?"),
            ):
                if domain in domains:
                    return question
            return "Does the same pattern recur in the next comparable training block?"
        return "Does this pattern repeat in the next comparable set of readings?"

    def assess(self, raw, *, repair_question=False):
        if isinstance(raw, str):
            fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw.strip(), re.DOTALL)
            if fenced:
                raw = fenced[1]
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return None, "invalid_response"
        if not isinstance(data, dict) or data.keys() != {"observation", "question", "evidence"}:
            return None, "invalid_response"
        if data == {"observation": "", "question": "", "evidence": []}:
            return None, "abstained"
        ids = data["evidence"]
        if (not isinstance(ids, list) or not 2 <= len(ids) <= 3
                or not all(type(i) is int and 1 <= i <= len(self.rows) for i in ids)
                or len(set(ids)) != len(ids)
                or len({self.rows[i - 1].domain for i in ids if not self.rows[i - 1].previous}) < 2):
            return None, "missing_citations"
        observation = _plain(data["observation"], 9, 55)
        if not observation:
            return None, "unsupported_wording"
        if _UNMEASURED.search(observation):
            return None, "unsupported_claim"
        pattern = r"[+−-]?\d+(?:[.:/]\d+)*"
        allowed = {n for i in ids for n in re.findall(pattern, self.rows[i - 1].text)}
        if not set(re.findall(pattern, observation)) <= allowed:
            return None, "uncited_number"
        question = _plain(data["question"], 5, 24)
        if (not question or question.count("?") != 1 or not question.endswith("?")
                or _UNMEASURED.search(question) or re.search(pattern, question)):
            if not repair_question:
                return None, "unsupported_question"
            return {"observation": observation, "question": self._repeat_question(ids),
                    "evidence": ids}, "question_reframed"
        return {"observation": observation, "question": question, "evidence": ids}, "valid"
