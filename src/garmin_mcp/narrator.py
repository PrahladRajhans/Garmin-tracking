"""Optional prose for dashboard facts. The sync and renderer never call Ollama."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import math
import re
import signal
import sqlite3
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "qwen2.5:3b-instruct"
ITEM_SECONDS = 20
SYNC_SECONDS = 120
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
    "Rewrite the provided dashboard facts into one to three plain, friendly, factual sentences, "
    "at most 60 words. Use only the given facts. Never add or infer advice, interpretation, "
    "predictions, medical claims, explanations, comparisons, or numbers. Keep the meaning, "
    "units, and source of each fact you use. Copy numbers as digits. Keep a pace such as m:ss "
    "as written. Choose and order the permitted sentences that best summarize the facts. "
    "Return them in the sentences array, with at most one statement about each fact."
)

# A model may select, order and phrase these statements. Python verifies the actual claim
# by checking the metric, value and unit together as well as the overall text limits.
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
    "average pace minutes per km": ("Your average pace was {} per km.", "You averaged {}/km."),
    "average heart rate bpm": ("Your heart rate averaged {} bpm.", "Average heart rate was {} bpm."),
    "cadence steps per minute": ("Your cadence averaged {} steps per minute.",
                                 "Average cadence was {} steps/min."),
}

Facts = dict[str, int | float | str]


@dataclass
class Item:
    kind: str
    facts: Facts

    @property
    def prompt(self) -> str:
        return _json({"item": self.kind, "facts": self.facts})

    @property
    def system(self) -> str:
        return f"{_SYSTEM}\n\nPermitted sentences: {_json(list(_sentences(self.facts)))}"

    def key(self, model: str) -> str:
        return hashlib.sha256(_json([1, model, self.system, self.prompt]).encode()).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def settings(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (_SETTING,)).fetchone()
    return json.loads(row[0]) if row else {"enabled": False, "model": DEFAULT_MODEL}


def configure(conn: sqlite3.Connection, enable: bool | None = None,
              model: str | None = None) -> dict[str, Any]:
    before = settings(conn)
    if model is not None:
        model = model.strip()
        if (len(model) > 128 or not _MODEL.fullmatch(model)
                or re.search(r"(?:[:.-]|^)cloud\b|:local$", model, re.IGNORECASE)):
            raise ValueError("Use a downloaded local Ollama tag such as " + DEFAULT_MODEL + ".")
    after = {"enabled": before["enabled"] if enable is None else enable,
             "model": before["model"] if model is None else model}
    if after != before:
        with conn:
            conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES (?,?)",
                         (_SETTING, _json(after)))
            conn.execute("INSERT OR REPLACE INTO meta(key,value) "
                         "VALUES ('dashboard_rebuild_pending','1')")
    return after


def update_settings(conn: sqlite3.Connection, enable: bool | None,
                    model: str | None) -> dict[str, Any]:
    before = settings(conn)
    state = configure(conn, enable, model)
    if before["enabled"] and state != before:
        # Remove summaries for the old setting from the local and iCloud copies immediately.
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
                and re.fullmatch(r"\d{1,3}:[0-5]\d", value))}


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
    night = data.get("night") or {}
    recorded = data.get("night_summary")
    if today and recorded and night.get("day") == data["end"]:
        hours, saved_score = recorded
        candidates["sleep"] = Item("last night's sleep", _facts(
            sleep_duration_hours=round(hours, 1),
            Garmin_sleep_score=night["overall"] if night.get("overall") is not None else saved_score,
            Garmin_sleep_need_hours=sleep["need_h"] if sleep.get("need_source") == "Garmin sleep need"
            else None))
    trial = data.get("trial") or {}
    if trial.get("active"):
        target = trial["trial"]["target"].get("cadence_spm")
        attempts = trial["attempts"]
        last = (attempts[-1].get("did_it") or {}) if attempts else {}
        candidates["trial"] = Item("active experiment", _facts(
            reviewed_attempts=len(attempts), target_cadence_steps_per_minute=target,
            minutes_near_target_on_last_attempt=last.get("minutes_at_target"),
            recorded_moving_minutes_on_last_attempt=last.get("moving_minutes")))
    for run in data["runs"]:
        cadence = run["form"].get("cadence_spm") or {}
        hr = run.get("avg_hr")
        candidates[f'run-{run["activity_id"]}'] = Item("run", _facts(
            distance_km=run["km"] or None, average_pace_minutes_per_km=run["pace"],
            average_heart_rate_bpm=round(hr) if isinstance(hr, (float, int))
            and math.isfinite(hr) else None,
            cadence_steps_per_minute=cadence.get("value")))
    return {name: item for name, item in candidates.items() if item.facts}


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


def _grounded(text: str, facts: Facts) -> bool:
    allowed = {_sentence_key(sentence): label for sentence, label in _sentences(facts).items()}
    used = [_sentence_key(sentence) for sentence in re.split(r"(?<=[.!?])\s+", text)]
    return set(used) <= allowed.keys() and len({allowed[sentence] for sentence in used}) == len(used)


def _response_text(response: Any, facts: Facts) -> str | None:
    if not isinstance(response, str):
        return None
    try:
        decoded = json.loads(response)
    except ValueError:
        return None
    if not isinstance(decoded, dict) or decoded.keys() != {"sentences"}:
        return None
    sentences = decoded["sentences"]
    if not isinstance(sentences, list) or not 1 <= len(sentences) <= 3 or not all(
        isinstance(sentence, str) and sentence.endswith(".") and "\n" not in sentence
        for sentence in sentences
    ):
        return None
    text = validate(" ".join(sentences), facts)
    return text if text and _grounded(text, facts) else None


def _read(db: sqlite3.Connection, item: Item, model: str) -> tuple[str | None] | None:
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
            labels[name] = {"text": found[0], "facts": item.facts}
    return labels, missing


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
        data = response.read(_RESPONSE_LIMIT + 1)
        if len(data) > _RESPONSE_LIMIT:
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


def generate(conn: sqlite3.Connection, data: dict, deadline: float) -> bool:
    """Called only in the detached worker. Returns whether new text was accepted."""
    state = settings(conn)
    if not state["enabled"]:
        return False
    model = state["model"]
    pending = [item for item in items(data).values() if _read(conn, item, model) is None]
    if not pending:
        return False
    try:
        status = _request("GET", "/api/status", min(deadline, time.monotonic() + ITEM_SECONDS))
        cloud = status.get("cloud")
        if not isinstance(cloud, dict) or cloud.get("disabled") is not True:
            return False
    except (OllamaUnavailable, TimeoutError):
        return False
    accepted = False
    for item in pending:
        if time.monotonic() >= deadline or settings(conn) != state:
            break
        item_deadline = min(deadline, time.monotonic() + ITEM_SECONDS)
        try:
            response = _request("POST", "/api/generate", item_deadline, {
                "model": model + ":local", "system": item.system, "prompt": item.prompt,
                "format": {"type": "object", "additionalProperties": False,
                           "required": ["sentences"], "properties": {"sentences": {
                               "type": "array", "minItems": 1, "maxItems": 3,
                               "items": {"type": "string", "enum": list(_sentences(item.facts))},
                           }}},
                "stream": False, "options": {"temperature": 0, "num_ctx": 2048, "num_predict": 128},
            })
        except (OllamaUnavailable, TimeoutError):
            continue  # a failed request can be tried again on the next sync
        if response.get("done") is not True or response.get("done_reason") == "length":
            continue
        text = _response_text(response.get("response"), item.facts)
        with conn:
            conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES (?,?)",
                         ("narrator:" + item.key(model), _json(text)))
        accepted |= text is not None
    return accepted


def _sync_in_progress(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM meta WHERE key='sync_retry_required'").fetchone() is not None


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

    deadline = time.monotonic() + SYNC_SECONDS
    lock_path = database.with_name(database.name + ".narrator.lock")
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        if dashboard._snapshot_id(out_dir / "index.html") != snapshot:
            return
        conn = db.connect(database)
        try:
            if (settings(conn)["enabled"] and not _sync_in_progress(conn)
                    and generate(conn, dashboard.collect(conn), deadline)
                    and not _sync_in_progress(conn)):
                dashboard.build(conn, only_if_snapshot=snapshot, out_dir=out_dir)
        finally:
            conn.close()


def main() -> None:
    from garmin_mcp import db
    from garmin_mcp.config import db_path

    parser = argparse.ArgumentParser(description="Settings for the optional local Ollama narrator.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--enable", dest="enable", action="store_true")
    group.add_argument("--disable", dest="enable", action="store_false")
    parser.set_defaults(enable=None)
    parser.add_argument("--model", help=f"Downloaded Ollama model tag (default {DEFAULT_MODEL})")
    parser.add_argument("--worker", nargs=3, metavar="ARG", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        database, out_dir, snapshot = args.worker
        _worker(Path(database), Path(out_dir), snapshot.encode("ascii"))
        return
    conn = db.connect(db_path())
    try:
        try:
            state = update_settings(conn, args.enable, args.model)
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(state))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
