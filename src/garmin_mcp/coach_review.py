"""Track published guidance and connect workout evidence to the next decision."""

import json

_KEY = "dashboard_guidance"


def guidance(conn, day, focus, *, save=False):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (_KEY,)).fetchone()
    state = json.loads(row[0]) if row else {}
    before = dict(state)
    current = state.get("current")
    latest = {"day": day, "title": focus["title"]}
    if current and current["day"] > day:
        return None
    if current and current["title"] != latest["title"]:
        state["previous"] = current
    elif current and current["day"] != day:
        state.pop("previous", None)
    state["current"] = latest
    if save and state != before:
        with conn:
            conn.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (_KEY, json.dumps(state)))
    previous = state.get("previous")
    if not previous:
        return None
    return {"previous": previous}


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
