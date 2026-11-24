"""Coaching follow-up: record what you tried, how it felt, and what changed on comparable runs.

A *trial* is one small change you choose to try (e.g. "cadence ~175 spm for 1-minute blocks on
easy runs"). Every run after the trial starts is an *attempt*. For each attempt we record:

- **What you did:** for cadence trials, the minutes the watch recorded at or above the target
  (FIT cadence is per foot, so it is doubled to steps/min).
- **How it felt:** Garmin's post-run prompts, read from the activity summary:
  `workoutFeel` (0 very weak, 25 weak, 50 normal, 75 strong, 100 very strong) and
  `workoutRpe` (10-100, i.e. perceived effort 1-10). Plus optional notes you log through
  Claude: knee comfort during and the next morning (0 = none, 10 = worst), and free text.
- **What changed:** the attempt versus your own *comparable runs before the trial* (same run
  type, average pace within +/-30 s/km, moving time within +/-40 %, steady). We compare
  heart rate, efficiency (speed per heartbeat), heart-rate drift, cadence and stride length,
  and give the median of the comparison runs.

Honesty rules:
- One attempt is anecdote: shown as "early", never as a result.
- Changes smaller than normal run-to-run variation are reported as "about the same".
- We describe what changed; we don't claim the trial caused it.
"""

from __future__ import annotations

import itertools
import json
import sqlite3
import statistics
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

SCHEMA = """
CREATE TABLE IF NOT EXISTS coach_trials (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  target TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  closed TEXT,
  closing_note TEXT
);
CREATE TABLE IF NOT EXISTS coach_trial_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trial_id INTEGER NOT NULL,
  activity_id INTEGER,
  logged TEXT NOT NULL,
  knee_during INTEGER,
  knee_next_morning INTEGER,
  felt INTEGER,
  effort INTEGER,
  note TEXT
);
"""

FEEL_WORDS = {0: "very weak", 25: "weak", 50: "normal", 75: "strong", 100: "very strong"}
PACE_WINDOW_S = 30
DURATION_WINDOW = 0.40
MAX_BASELINE = 6
# A change smaller than this is "about the same" (typical run-to-run noise on wrist data).
NOISE = {"avg_hr": 3.0, "efficiency_factor_pct": 3.0, "decoupling_pct": 2.0,
         "cadence_spm": 2.0, "step_length_m": 0.02}


