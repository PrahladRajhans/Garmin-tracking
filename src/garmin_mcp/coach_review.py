"""Track published guidance and connect workout evidence to the next decision."""

import json
from datetime import date, timedelta

_KEY = "dashboard_guidance"


def decision_evidence(day, brief, signals):
    """Capture only inputs consulted by the published guidance rule."""
    output = []
    end = date.fromisoformat(day)
    current = f"{end - timedelta(days=6):%d %b}–{end:%d %b}"
    previous = f"{end - timedelta(days=13):%d %b}–{end - timedelta(days=7):%d %b}"
    for key in brief["focus"].get("evidence_keys", ()):
        if key in {"pulse_week", "sleep_week"}:
            stat = signals["resting_hr" if key == "pulse_week" else "sleep_h"]
            unit = stat["unit"]
            detail = (f'{stat["recent"]:.1f} {unit} from {stat["recent_count"]} readings ({current}) '
                      f'vs {stat["previous"]:.1f} {unit} from {stat["previous_count"]} ({previous}).')
            output.append({"label": stat["label"], "detail": detail})
        elif key == "score":
            score = brief["readiness"]["ours"]
            usable = [c["name"] for c in score["components"] if c["contribution"] is not None]
            detail = ", ".join(usable) or "No measure has enough baseline coverage."
            output.append({"label": f'Recovery · {score["state"]}', "detail": detail})
        elif key == "garmin":
            level = (brief["readiness"]["garmin"] or {}).get("level")
            if level:
                output.append({"label": "Garmin readiness", "detail": f"{level.title()} on {day}."})
        elif key == "hrv_week":
            output.append({"label": "Overnight HRV", "detail": f"Seven-day HRV is below usual ({current})."})
        elif key == "illness":
            changes = brief.get("illness_details", {}).get("days", ())
            output.extend({"label": r["day"], "detail": ", ".join(r["signals"])} for r in changes if r["signals"])
        elif key in {"knee_checkin", "activity_status"}:
            output.append({"label": "Your check-in" if key == "knee_checkin" else "Your activity status",
                           "detail": brief["focus"]["detail"]})
    return output


def guidance(conn, day, focus, *, evidence=(), save=False):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (_KEY,)).fetchone()
    state = json.loads(row[0]) if row else {}
    before = dict(state)
    current = state.get("current")
    latest = {"day": day, "title": focus["title"], "detail": focus.get("detail", ""),
              "target": focus.get("target"), "evidence": list(evidence)}
    if current and current["day"] > day:
        return None
    changed = current and (current["title"] != latest["title"] or
                           ("detail" in current and current["detail"] != latest["detail"]))
    if changed:
        state["previous"] = current
    elif current and current["day"] != day:
        state.pop("previous", None)
    state["current"] = latest
    if save and state != before:
        history = state.get("history", [])
        if changed or not current or current["day"] != day:
            state["history"] = [*history[-27:], latest]
        elif history and history[-1]["day"] == day:
            state["history"] = [*history[:-1], latest]
        with conn:
            conn.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (_KEY, json.dumps(state)))
    previous = state.get("previous")
    return {"previous": previous, "current": latest} if previous else None


def after_run(comparison):
    if not comparison["available"]:
        return None
    low, high = comparison["observed_hr_range_bpm"]
    heart_rate = comparison["this_run"]["avg_hr_bpm"]
    if low <= heart_rate <= high:
        return "This comparison alone gives no reason to change your next session."
    return ("On another comparable easy run, check whether the difference repeats. "
            "Use today’s guidance to choose the next session.")


def run_questions(run):
    """Eligible explanations to investigate when a matched result lies outside its range."""
    comparison = run.get("comparable_effort", {})
    if not comparison.get("available"):
        return ()
    low, high = comparison["observed_hr_range_bpm"]
    hr = comparison["this_run"]["avg_hr_bpm"]
    if low <= hr <= high:
        return ()
    choices = [
        {"title": "Repeat a comparable easy run",
         "basis": "One result outside the earlier span does not establish a trend."},
        {"title": "Check watch fit before the next comparison",
         "basis": "Wrist heart rate can be affected by the fit of the watch."},
    ]
    if run.get("conditions_comparison"):
        choices.append({"title": "Check the recorded conditions",
                        "basis": "Comparable pace and climb do not control for weather."})
    return tuple(choices)
