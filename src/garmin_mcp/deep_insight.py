"""Allowlisted evidence and validation for a model-authored interpretation."""

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from garmin_mcp.config import data_dir


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
    "running_review": "Think like a distance-running coach reviewing a training log. Look for a contrast "
                      "between repeatability and a single workout, then propose a measurement that would settle it.",
}


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
        rows.append(Evidence("matched effort", f'Latest detailed run had moving heart rate '
                             f'{match["this_run"]["avg_hr_bpm"]:g} bpm versus an earlier span of '
                             f'{low:g} to {high:g} bpm.', f'run-{run["activity_id"]}-compare'))
    if halves := run.get("pacing", {}).get("effort_halves"):
        a, b = halves
        rows.append(Evidence("pacing", f'Latest detailed run averaged {a["pace_s_per_km"]} and '
                             f'{b["pace_s_per_km"]} seconds per kilometre, with pulse {a["hr"]:g} and '
                             f'{b["hr"]:g} bpm, in the first and second moving halves.',
                             f'run-{run["activity_id"]}-pacing'))
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
    "running-block": (
        "running_review", (
            Evidence("consistency", "Running days increased from 5 to 8 across completed four-week blocks.",
                     "running-block"),
            Evidence("matched effort", "The latest run's moving heart rate was inside its earlier matched span.",
                     "running-efforts"),
            Evidence("pacing", "Pace slowed and pulse rose in the second half of the latest run.", "running-efforts"),
        ),
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
    "Write one original coaching observation about the readings. Look for an exception or a "
    "contrast across signals. Separate single efforts from multi-day averages. Describe what the "
    "measurements show without inferring how the athlete felt, what caused the difference, "
    "or what will happen next. Cite the IDs you used across at least two domains. Use numbers "
    "only when they help, copied exactly from cited readings. Ask one neutral question about "
    "whether the same signals repeat when measured again. Keep the question free of targets, "
    "new quantities, and advice. "
    "Output JSON with observation and question strings and an evidence array of IDs. "
    "Earlier reviewed snapshots are context only and may overlap current windows. Treat them "
    "as earlier context, not new independent observations. Cite at least two current domains. "
    "If nothing useful stands out, return empty strings and an empty list."
)
REVIEW = (
    "Check the observation and question against the cited readings. Accept a supported contrast "
    "and an observational question, even if you would phrase them differently. Reject a concrete "
    "unsupported measurement or comparison, contradiction, causal claim, diagnosis, prescription "
    "or prediction. A question about whether a pattern repeats is not a claim that it will. "
    "Return only JSON with a boolean publish field."
)
_EXCLUDED = re.compile(
    r"[<>#`*\[\]{}]|\b(?:because|caused?|due to|leads? to|will|guarantee\w*|must|should|"
    r"correlat\w*|prescri\w*|diagnos\w*|diseases?|medicat\w*|symptoms?|treat\w*|injur\w*)\b", re.IGNORECASE)


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
        return json.dumps([{"id": i, "domain": r.domain, "reading": r.text}
                           for i, r in enumerate(self.rows, 1)], ensure_ascii=False)

    @property
    def schema(self):
        return {"type": "object", "additionalProperties": False,
                "required": ["observation", "question", "evidence"], "properties": {
                    "observation": {"type": "string"}, "question": {"type": "string"},
                    "evidence": {"type": "array", "maxItems": 3, "items": {
                        "type": "integer", "enum": list(range(1, len(self.rows) + 1))}}}}

    def response(self, raw):
        if isinstance(raw, str):
            fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw.strip(), re.DOTALL)
            if fenced:
                raw = fenced[1]
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return None
        if not isinstance(data, dict) or data.keys() != {"observation", "question", "evidence"}:
            return None
        ids = data["evidence"]
        if (not isinstance(ids, list) or not 2 <= len(ids) <= 3
                or not all(type(i) is int and 1 <= i <= len(self.rows) for i in ids)
                or len(set(ids)) != len(ids)
                or len({self.rows[i - 1].domain for i in ids if not self.rows[i - 1].previous}) < 2):
            return None
        observation = _plain(data["observation"], 9, 55)
        question = _plain(data["question"], 5, 24)
        if not observation or not question or question.count("?") != 1 or not question.endswith("?"):
            return None
        pattern = r"[+−-]?\d+(?:[.:/]\d+)*"
        allowed = {n for i in ids for n in re.findall(pattern, self.rows[i - 1].text)}
        if not set(re.findall(pattern, f"{observation} {question}")) <= allowed:
            return None
        return {"observation": observation, "question": question, "evidence": ids}
