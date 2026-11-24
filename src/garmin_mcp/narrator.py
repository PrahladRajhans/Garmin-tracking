"""Optional local insights from checked facts and findings."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import math
import re
import signal
import sqlite3
import statistics
import subprocess
import sys
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from garmin_mcp import coach_review, deep_insight
from garmin_mcp.config import DEFAULT_NARRATOR_MODEL as DEFAULT_MODEL

ITEM_SECONDS = 20
SYNC_SECONDS = 120
DEFAULT_THINKING_MINUTES = 10
INSIGHT_WARM_SECONDS = 90
INSIGHT_OVERHEAD_SECONDS = 240
PORT = 11434
_RESPONSE_LIMIT = 16 * 1024
_SETTING = "ai_narrator"
_MODEL = re.compile(r"[a-zA-Z0-9][\w.-]*(?::[a-zA-Z0-9][\w.-]*)?", flags=re.ASCII)
_NUMBER = re.compile(r"[+\-−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
                     r"(?:(?::|/)\d+(?:\.\d+)?)*|[+\-−]?\.\d+")
_NUMBER_WORD = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|"
    r"fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|trillion|"
    r"first|second|third|fourth|fifth|half|quarter|dozen|once|twice|thrice)\b", re.IGNORECASE)
_BANNED = re.compile(r"\b(?:diagnos\w*|diseases?|injur(?:y|ies)[\s-]+risks?|guarantee\w*|"
                     r"you\s+(?:should|must|need to)|recommend\w*|prescri\w*)\b", re.IGNORECASE)
_SYSTEM = (
    "Choose the one to three numbered sentences that best summarize the readings. "
    "Lead with the most useful reading and choose at most one sentence about each metric. "
    "Return their IDs in order in the selection array."
)

# A model selects and orders these statements. Python supplies their wording and verifies
# each claim's metric, value and unit as well as the overall text limits.
_CLAUSES = {
    "recovery percent": ("Your recovery score is {}%.", "Recovery is {}%."),
    "recovery band": ("Your recovery falls in the {} range.", "Your recovery band is {}."),
    "Garmin readiness score": ("Garmin recorded a readiness score of {}.",
                               "Your Garmin readiness score is {}."),
    "sleep duration hours": ("You slept {} hours.", "You logged {} h of sleep.", "You slept {} h."),
    "Garmin sleep score": ("Garmin recorded a sleep score of {}.", "Your Garmin sleep score is {}."),
    "Garmin sleep need hours": ("Garmin estimated you needed {} hours of sleep.",
                                "Your Garmin sleep target was {} h."),
    "reviewed attempts": ("The experiment has {} reviewed attempts.", "We reviewed {} attempts."),
    "target cadence steps per minute": ("The cadence target is {} steps per minute.",
                                        "Your target cadence is {} steps/min."),
    "minutes near target on last attempt": ("You spent {} minutes near the target last time.",
                                            "Your last attempt included {} minutes near target."),
    "recorded moving minutes on last attempt": ("You moved for {} minutes on the last attempt.",
                                                "The last attempt had {} minutes of moving time."),
    "distance km": ("You ran {} km.", "The run was {} km."),
    "workout distance km": ("The workout covered {} km.", "You covered {} km in this workout."),
    "workout duration": ("The workout lasted {}.", "Your recorded workout duration was {}."),
    "average pace minutes per km": ("Your average pace was {} per km.", "You averaged {}/km."),
    "average heart rate bpm": ("Your heart rate averaged {} bpm.", "Average heart rate was {} bpm."),
    "cadence steps per minute": ("Your cadence averaged {} steps per minute.",
                                 "Average cadence was {} steps/min."),
    "weekly workouts with load data": ("The weekly count of workouts with load data was {}.",),
    "weekly training load points": ("Your weekly training load was {} points.",),
    "weekly average sleep hours": ("Recorded nights averaged {} hours of sleep this week.",),
}

Facts = dict[str, int | float | str]


@dataclass
class Item:
    kind: str
    facts: Facts
    choices: tuple[dict, ...] = ()

    @property
    def prompt(self) -> str:
        if self.choices:
            return _json({"task": self.kind, "evidence": self.facts, "findings": [
                {"id": index, **choice} for index, choice in enumerate(self.choices, 1)
            ]})
        return _json({"item": self.kind, "facts": self.facts})

    @property
    def system(self) -> str:
        if self.choices:
            return ("Choose the most useful follow-up for the supplied task and evidence. "
                    "Weigh the strength and relevance of the evidence and prioritize an actionable "
                    "follow-up consistent with recovery. Treat an association as weaker than direct "
                    "measurements over several days. Return the chosen finding ID only in the JSON field choice.")
        return (f"{_SYSTEM} Optional voice: write checked paraphrases with cited IDs. "
                "You may join two supported clauses with 'and' or 'while'. "
                "Do not add causes, advice or new claims. "
                f"Permitted sentences: {_json(dict(enumerate(_sentences(self.facts), 1)))}")

    @property
    def schema(self) -> dict:
        if self.choices:
            fields = {"choice": {"type": "integer", "enum": list(range(1, len(self.choices) + 1))}}
        else:
            ids = list(range(1, len(_sentences(self.facts)) + 1))
            fields = {
                "selection": {"type": "array", "minItems": 1, "maxItems": min(3, len(self.facts)),
                              "items": {"type": "integer", "enum": ids}},
                "voice": {"type": "array", "maxItems": 3, "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["text", "facts"], "properties": {
                        "text": {"type": "string"}, "facts": {"type": "array", "minItems": 1,
                            "maxItems": 2, "items": {"type": "integer", "enum": ids}},
                    },
                }},
            }
        return {"type": "object", "additionalProperties": False,
                "required": [next(iter(fields))], "properties": fields}

    def response(self, raw: Any) -> str | int | None:
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            return None
        if not isinstance(value, dict):
            return None
        if self.choices:
            choice = value.get("choice") if value.keys() == {"choice"} else None
            return choice if type(choice) is int and 1 <= choice <= len(self.choices) else None
        if value.keys() - {"selection", "voice"}:
            return None
        selected = value.get("selection")
        sentences = list(_sentences(self.facts))
        if not self._citations(selected, len(sentences), min(3, len(self.facts))):
            return None
        if voice := self._voice(value.get("voice"), sentences):
            return voice
        text = validate(" ".join(sentences[index - 1] for index in selected), self.facts)
        return _grounded(text, self.facts) if text else None

    @staticmethod
    def _citations(ids, count, limit):
        return (isinstance(ids, list) and 1 <= len(ids) <= limit
                and all(type(index) is int and 1 <= index <= count for index in ids))

    def _voice(self, value, sentences):
        if not isinstance(value, list) or not 1 <= len(value) <= 3:
            return None
        checked = []
        for entry in value:
            if not isinstance(entry, dict) or entry.keys() != {"text", "facts"}:
                return None
            ids = entry["facts"]
            text = validate(entry["text"], self.facts)
            if not text or not self._citations(ids, len(sentences), 2):
                return None
            expected = [_sentence_key(sentences[index - 1]) for index in ids]
            actual = [_sentence_key(part) for part in re.split(r",? (?:and|while) ", text)]
            if actual != expected:
                return None
            checked.append(text)
        return validate(" ".join(checked), self.facts)

    def key(self, model: str) -> str:
        return hashlib.sha256(_json([1, model, self.system, self.prompt]).encode()).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def settings(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (_SETTING,)).fetchone()
    return json.loads(row[0]) if row else {"enabled": False, "model": DEFAULT_MODEL}


def configure(conn: sqlite3.Connection, enable: bool | None = None,
              model: str | None = None, thinking: bool | None = None,
              thinking_minutes: int | None = None) -> dict[str, Any]:
    before = settings(conn)
    if model is not None:
        model = model.strip()
        if (len(model) > 128 or not _MODEL.fullmatch(model)
                or re.search(r"(?:[:.-]|^)cloud\b|:local$", model, re.IGNORECASE)):
            raise ValueError("Use a downloaded local Ollama tag such as " + DEFAULT_MODEL + ".")
    after = {"enabled": before["enabled"] if enable is None else enable,
             "model": before["model"] if model is None else model}
    if thinking is not None or "thinking" in before:
        after["thinking"] = before.get("thinking", False) if thinking is None else thinking
    if thinking_minutes is not None:
        if type(thinking_minutes) is not int or not 1 <= thinking_minutes <= 30:
            raise ValueError("Choose 1 to 30 minutes of thinking time.")
        after["thinking_minutes"] = thinking_minutes
    elif "thinking_minutes" in before:
        after["thinking_minutes"] = before["thinking_minutes"]
    if after != before:
        with conn:
            conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES (?,?)",
                         (_SETTING, _json(after)))
            conn.execute("INSERT OR REPLACE INTO meta(key,value) "
                         "VALUES ('dashboard_rebuild_pending','1')")
    return after


def update_settings(conn: sqlite3.Connection, enable: bool | None,
                    model: str | None, thinking: bool | None = None,
                    thinking_minutes: int | None = None) -> dict[str, Any]:
    before = settings(conn)
    state = configure(conn, enable, model, thinking, thinking_minutes)
    if state != before:
        # Enabling starts work against the existing archive. Disabling removes saved prose.
        from garmin_mcp import dashboard

        try:
            dashboard.build(conn)
        except (OSError, sqlite3.Error):
            state = {**state, "dashboard_refresh_pending": True}
    return state


def _facts(**values: Any) -> Facts:
    return {label.replace("_", " "): value for label, value in values.items()
            if (type(value) in (float, int) and math.isfinite(value))
            or (label == "recovery_band" and isinstance(value, str)
                and value in {"low", "moderate", "recovered"})
            or (label == "average_pace_minutes_per_km" and isinstance(value, str)
                and re.fullmatch(r"\d{1,3}:[0-5]\d", value))
            or (label == "workout_duration" and isinstance(value, str)
                and re.fullmatch(r"\d{1,3}:[0-5]\d(?::[0-5]\d)?", value))}


def items(data: dict) -> dict[str, Item]:
    """Allowlisted display values only. No dates, IDs, routes, or free-form notes in prompts."""
    if data.get("available") is False:
        return {}
    candidates = {}
    today = not (data.get("older_snapshot") or data.get("sync_retry_required"))
    rec, sleep = data["scores"]["recovery"], data["scores"]["sleep"]
    if today and rec["pct"] is not None:
        candidates["today"] = Item("today", _facts(
            recovery_percent=rec["pct"], recovery_band=rec["label"],
            Garmin_readiness_score=rec["garmin_readiness"]))
    focus = data.get("brief", {}).get("focus", {})
    findings = focus.get("findings", [])
    if today and focus.get("target") and len(findings) > 1:
        # These findings come only from daily_focus, with program-authored text and aggregates.
        choices = tuple({field: item.get(field, "") for field in ("title", "detail", "basis", "action")}
                        for item in findings)
        candidates["focus"] = Item("prioritize a daily follow-up",
                                   _facts(recovery_band=rec["label"]), choices)
    night = data.get("night") or {}
    recorded = data.get("night_summary")
    if today and recorded and night.get("day") == data["end"]:
        hours, saved_score = recorded
        candidates["sleep"] = Item("last night's sleep", _facts(
            sleep_duration_hours=round(hours, 1),
            Garmin_sleep_score=night["overall"] if night.get("overall") is not None else saved_score,
            Garmin_sleep_need_hours=sleep["need_h"] if sleep.get("need_source") == "Garmin sleep need"
            else None))
    review = data.get("weekly_review")
    if today and review:
        week, rest = review["week"], review["recovery"]
        candidates["training"] = Item("seven-day training review", _facts(
            weekly_workouts_with_load_data=week["sessions"] or None,
            weekly_training_load_points=week["trimp"] if week["sessions"] else None,
            weekly_average_sleep_hours=round(rest["avg_sleep_h"], 1)
            if rest["avg_sleep_h"] is not None else None))
    trial = data.get("trial") or {}
    if trial.get("active"):
        target = trial["trial"]["target"].get("cadence_spm")
        attempts = trial["attempts"]
        last = (attempts[-1].get("did_it") or {}) if attempts else {}
        candidates["trial"] = Item("active experiment", _facts(
            reviewed_attempts=len(attempts), target_cadence_steps_per_minute=target,
            minutes_near_target_on_last_attempt=last.get("minutes_at_target"),
            recorded_moving_minutes_on_last_attempt=last.get("moving_minutes")))
    if today and data["runs"]:
        newest = data["runs"][0]
        if questions := coach_review.run_questions(newest):
            match = newest["comparable_effort"]
            candidates[f'run-check-{newest["activity_id"]}'] = Item(
                "choose which uncertainty to check before drawing a conclusion from this run",
                _facts(matched_runs=len(match["matches"]), difference_bpm=match["difference_hr_bpm"],
                       earlier_low_bpm=match["observed_hr_range_bpm"][0],
                       earlier_high_bpm=match["observed_hr_range_bpm"][1]), questions)
    for run in data["runs"]:
        cadence = run["form"].get("cadence_spm") or {}
        hr = run.get("avg_hr")
        candidates[f'run-{run["activity_id"]}'] = Item("run", _facts(
            distance_km=run["km"] or None, average_pace_minutes_per_km=run["pace"],
            average_heart_rate_bpm=round(hr) if isinstance(hr, (float, int))
            and math.isfinite(hr) else None,
            cadence_steps_per_minute=cadence.get("value")))
    for workout in data.get("workouts", []):
        hr = workout.get("avg_hr")
        candidates[f'workout-{workout["id"]}'] = Item("workout", _facts(
            workout_duration=workout.get("duration"),
            workout_distance_km=workout.get("distance_km"),
            average_heart_rate_bpm=round(hr) if isinstance(hr, (float, int))
            and math.isfinite(hr) else None))
    return {name: item for name, item in candidates.items() if item.facts or item.choices}


def _number_key(token: str) -> str:
    def exact(part: re.Match) -> str:
        value = Decimal(part[0])
        digits = format(value, "f") if value else "0"
        return digits.rstrip("0").rstrip(".") if "." in digits else digits

    return re.sub(r"[^:/]+", exact, token.replace(",", "").replace("−", "-"))


def _numbers(text: str) -> set[str]:
    return {_number_key(token) for token in _NUMBER.findall(text)}


def _sentence_key(text: str) -> str:
    plain = re.sub(r"\s+%", "%", text.casefold().rstrip(".!?").strip())
    return _NUMBER.sub(lambda match: _number_key(match[0]), " ".join(plain.split()))


def validate(text: Any, facts: Facts) -> str | None:
    if not isinstance(text, str) or len(text) > 700:
        return None
    plain = unicodedata.normalize("NFKC", text).strip().replace("⁄", "/").replace("∕", "/")
    if (not plain or len(plain.split()) > 60 or re.search(r"[<>*#`]|[\r\n]|[^\S ]", plain)
            or any(unicodedata.category(c).startswith("C") for c in plain)
            or re.search(r"\d\s*[eE][+−-]?\d|\d\s*[×x]\s*\d|\d\s*\^\s*\d", plain)
            or _BANNED.search(plain) or _NUMBER_WORD.search(plain)):
        return None
    # Remove numeric punctuation before counting sentences. Keep each pace and ratio intact.
    sentences = re.sub(r"[.!?]+", ".", _NUMBER.sub("VALUE", plain)).split(".")
    if not 1 <= sum(bool(part.strip()) for part in sentences) <= 3:
        return None
    allowed = set().union(*(_numbers(str(value)) for value in facts.values()))
    return plain if _numbers(plain) <= allowed else None


def _sentences(facts: Facts) -> dict[str, str]:
    return {pattern.format(value): label for label, value in facts.items()
            for pattern in _CLAUSES[label]}


def _grounded(text: str, facts: Facts) -> str | None:
    allowed = {_sentence_key(sentence): label for sentence, label in _sentences(facts).items()}
    verified = {}
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        label = allowed.get(_sentence_key(sentence))
        if label is None:
            return None
        verified.setdefault(label, sentence)
    return " ".join(verified.values())


def _read(db: sqlite3.Connection, item: Item, model: str) -> tuple[str | int | None] | None:
    row = db.execute("SELECT value FROM meta WHERE key=?", ("narrator:" + item.key(model),)).fetchone()
    return (json.loads(row[0]),) if row else None


def cached(conn: sqlite3.Connection, data: dict) -> tuple[dict, bool]:
    state = settings(conn)
    if not state["enabled"]:
        return {}, False
    labels, missing = {}, False
    for name, item in items(data).items():
        found = _read(conn, item, state["model"])
        if found is None:
            missing = True
        elif found[0]:
            labels[name] = ({"choice": found[0]} if item.choices else
                            {"text": found[0], "facts": item.facts})
    for name, item in _deep_items(conn, state, data).items():
        found = _deep_cached(conn, item, state)
        if found is None:
            missing = True
        elif found[0]:
            drafted = found[0]
            labels[name] = {
                **drafted, "lens": item.lens,
                "readings": [{"text": item.rows[i - 1].text, "page": item.rows[i - 1].page,
                              "previous": item.rows[i - 1].previous} for i in drafted["evidence"]],
            }
    return labels, missing


def summary_id(summaries: dict) -> bytes:
    return hashlib.sha256(_json(summaries).encode()).hexdigest().encode("ascii")


def _worker_status(conn, model):
    row = conn.execute("SELECT value FROM meta WHERE key=?", ("narrator_worker:" + model,)).fetchone()
    return json.loads(row[0]) if row else {}


def _record_worker(conn, model, outcome, accepted=False):
    state = _worker_status(conn, model)
    state["outcome"] = outcome
    if accepted:
        state["last_accepted"] = datetime.now(UTC).isoformat(timespec="seconds")
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", ("narrator_worker:" + model, _json(state)))
    return accepted


def snapshot_status(conn, data, summaries, pending):
    """Report recorded worker outcomes without contacting Ollama during HTML rendering."""
    state = settings(conn)
    if not state["enabled"]:
        return {"outcome": "disabled", "count": 0}
    report = _worker_status(conn, state["model"])
    if data.get("sync_retry_required"):
        outcome = "sync_incomplete"
    elif pending:
        previous = report.get("outcome")
        outcome = previous if previous in {"cloud_blocked", "unavailable", "unsupported", "incomplete"} else "pending"
    elif summaries:
        outcome = "ready"
    elif items(data) or _deep_items(conn, state, data):
        outcome = "withheld"
    else:
        outcome = "no_evidence"
    return {"outcome": outcome, "count": len(summaries), "last_accepted": report.get("last_accepted")}


class OllamaUnavailable(Exception):
    """Local server could not verify or finish the request."""


def _timed_out(_signum, _frame) -> None:
    raise TimeoutError("Ollama request timed out")


def _request(method: str, path: str, deadline: float, body: dict | None = None) -> dict:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Ollama request timed out")
    # Literal loopback avoids DNS and proxy configuration. The HTTP origin is localhost:11434.
    client = http.client.HTTPConnection("127.0.0.1", PORT, timeout=remaining)
    headers = {"Host": f"localhost:{PORT}", "Content-Type": "application/json"}
    previous = signal.signal(signal.SIGALRM, _timed_out)
    try:
        signal.setitimer(signal.ITIMER_REAL, remaining)
        client.request(method, path, body=_json(body).encode() if body is not None else None,
                     headers=headers)
        response = client.getresponse()
        if response.status != 200:
            raise OllamaUnavailable
        limit = (256 * 1024 if path == "/api/show" else
                  64 * 1024 if body and body.get("think") else _RESPONSE_LIMIT)
        data = response.read(limit + 1)
        if len(data) > limit:
            raise OllamaUnavailable
        value = json.loads(data)
        if not isinstance(value, dict):
            raise OllamaUnavailable
        return value
    except (OSError, http.client.HTTPException, ValueError) as exc:
        raise OllamaUnavailable from exc
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        client.close()


def _model_profile(model: str, deadline: float) -> dict:
    info = _request("POST", "/api/show", deadline, {"model": model + ":local"})
    capabilities = info.get("capabilities") or []
    controls = info.get("thinking") or {}
    values = controls.get("values", []) if isinstance(controls, dict) else []
    thinks = "thinking" in capabilities or any(value is not False for value in values)
    context = next((value for key, value in (info.get("model_info") or {}).items()
                    if key.endswith(".context_length") and type(value) is int and value > 0), None)
    return {"thinking": thinks, "controls": values, "context_length": context,
            "text_generation": "decision" not in capabilities or "completion" in capabilities,
            "num_ctx": min(context or 2048, 4096 if thinks else 2048)}


def _warm(model: str, profile: dict, deadline: float) -> None:
    _request("POST", "/api/generate", deadline, {"model": model + ":local", "prompt": "",
                                                "keep_alive": "5m", "stream": False,
                                                "options": {"num_ctx": profile["num_ctx"]}})


def _infer(model, profile, item, deadline):
    budget = 35 if profile["thinking"] else ITEM_SECONDS
    response = _request("POST", "/api/generate", min(deadline, time.monotonic() + budget), {
        "model": model + ":local", "system": item.system, "prompt": item.prompt,
        "format": item.schema, "stream": False, "keep_alive": "5m",
        **({"think": False} if profile["thinking"] else {}),
        "options": {"temperature": 0, "num_ctx": profile["num_ctx"],
                    "num_predict": 96 if item.choices else 240},
    })
    if response.get("done") is not True or response.get("done_reason") == "length":
        return None, "incomplete"
    result = item.response(response.get("response"))
    return result, "accepted" if result is not None else "failed_validation"


def _thinking_seconds(state):
    return 60 * state.get("thinking_minutes", DEFAULT_THINKING_MINUTES)


def _deep_item(conn, state, data):
    rows = deep_insight.evidence(data) if state.get("thinking") else ()
    if not rows:
        return None
    lens = "running" if any(row.domain == "running" for row in rows) else "sleep"
    voice, focus, _ = deep_insight.writing_style(conn, lens)
    previous = deep_insight.remembered(conn, data.get("end"))
    return deep_insight.Insight(rows + previous, lens, voice, focus)


def _deep_items(conn, state, data):
    result = {}
    if rows := deep_insight.running_review(data):
        lens = "running_review"
        voice, focus, _ = deep_insight.writing_style(conn, lens)
        result["running-insight"] = deep_insight.Insight(rows, lens, voice, focus)
    if daily := _deep_item(conn, state, data):
        result["deep-insight"] = daily
    if rows := deep_insight.sunday_review(data):
        lens = "sunday_review"
        voice, focus, _ = deep_insight.writing_style(conn, lens)
        result["sunday-insight"] = deep_insight.Insight(rows, lens, voice, focus)
    return result


def _deep_key(item, state):
    content = _json([state["model"], bool(state.get("thinking")), _thinking_seconds(state),
                     item.system, deep_insight.REVIEW, item.prompt])
    return "narrator:deep:" + hashlib.sha256(content.encode()).hexdigest()


def _deep_cached(conn, item, state):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (_deep_key(item, state),)).fetchone()
    return (json.loads(row[0]),) if row else None


def _think_value(profile):
    controls = profile.get("controls", [])
    if True in controls:
        return True
    for level in ("low", "medium", "high"):
        if level in controls:
            return level
    return True


def _deep_request(model, profile, item, deadline, *, still_current=None, think_first=True,
                  thinking_seconds=DEFAULT_THINKING_MINUTES * 60):
    """A thinking draft followed by a separate review of its final answer and cited readings."""
    common = {"model": model + ":local", "stream": False, "keep_alive": "5m"}
    options = {"num_ctx": profile["num_ctx"], "temperature": 0}
    def draft_response(thinking):
        # Let the reasoning model use its default sampling and emit final JSON without an
        # Ollama grammar. Python checks the complete final answer in both modes.
        return _request("POST", "/api/generate",
                        min(deadline, time.monotonic() + (thinking_seconds if thinking else 75)), {
            **common, "system": item.system, "prompt": item.prompt,
            **({} if thinking else {"format": item.schema}),
            **({"think": _think_value(profile) if thinking else False} if profile.get("thinking", True) else {}),
            "options": ({"num_ctx": profile["num_ctx"], "num_predict": 2450} if thinking
                        else {**options, "num_predict": 260}),
        })

    def final(response):
        text = response.get("response")
        if (response.get("done") is not True or response.get("done_reason") == "length"
                or not isinstance(text, str) or not text.strip()):
            raise OllamaUnavailable
        return item.response(text)

    mode = "thinking" if think_first else "direct"
    try:
        draft = final(draft_response(think_first))
    except (OllamaUnavailable, TimeoutError):
        if not think_first or (still_current is not None and not still_current()):
            raise
        mode = "direct_retry"
        draft = final(draft_response(False))
    if still_current is not None and not still_current():
        raise OllamaUnavailable
    if not draft:
        return None
    readings = [{"id": i, "domain": item.rows[i - 1].domain, "reading": item.rows[i - 1].text}
                for i in draft["evidence"]]
    review = _request("POST", "/api/generate", min(deadline, time.monotonic() + 60), {
        **common, "system": deep_insight.REVIEW,
        **({"think": False} if profile.get("thinking", True) else {}),
        "prompt": _json({"proposed": draft, "readings": readings}),
        "format": {"type": "object", "required": ["publish"], "additionalProperties": False,
                   "properties": {"publish": {"type": "boolean"}}},
        "options": {**options, "num_predict": 80},
    })
    if review.get("done") is not True or review.get("done_reason") == "length":
        raise OllamaUnavailable
    try:
        verdict = json.loads(review.get("response"))
    except (TypeError, ValueError):
        return None
    if isinstance(verdict, dict) and verdict.keys() == {"publish"} and verdict["publish"] is True:
        return {**draft, "mode": mode}
    return None


def _cloud_disabled(deadline):
    cloud = _request("GET", "/api/status", deadline).get("cloud")
    return isinstance(cloud, dict) and cloud.get("disabled") is True


def generate(conn: sqlite3.Connection, data: dict, deadline: float, *,
             still_current: Callable[[], bool] | None = None) -> bool:
    """Called only in the detached worker. Returns whether new text was accepted."""
    state = settings(conn)
    if not state["enabled"]:
        return False
    model = state["model"]
    pending = [item for item in items(data).values() if _read(conn, item, model) is None]
    insights = {name: item for name, item in _deep_items(conn, state, data).items()
                if _deep_cached(conn, item, state) is None}
    if not pending and not insights:
        return False
    try:
        if not _cloud_disabled(min(deadline, time.monotonic() + 5)):
            return _record_worker(conn, model, "cloud_blocked")
        profile = _model_profile(model, min(deadline, time.monotonic() + 5))
        if not profile["text_generation"]:
            return _record_worker(conn, model, "unsupported")
        warm_budget = INSIGHT_WARM_SECONDS if state.get("thinking") else 30
        _warm(model, profile, min(deadline, time.monotonic() + warm_budget))
    except (OllamaUnavailable, TimeoutError):
        return _record_worker(conn, model, "unavailable")
    accepted = False
    incomplete = False
    unsupported = False
    for name, insight in insights.items():
        if settings(conn) != state or (still_current is not None and not still_current()):
            return accepted
        use_thinking = bool(state.get("thinking") and profile["thinking"])
        if name == "deep-insight" and not use_thinking:
            unsupported = True
            continue
        seconds = _thinking_seconds(state)
        item_budget = (seconds if use_thinking else 0) + 135
        try:
            draft = _deep_request(model, profile, insight, min(deadline, time.monotonic() + item_budget),
                                  still_current=still_current, think_first=use_thinking, thinking_seconds=seconds)
        except (OllamaUnavailable, TimeoutError):
            incomplete = True
        else:
            if settings(conn) != state or (still_current is not None and not still_current()):
                return False
            with conn:
                conn.execute("INSERT OR IGNORE INTO meta VALUES (?,?)",
                             (_deep_key(insight, state), _json(draft)))
                if draft and name == "deep-insight":
                    deep_insight.remember(conn, data.get("end"),
                                         [insight.rows[i - 1] for i in draft["evidence"]])
            accepted |= draft is not None
    for item in pending:
        if settings(conn) != state or (still_current is not None and not still_current()):
            return accepted
        if time.monotonic() >= deadline:
            incomplete = True
            break
        try:
            text, outcome = _infer(model, profile, item, deadline)
        except (OllamaUnavailable, TimeoutError):
            incomplete = True
            continue
        if outcome == "incomplete":
            incomplete = True
            continue
        with conn:
            conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES (?,?)",
                         ("narrator:" + item.key(model), _json(text)))
        accepted |= text is not None
    result = "incomplete" if incomplete else "unsupported" if unsupported else "ready" if accepted else "withheld"
    return _record_worker(conn, model, result, accepted)


def _sync_in_progress(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM meta WHERE key='sync_retry_required'").fetchone() is not None


def check(conn: sqlite3.Connection) -> dict[str, Any]:
    """Inspect Ollama and coverage without sending health facts to the model."""
    from garmin_mcp import dashboard

    state = settings(conn)
    profile = None
    try:
        deadline = time.monotonic() + 5
        cloud = _request("GET", "/api/status", deadline).get("cloud")
        if not isinstance(cloud, dict) or cloud.get("disabled") is not True:
            service = "cloud_disabled_not_verified"
        else:
            models = _request("GET", "/api/tags", deadline).get("models", [])
            tag = state["model"] if ":" in state["model"] else state["model"] + ":latest"
            installed = isinstance(models, list) and any(
                isinstance(row, dict) and row.get("name") == tag for row in models)
            service = "ready" if installed else "model_not_installed"
            if installed:
                profile = _model_profile(state["model"], deadline)
    except (OllamaUnavailable, TimeoutError):
        service = "local_api_unavailable"
    coverage = {}
    applied = None
    status = {"outcome": "disabled", "count": 0}
    if state["enabled"]:
        data = dashboard.collect(conn)
        for name, item in items(data).items():
            found = _read(conn, item, state["model"])
            group = name.partition("-")[0]
            counts = coverage.setdefault(group, {"ready": 0, "pending": 0, "rejected": 0})
            counts["pending" if found is None else "ready" if found[0] else "rejected"] += 1
        for name, insight in _deep_items(conn, state, data).items():
            found = _deep_cached(conn, insight, state)
            counts = {"ready": 0, "pending": 0, "rejected": 0}
            counts["pending" if found is None else "ready" if found[0] else "rejected"] = 1
            groups = {"deep-insight": "interpretation", "running-insight": "running_review",
                      "sunday-insight": "sunday_review"}
            coverage[groups[name]] = counts
        path, _ = dashboard._snapshot_paths()
        summaries, missing = cached(conn, data)
        status = snapshot_status(conn, data, summaries, missing)
        applied = dashboard._narration_id(path) == summary_id(summaries)
    if profile and not profile["text_generation"]:
        service = "model_does_not_support_text_generation"
    elif profile and state.get("thinking") and not profile["thinking"]:
        service = "model_does_not_support_thinking"
    report = conn.execute("SELECT value FROM meta WHERE key=?",
                          ("narrator_eval:" + state["model"],)).fetchone()
    return {**state, "ollama": service, "coverage": coverage, "model_profile": profile, "snapshot_status": status,
            "last_eval": json.loads(report[0]) if report else None,
            "thinking_minutes": _thinking_seconds(state) // 60,
            "prompt_profile": deep_insight.writing_style(conn, "daily")[2],
            "cache_matches_dashboard": applied, "sync_incomplete": _sync_in_progress(conn)}


def start_worker(conn: sqlite3.Connection, path: Path, snapshot: bytes) -> None:
    database = conn.execute("PRAGMA database_list").fetchone()[2]
    if not database:
        return
    try:
        subprocess.Popen(
            [sys.executable, "-m", "garmin_mcp.narrator", "--worker", database,
             str(path.parent.resolve()), snapshot.decode("ascii")],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return  # analytics and the rendered dashboard are already available


def _worker(database: Path, out_dir: Path, snapshot: bytes) -> None:
    import fcntl

    from garmin_mcp import dashboard, db

    path = out_dir / "index.html"
    wait_until = time.monotonic() + 3 * (30 * 60 + INSIGHT_OVERHEAD_SECONDS) + SYNC_SECONDS
    lock_path = database.with_name(database.name + ".narrator.lock")
    with lock_path.open("a") as lock:
        # A newer build should get a turn once the older worker releases the database lock.
        while dashboard._snapshot_id(path) == snapshot and time.monotonic() < wait_until:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(0.25)
        else:
            return
        if dashboard._snapshot_id(path) != snapshot:
            return
        conn = db.connect(database)
        try:
            if settings(conn)["enabled"] and not _sync_in_progress(conn):
                data = dashboard.collect(conn)
                state = settings(conn)
                before_status = _worker_status(conn, state["model"])
                count = len(_deep_items(conn, state, data))
                budget = SYNC_SECONDS + count * (
                    _thinking_seconds(state) + INSIGHT_OVERHEAD_SECONDS if state.get("thinking") else 135)
                generate(conn, data, time.monotonic() + budget,
                         still_current=lambda: dashboard._snapshot_id(path) == snapshot
                         and not _sync_in_progress(conn))
                summaries, _ = cached(conn, data)
                if (dashboard._narration_id(path) != summary_id(summaries)
                        or _worker_status(conn, state["model"]) != before_status):
                    dashboard.build(conn, only_if_snapshot=snapshot, out_dir=out_dir)
        finally:
            conn.close()


def evaluate(conn, models):
    """Exercise the real response validators on fictional inputs only."""
    fixtures = (
        Item("fictional recovery", {"recovery percent": 73, "Garmin readiness score": 60}),
        Item("fictional sleep", {"sleep duration hours": 7.5, "Garmin sleep score": 82}),
        Item("fictional run", {"distance km": 5, "average pace minutes per km": "6:20",
                               "average heart rate bpm": 143}),
        Item("fictional workout", {"workout duration": "24:57", "average heart rate bpm": 125}),
        Item("fictional follow-up", {"recovery percent": 61},
             ({"title": "Review the sleep readings"}, {"title": "Compare the next easy run"})),
    )
    if not _cloud_disabled(time.monotonic() + 5):
        raise ValueError("Ollama must confirm cloud access is disabled before evaluation.")
    if not models:
        installed = _request("GET", "/api/tags", time.monotonic() + 5).get("models", [])
        models = [model["name"] for model in installed
                  if isinstance(model, dict) and isinstance(model.get("name"), str)]
    reports = {}
    for model in dict.fromkeys(models):
        if len(model) > 128 or not _MODEL.fullmatch(model) or "cloud" in model.lower():
            continue
        outcomes, durations = {}, []
        try:
            profile = _model_profile(model, time.monotonic() + 5)
            if not profile["text_generation"]:
                reports[model] = {"error": "model_does_not_support_text_generation"}
                continue
            _warm(model, profile, time.monotonic() + 30)
        except (OllamaUnavailable, TimeoutError):
            reports[model] = {"error": "model_unavailable"}
            continue
        for item in fixtures:
            start = time.monotonic()
            try:
                _, outcome = _infer(model, profile, item, start + 35)
            except (OllamaUnavailable, TimeoutError):
                outcome = "request_failed_or_timed_out"
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
            durations.append(time.monotonic() - start)
        report = {"cases": len(fixtures), "acceptance": outcomes.get("accepted", 0) / len(fixtures),
                  "outcomes": outcomes, "median_seconds": round(statistics.median(durations), 2)}
        reports[model] = report
        with conn:
            conn.execute("INSERT OR REPLACE INTO meta VALUES (?,?)",
                         ("narrator_eval:" + model, _json(report)))
    qualified = [tag for tag, report in reports.items() if report.get("acceptance", 0) >= .95]
    return {"models": reports,
            "recommended": min(qualified, key=lambda tag: reports[tag]["median_seconds"])
            if qualified else None}


def main() -> None:
    from garmin_mcp import db
    from garmin_mcp.config import db_path

    parser = argparse.ArgumentParser(description="Settings for the optional local Ollama narrator.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--enable", dest="enable", action="store_true")
    group.add_argument("--disable", dest="enable", action="store_false")
    parser.set_defaults(enable=None)
    parser.add_argument("--model", help=f"Downloaded Ollama model tag (default {DEFAULT_MODEL})")
    parser.add_argument("--check", action="store_true",
                        help="Check local Ollama and count ready, pending and rejected summaries")
    parser.add_argument("--thinking", action=argparse.BooleanOptionalAction, default=None,
                        help="Use deliberate reasoning for the daily evidence review")
    parser.add_argument("--thinking-minutes", type=int, help="Time for the thinking draft, 1 to 30 minutes")
    parser.add_argument("--eval-insight", action="store_true", help="Try a fictional thinking insight")
    parser.add_argument("--insight-case", choices=deep_insight.FICTIONAL_CASES, default="mixed-recovery",
                        help="Select the fictional evidence used by --eval-insight")
    parser.add_argument("--eval", action="store_true", help="Benchmark installed models with fiction")
    parser.add_argument("--models", help="Comma-separated local tags to benchmark")
    parser.add_argument("--worker", nargs=3, metavar="ARG", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        database, out_dir, snapshot = args.worker
        _worker(Path(database), Path(out_dir), snapshot.encode("ascii"))
        return
    conn = db.connect(db_path())
    try:
        try:
            if args.eval_insight:
                chosen = args.model or settings(conn)["model"]
                if len(chosen) > 128 or not _MODEL.fullmatch(chosen) or "cloud" in chosen.lower():
                    raise ValueError("Choose an installed local model.")
                minutes = (args.thinking_minutes if args.thinking_minutes is not None
                           else _thinking_seconds(settings(conn)) // 60)
                if not 1 <= minutes <= 30:
                    raise ValueError("Choose 1 to 30 minutes of thinking time.")
                deadline = time.monotonic() + minutes * 60 + INSIGHT_OVERHEAD_SECONDS
                if not _cloud_disabled(time.monotonic() + 5):
                    raise ValueError("Ollama must confirm cloud access is disabled.")
                model_profile = _model_profile(chosen, time.monotonic() + 5)
                if not model_profile["text_generation"]:
                    raise ValueError("This model does not support Ollama text generation.")
                if args.thinking is not False and not model_profile["thinking"]:
                    raise ValueError("This model does not advertise thinking support.")
                _warm(chosen, model_profile, time.monotonic() + INSIGHT_WARM_SECONDS)
                lens, rows = deep_insight.FICTIONAL_CASES[args.insight_case]
                voice, focus, _ = deep_insight.writing_style(conn, lens)
                fixture = deep_insight.Insight(rows, lens, voice, focus)
                start = time.monotonic()
                try:
                    insight = _deep_request(chosen, model_profile, fixture, deadline,
                                            think_first=args.thinking is not False, thinking_seconds=minutes * 60)
                except (OllamaUnavailable, TimeoutError):
                    print(_json({"model": chosen, "status": "incomplete_or_timed_out",
                                 "seconds": round(time.monotonic() - start, 2)}))
                    return
                print(_json({"model": chosen, "case": args.insight_case, "insight": insight,
                             "status": "accepted" if insight else "withheld",
                             "seconds": round(time.monotonic() - start, 2)}))
                return
            if args.eval:
                print(json.dumps(evaluate(conn, [tag.strip() for tag in args.models.split(",")] if args.models else [])))
                return
            state = update_settings(conn, args.enable, args.model, args.thinking, args.thinking_minutes)
        except (OllamaUnavailable, TimeoutError):
            parser.error("Could not reach the local Ollama service.")
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(check(conn) if args.check else state))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
