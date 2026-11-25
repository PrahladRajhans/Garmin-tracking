"""Turn recorded changes into one practical focus and a short list of follow-ups."""

from __future__ import annotations

from collections.abc import Sequence
from statistics import fmean
from typing import Any


def _weekly_change(signal: dict, direction: str, minimum: float,
                   multiplier: float = 1) -> int | None:
    """Return a rounded week-over-week change only when it also leaves the usual range."""
    delta = signal.get("delta")
    if signal.get("state") != direction or delta is None:
        return None
    signed = delta if direction == "above" else -delta
    change = round(signed * multiplier)
    return change if change >= minimum else None


def daily_focus(readiness: dict, signals: dict, suggestion: dict, *,
                training_status: str | None = None, running_km: float = 0,
                patterns: Sequence[dict] = ()) -> dict[str, Any]:
    """Offer a conservative adjustment only when the personal evidence agrees."""
    pulse = _weekly_change(signals["resting_hr"], "above", 1)
    sleep = _weekly_change(signals["sleep_h"], "below", 10, 60)
    hrv = readiness["hrv"].get("state") == "below normal"
    pulse_text = f"Your resting heart rate averaged {pulse} bpm higher than the week before." if pulse else ""
    sleep_text = f"You slept about {sleep} minutes less per night than the week before." if sleep else ""
    findings = []
    nights = readiness.get("sleep", {}).get("debt_inputs", [])
    if len(nights) >= 4:
        hours = fmean(n["sleep_h"] for n in nights)
        goal = fmean(n["need_h"] for n in nights)
        if goal - hours >= 0.5:
            sources = {n["source"] for n in nights}
            source = "Garmin’s targets" if sources == {"Garmin sleep need"} else (
                "the 8-hour planning target" if len(sources) == 1 else
                "Garmin’s targets and an 8-hour estimate on nights without one")
            findings.append({
                "title": "Make room for more sleep",
                "detail": f"You averaged {hours:.1f} hours, about {round((goal-hours)*60)} minutes "
                          "short of your nightly goal.",
                "action": "Try starting your bedtime routine 30 minutes earlier tonight.",
                "basis": f"{len(nights)} recorded nights in the last seven days, compared with {source}.",
                "target": "sleep",
            })
    if not findings and sleep:
        findings.append({"title": "Your sleep was shorter this week", "detail": sleep_text,
                         "action": "Check whether bedtime moved or your alarm got earlier.",
                         "basis": "Two separate seven-day windows.", "target": "sleep"})
    pair = next((p for p in patterns if p["x"] == "sleep_h" and p["y"] == "garmin_readiness"
                 and p["notable"] and p["lag_days"] == 0 and p["slope"] >= 1), None)
    if pair:
        text = (f'In your records, an extra hour of sleep went with about {round(pair["slope"])} '
                "more points on Garmin’s readiness score.")
        if findings:
            findings[0]["basis"] += f' {text} Based on {pair["n"]} paired days. Compare in Patterns.'
        else:
            findings.append({"title": "Sleep and readiness moved together", "detail": text,
                             "action": "Compare several nights of longer sleep.",
                             "basis": f'{pair["n"]} paired days. This is a pattern in your records.',
                             "target": "patterns"})
    if training_status and training_status.upper() == "DETRAINING":
        findings.append({"title": "Build consistency before adding intensity",
                         "detail": f'Garmin says Detraining. You logged {running_km:g} km '
                                   "of running in the past seven days.",
                         "action": "Use the next-seven-days plan as a starting point.",
                         "basis": "Garmin’s status and your recorded workouts.", "target": "training"})
    if pulse:
        findings.append({"title": "Your resting heart rate was higher", "detail": pulse_text,
                         "action": "See how you feel on your next easy session.",
                         "basis": "Two separate seven-day windows and your usual range.",
                         "target": "recovery"})
    oxygen = signals["sleep_spo2"]
    if oxygen.get("state") == "below":
        findings.append({"title": "Overnight Pulse Ox was below your usual range",
                         "detail": "Check your watch fit tonight and see if it happens again.",
                         "basis": "At least four nights and your personal range.",
                         "target": "recovery"})

    state = readiness["ours"]["state"]
    status = readiness.get("activity_status")
    level = (readiness.get("garmin") or {}).get("level")
    rough_day = readiness["illness_flag"]["raised"] or state == "well below usual"
    focus = {"title": "Follow your planned effort if you feel well.",
             "detail": "", "target": "training", "findings": findings,
             "evidence_keys": ("score",)}
    if status:
        focus.update(title="Pause training today.",
                     detail=f"You marked today as {status}. See how you feel before resuming.",
                     target=None, evidence_keys=("activity_status",))
    elif rough_day or level == "POOR":
        detail = ("Several recovery readings have shifted." if readiness["illness_flag"]["raised"]
                  else "Garmin marked readiness Poor today." if level == "POOR"
                  else "Today’s recovery score is low.")
        drivers = ("illness",) if readiness["illness_flag"]["raised"] else (
            ("garmin",) if level == "POOR" else ("score",))
        focus.update(title="Rest today or choose very easy movement.", detail=detail,
                     target="recovery", evidence_keys=drivers)
    elif pulse and (sleep or hrv):
        second = ("You also slept less." if sleep else "Your heart rate variability is also below usual.")
        focus.update(title="Keep today’s effort easy.", detail=f"{pulse_text} {second}",
                     target="recovery", evidence_keys=("pulse_week", "sleep_week" if sleep else "hrv_week"))
        # The lead already explains these readings. Keep a linked sleep follow-up if useful.
        focus["findings"] = [item for item in findings if item["title"] !=
                             "Your resting heart rate was higher"]
    elif state == "below usual" or level == "LOW":
        focus.update(title="Keep today’s effort easy.", detail=pulse_text or sleep_text
                     or ("Garmin marked readiness Low today." if level == "LOW"
                         else "Today’s recovery is below your usual level."), target="recovery",
                     evidence_keys=((("pulse_week",) if pulse_text else ("sleep_week",) if sleep_text else ())
                                    + (("score",) if state == "below usual" else ("garmin",))))
    elif state == "calibrating":
        focus.update(title="Start gently if you feel well.",
                     detail="There aren’t enough recent readings for a recovery score yet.",
                     target="recovery")
    elif pulse or sleep:
        focus.update(detail=pulse_text or sleep_text, target="recovery" if pulse else "sleep",
                     evidence_keys=("pulse_week" if pulse else "sleep_week",))
    elif suggestion.get("suggest") == "follow your planned session if you feel well":
        focus.update(detail="Both your Garmin reading and your recovery score support your plan.",
                     evidence_keys=("garmin", "score"))
    focus["findings"] = focus["findings"][:3]
    return focus