def ensure(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _check_scale(name: str, value: int | None, lo: int, hi: int) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or not lo <= value <= hi:
        raise ValueError(f"{name} must be a whole number from {lo} to {hi}")
    return value


# --------------------------------------------------------------------------- recording
def start(conn: sqlite3.Connection, kind: str = "cadence", title: str | None = None,
          target_spm: int | None = None) -> dict[str, Any]:
    """Start a trial. Only one trial is active at a time; starting a new one closes the old."""
    ensure(conn)
    if kind not in ("cadence", "custom"):
        raise ValueError("kind must be 'cadence' or 'custom'")
    target: dict[str, Any] = {}
    if kind == "cadence":
        if target_spm is None:
            target_spm = suggested_cadence(conn)
        if target_spm is None:
            raise ValueError("No recent steady run with cadence to base a target on; "
                             "pass target_spm")
        if not 140 <= target_spm <= 200:
            raise ValueError("target_spm must be between 140 and 200")
        target = {"cadence_spm": int(target_spm)}
        title = title or f"Cadence about {target_spm} steps/min in 1-minute blocks on easy runs"
    if not title:
        raise ValueError("A custom trial needs a title, e.g. 'Lights out by 01:00'")
    for (tid,) in conn.execute("SELECT id FROM coach_trials WHERE status='active'").fetchall():
        close(conn, tid, "replaced by a new trial")
    cur = conn.execute("INSERT INTO coach_trials(created, kind, title, target) VALUES (?,?,?,?)",
                       (_now(), kind, title, json.dumps(target)))
    conn.commit()
    return {"trial_id": cur.lastrowid, "kind": kind, "title": title, "target": target,
            "next": "Do it on your next easy run, then answer Garmin's 'How did you feel?' "
                    "prompt. Tell Claude your knee comfort that evening and the next morning."}


def close(conn: sqlite3.Connection, trial_id: int, note: str | None = None) -> dict[str, Any]:
    ensure(conn)
    conn.execute("UPDATE coach_trials SET status='closed', closed=?, closing_note=? "
                 "WHERE id=? AND status='active'", (_now(), note, trial_id))
    conn.commit()
    return {"trial_id": trial_id, "status": "closed", "note": note}


def log(conn: sqlite3.Connection, *, activity_id: int | None = None,
        knee_during: int | None = None, knee_next_morning: int | None = None,
        felt: int | None = None, effort: int | None = None,
        note: str | None = None, trial_id: int | None = None) -> dict[str, Any]:
    """Record how an attempt felt. Defaults: the active trial and its latest attempt run.
    felt: 1-5 (1 very weak … 5 very strong); effort: 1-10; knee: 0 (none) - 10 (worst)."""
    ensure(conn)
    knee_during = _check_scale("knee_during", knee_during, 0, 10)
    knee_next_morning = _check_scale("knee_next_morning", knee_next_morning, 0, 10)
    felt = _check_scale("felt", felt, 1, 5)
    effort = _check_scale("effort", effort, 1, 10)
    trial = _trial(conn, trial_id)
    if not trial:
        raise ValueError("No active trial. Start one first.")
    if activity_id is None:
        runs = _attempt_runs(conn, trial)
        activity_id = runs[-1][0] if runs else None
    cur = conn.execute(
        "INSERT INTO coach_trial_logs(trial_id, activity_id, logged, knee_during, "
        "knee_next_morning, felt, effort, note) VALUES (?,?,?,?,?,?,?,?)",
        (trial["id"], activity_id, _now(), knee_during, knee_next_morning, felt, effort, note))
    conn.commit()
    return {"log_id": cur.lastrowid, "trial_id": trial["id"], "activity_id": activity_id}


# --------------------------------------------------------------------------- reading
def _trial(conn: sqlite3.Connection, trial_id: int | None = None, *,
           before: str | None = None) -> dict[str, Any] | None:
    ensure(conn)
    q = "SELECT id, created, kind, title, target, status, closed FROM coach_trials WHERE "
    if trial_id:
        row = conn.execute(q + "id=?", (trial_id,)).fetchone()
    elif before:
        row = conn.execute(q + "julianday(created) < julianday(?) AND "
                           "(closed IS NULL OR julianday(closed) >= julianday(?)) "
                           "ORDER BY id DESC LIMIT 1", (before, before)).fetchone()
    else:
        row = conn.execute(q + "status='active' ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return None
    keys = ("id", "created", "kind", "title", "target", "status", "closed")
    t = dict(zip(keys, row, strict=True))
    t["target"] = json.loads(t["target"] or "{}")
    if before:
        t.update(status="active", closed=None)
    return t


def _activity_start(gmt: str | None, local: str | None, zone: ZoneInfo) -> datetime | None:
    try:
        stamp = datetime.fromisoformat(gmt or local or "")
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC if gmt else zone)


def _attempt_runs(conn: sqlite3.Connection, trial: dict[str, Any], *,
                  through_day: str = "9999-12-31", zone: ZoneInfo | None = None) -> list[tuple]:
    from garmin_mcp.engine import _tz
    from garmin_mcp.loads import RUN_TYPES

    zone = zone or _tz(conn)
    created = datetime.fromisoformat(trial["created"])
    end = datetime.fromisoformat(trial["closed"]) if trial["closed"] else datetime.max.replace(tzinfo=UTC)
    marks = ",".join("?" * len(RUN_TYPES))
    rows = conn.execute(
        f"SELECT activity_id, start_time_local, type, start_time_gmt FROM activities WHERE type IN ({marks}) "
        "AND fit_parsed=1 AND substr(start_time_local,1,10) BETWEEN ? AND ? "
        "ORDER BY julianday(start_time_local), activity_id",
        (*RUN_TYPES, created.astimezone(zone).date().isoformat(), through_day))
    return [(aid, local, kind) for aid, local, kind, gmt in rows
            if (start := _activity_start(gmt, local, zone)) is not None and created < start <= end]


def garmin_feel(conn: sqlite3.Connection, aid: int) -> dict[str, Any]:
    row = conn.execute("SELECT summary FROM activities WHERE activity_id=?", (aid,)).fetchone()
    try:
        s = json.loads(row[0]) if row and row[0] else {}
    except (TypeError, ValueError):
        s = {}
    if not isinstance(s, dict):
        s = {}
    # Live API puts the answers in summaryDTO or at the top level; the export under _export.
    feel = rpe = None
    for part in (s.get("summaryDTO"), s, s.get("_export")):
        if isinstance(part, dict):
            feel = feel if feel is not None else part.get("workoutFeel")
            rpe = rpe if rpe is not None else part.get("workoutRpe")
    out: dict[str, Any] = {}
    if isinstance(feel, (int, float)) and feel in FEEL_WORDS:
        out["felt"] = FEEL_WORDS[int(feel)]
    if isinstance(rpe, (int, float)) and 10 <= rpe <= 100:
        out["effort_1_10"] = round(rpe / 10)
    return out


def minutes_at_cadence(conn: sqlite3.Connection, aid: int, target: int) -> dict[str, Any]:
    """Moving minutes with recorded cadence >= target - 2 steps/min (FIT one-foot x 2)."""
    from garmin_mcp.coaching import _moving, _rows

    mov = [r for r in _moving(_rows(conn, aid)) if r.get("cadence")]
    if len(mov) < 60:
        return {"available": False}
    times = [r["t"] for r in mov]
    gaps = [b - a for a, b in itertools.pairwise(times)]
    step = statistics.median(gaps) if gaps else 1.0
    step = step if 0 < step <= 10 else 1.0
    hits = sum(1 for r in mov if r["cadence"] * 2 >= target - 2)
    return {"available": True, "minutes_at_target": round(hits * step / 60, 1),
            "moving_minutes": round(len(mov) * step / 60, 1)}


def _baseline(conn: sqlite3.Connection, trial: dict[str, Any], aid: int,
              m: dict[str, Any]) -> list[dict[str, Any]]:
    """Steady runs of the same type before the trial started, near this attempt's pace and
    duration. Most recent first, at most MAX_BASELINE."""
    from garmin_mcp.coaching import run_metrics
    from garmin_mcp.engine import _tz

    typ = conn.execute("SELECT type FROM activities WHERE activity_id=?", (aid,)).fetchone()
    created = datetime.fromisoformat(trial["created"])
    zone = _tz(conn)
    pace = 1000 / m["avg_speed"]
    out = []
    checked = 0
    for other, start, gmt in conn.execute(
            "SELECT activity_id, start_time_local, start_time_gmt FROM activities WHERE type=? AND fit_parsed=1 "
            "AND substr(start_time_local,1,10) <= ? ORDER BY julianday(start_time_local) DESC",
            (typ[0] if typ else None, created.astimezone(zone).date().isoformat())):
        at = _activity_start(gmt, start, zone)
        if at is None or at >= created:
            continue
        if checked == 60:
            break
        checked += 1
        o = run_metrics(conn, other)
        if not o or not o.get("steady") or not o.get("avg_speed"):
            continue
        if abs(1000 / o["avg_speed"] - pace) > PACE_WINDOW_S:
            continue
        if abs(o["moving_s"] - m["moving_s"]) > DURATION_WINDOW * m["moving_s"]:
            continue
        out.append({"activity_id": other, "date": start[:10], **o})
        if len(out) == MAX_BASELINE:
            break
    return out


def _change(name: str, now: float | None, ref: list[float], unit: str, better: str,
            nd: int = 1) -> dict[str, Any] | None:
    ref = [v for v in ref if isinstance(v, (int, float))]
    if now is None or not ref:
        return None
    med = statistics.median(ref)
    if name == "efficiency_factor":
        diff_pct = (now - med) / med * 100 if med else 0
        same = abs(diff_pct) < NOISE["efficiency_factor_pct"]
        word = "about the same" if same else ("better" if diff_pct > 0 else "worse")
        return {"metric": name, "this_run": round(now, 3), "usual": round(med, 3),
                "change_pct": round(diff_pct, 1), "verdict": word}
    diff = now - med
    same = abs(diff) < NOISE.get(name, 0)
    if same:
        word = "about the same"
    elif better == "lower":
        word = "better" if diff < 0 else "worse"
    elif better == "higher":
        word = "better" if diff > 0 else "worse"
    else:
        word = "higher" if diff > 0 else "lower"
    return {"metric": name, "this_run": round(now, nd), "usual": round(med, nd),
            "change": round(diff, nd), "unit": unit, "verdict": word}


def attempt_review(conn: sqlite3.Connection, trial: dict[str, Any], aid: int, *,
                   before: str = "9999-12-31") -> dict[str, Any]:
    from garmin_mcp.coaching import _pace, run_metrics

    m = run_metrics(conn, aid)
    start = conn.execute("SELECT start_time_local FROM activities WHERE activity_id=?",
                         (aid,)).fetchone()
    out: dict[str, Any] = {"activity_id": aid, "date": start[0][:10] if start else None}
    if not m or not m.get("avg_speed"):
        return {**out, "available": False, "reason": "no second-by-second data for this run"}
    out.update(pace=_pace(m["avg_speed"]), garmin_feel=garmin_feel(conn, aid))
    logs = conn.execute("SELECT knee_during, knee_next_morning, felt, effort, note FROM "
                        "coach_trial_logs WHERE trial_id=? AND activity_id=? "
                        "AND julianday(logged) < julianday(?) ORDER BY id",
                        (trial["id"], aid, before)).fetchall()
    if logs:
        merged: dict[str, Any] = {}
        for kd, kn, felt, eff, note in logs:  # later entries fill or override earlier ones
            for k, v in (("knee_during", kd), ("knee_next_morning", kn), ("felt_1_5", felt),
                         ("effort_1_10", eff), ("note", note)):
                if v is not None:
                    merged[k] = v
        out["your_notes"] = merged
    target = trial["target"].get("cadence_spm")
    if target:
        out["did_it"] = minutes_at_cadence(conn, aid, target)
    base = _baseline(conn, trial, aid, m)
    out["comparison_runs"] = [{"activity_id": b["activity_id"], "date": b["date"]} for b in base]
    if not m.get("steady"):
        out["comparison_note"] = ("This run wasn't steady enough (pauses or big pace changes) "
                                  "to compare fairly.")
        changes = []
    elif len(base) < 2:
        out["comparison_note"] = (f"{len(base)} comparable run(s) before the trial; at least 2 "
                                  "are needed.")
        changes = []
    else:
        changes = [c for c in (
            _change("avg_hr", m.get("avg_hr"), [b.get("avg_hr") for b in base], "bpm",
                    "lower"),
            _change("efficiency_factor", m.get("efficiency_factor"),
                    [b.get("efficiency_factor") for b in base], "", "higher"),
            _change("decoupling_pct", m.get("decoupling_pct"),
                    [b.get("decoupling_pct") for b in base], "%", "lower"),
            _change("cadence_spm", m.get("cadence_spm"), [b.get("cadence_spm") for b in base],
                    "steps/min", "neutral", 0),
            _change("step_length_m", m.get("step_length_m"),
                    [b.get("step_length_m") for b in base], "m", "neutral", 2),
        ) if c]
    out["changes"] = changes
    out["available"] = True
    out["summary"] = _sentence(out, target)
    return out


LABELS = {"avg_hr": "heart rate", "efficiency_factor": "speed per heartbeat",
          "decoupling_pct": "heart-rate drift", "cadence_spm": "cadence",
          "step_length_m": "stride length"}


def _sentence(a: dict[str, Any], target: int | None) -> str:
    parts = []
    did = a.get("did_it") or {}
    if did.get("available"):
        parts.append(f"{did['minutes_at_target']:g} of {did['moving_minutes']:g} minutes at "
                     f"or near {target} steps/min")
    feel = a.get("garmin_feel") or {}
    notes = a.get("your_notes") or {}
    if feel.get("felt"):
        parts.append(f"felt {feel['felt']}")
    if feel.get("effort_1_10"):
        parts.append(f"effort {feel['effort_1_10']}/10")
    if "knee_during" in notes:
        parts.append(f"knee {notes['knee_during']}/10 during")
    if "knee_next_morning" in notes:
        parts.append(f"{notes['knee_next_morning']}/10 next morning")
    moved = [c for c in a.get("changes", []) if c["verdict"] != "about the same"]
    if moved:
        bits = []
        for c in moved[:3]:
            if "change_pct" in c:
                bits.append(f"{LABELS[c['metric']]} {c['change_pct']:+g}%")
            else:
                bits.append(f"{LABELS[c['metric']]} {c['change']:+g} {c['unit']}".strip())
        parts.append("vs your comparable runs: " + ", ".join(bits))
    elif a.get("changes"):
        parts.append("heart rate and efficiency about the same as your comparable runs")
    return "; ".join(parts).capitalize() + "." if parts else "Nothing recorded yet."


def status(conn: sqlite3.Connection, trial_id: int | None = None, *,
           through: tuple[date, ZoneInfo] | None = None) -> dict[str, Any]:
    """The active (or given) trial, every attempt reviewed, and a plain verdict so far."""
    before = (datetime.combine(through[0] + timedelta(days=1), time.min, through[1])
              .astimezone(UTC).isoformat()) if through else None
    trial = _trial(conn, trial_id, before=before)
    if not trial:
        sug = None if through else suggested_cadence(conn)
        return {"active": False, "suggestion": (
            f"No experiment running. Suggested: cadence about {sug} steps/min in 1-minute "
            "blocks on easy runs (knee-friendly)." if sug else
            "No experiment running.")}
    runs = _attempt_runs(conn, trial, through_day=through[0].isoformat() if through else "9999-12-31",
                         zone=through[1] if through else None)
    attempts = [attempt_review(conn, trial, aid, before=before or "9999-12-31")
                for aid, _, _ in runs]
    done = [a for a in attempts if a.get("available")]
    return {"active": trial["status"] == "active", "trial": trial, "attempts": done,
            "verdict": _verdict(done), "next": _next(trial, done)}


def _verdict(attempts: list[dict[str, Any]]) -> str:
    if not attempts:
        return "No attempts yet."
    if len(attempts) < 3:
        return (f"Early: {len(attempts)} attempt(s). Keep going; after 3 comparable runs we "
                "can say whether anything changed beyond normal variation.")
    knees = [a["your_notes"]["knee_next_morning"] for a in attempts
             if "knee_next_morning" in a.get("your_notes", {})]
    eff = [c["change_pct"] for a in attempts for c in a.get("changes", [])
           if c["metric"] == "efficiency_factor"]
    bits = []
    if len(eff) >= 3:
        med = statistics.median(eff)
        bits.append("speed per heartbeat " + ("about the same" if abs(med) < 3 else
                                               f"{med:+.1f}% vs before"))
    else:
        bits.append(f"{len(eff)} comparable pace-and-pulse results so far")
    if knees:
        bits.append(f"knee next morning median {statistics.median(knees):g}/10")
    return (f"After {len(attempts)} attempts: " + "; ".join(bits) + "."
            if bits else f"{len(attempts)} attempts recorded.")


def _next(trial: dict[str, Any], attempts: list[dict[str, Any]]) -> str:
    if not attempts:
        return "Try it on your next easy run."
    last = attempts[-1]
    notes = last.get("your_notes", {})
    if notes.get("knee_next_morning", 0) >= 4 or notes.get("knee_during", 0) >= 4:
        return "Knee discomfort was reported. Stop the trial and rest; see a physio if it lasts."
    if "knee_next_morning" not in notes:
        return "Tell Claude how your knee felt the morning after your last run."
    if trial["target"].get("cadence_spm"):
        did = last.get("did_it", {})
        if did.get("available") and did["minutes_at_target"] < 3:
            return "Few minutes reached the target. Try 3–5 one-minute blocks next run."
    return "Repeat on your next easy run at the same pace."


def suggested_cadence(conn: sqlite3.Connection) -> int | None:
    """+5 % over the latest steady run's cadence (knee-load evidence: Heiderscheit 2011)."""
    from garmin_mcp.coaching import run_metrics
    from garmin_mcp.loads import RUN_TYPES

    marks = ",".join("?" * len(RUN_TYPES))
    for (aid,) in conn.execute(f"SELECT activity_id FROM activities WHERE type IN ({marks}) "
                               "AND fit_parsed=1 ORDER BY start_time_local DESC LIMIT 10",
                               RUN_TYPES):
        m = run_metrics(conn, aid)
        if m and m.get("steady") and m.get("cadence_spm"):
            return round(m["cadence_spm"] * 1.05)
    return None
