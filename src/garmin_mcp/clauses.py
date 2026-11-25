"""Deterministic checks for one model-written clause about one recorded reading.

The local model review accepted reversed directions and swapped comparison periods in tests, so a
clause has to agree with what Python recorded before that review runs. Wording outside these lists
is rejected: a false rejection falls back to exact readings.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Claim:
    metric: str
    subject: str  # regex the clause has to name
    trend: str | None = None  # "up", "down" or "same"
    window: str | None = None  # key of PERIODS
    pace: str | None = None  # "faster", "slower" or "same", for the two-measure pacing reading

    @property
    def changed(self):
        return self.trend in {"up", "down"} or self.pace in {"faster", "slower"}


# Movements smaller than these read as "about the same". Design choices, listed in METRICS.md.
NOISE = {"sleep_h": 0.25, "sleep_min": 15, "resting_bpm": 2, "hrv_ms": 3, "shortfall_min": 15,
         "run_pulse_bpm": 3, "cadence_spm": 3, "decoupling_pct": 5}


# Plain wording for the drafter: measure, up/down direction words, the period the reading describes
# and the period it is compared with.
_WORDING = {
    ("runs", "blocks"): ("number of running days", "higher", "lower", "in the last four weeks",
                         "in the previous four weeks"),
    ("workouts", "blocks"): ("workout count", "higher", "lower", "this week", "the previous four weeks' average"),
    ("sleep", "week"): ("sleep per night", "longer", "shorter", "this week", "last week"),
    ("resting", "week"): ("resting heart rate", "higher", "lower", "this week", "last week"),
    ("hrv", "week"): ("heart rate variability", "higher", "lower", "this week", "last week"),
    ("shortfall", "week"): ("sleep shortfall", "larger", "smaller", "this week", "last week"),
    ("pulse", "runs"): ("moving heart rate", "higher", "lower", "on the latest run", "on earlier comparable runs"),
    ("cadence", "runs"): ("cadence", "higher", "lower", "on the latest run", "on earlier comparable runs"),
    ("cadence", "halves"): ("cadence", "higher", "lower", "late in the latest run", "early in that run"),
    ("pace", "halves"): ("pace and pulse", "higher", "lower", "in the second half", "in the first half"),
}
# For calendar periods the earlier one has to follow a comparison word. "Sleep was lower last week
# than the week before" would otherwise move this week's reading onto last week.
_AGAINST = (r"\b(?:than|compared\s+(?:to|with)|versus|vs\.?|against|from|as|to|below|above|match(?:es|ed))\s+"
            r"(?:(?:in|during|that\s+of)\s+)?(?:(?:the|its|your)\s+)?(?:recent\s+)?"
            r"(?:(?:weekly\s+)?(?:average|count|level)\s+(?:of|from|over|in|for)\s+(?:the\s+)?)?")
_CONTEXT = (r"\bat\s+(?:a\s+)?(?:similar|comparable|matched|the\s+same)\s+(?:pace|effort|grade)"
            r"(?:\s+and\s+(?:pace|grade|climbing))?")
# Order matters: each match is removed before the next period is searched, so
# "earlier comparable runs" is not also read as the early part of a run.
_WINDOWS = (
    ("context", _CONTEXT),
    ("runs", (r"\b(?:(?:earlier|previous|prior|past|other)\s+)?(?:comparable|similar|matched)\s+(?:runs?|efforts?)\b|"
             r"\b(?:earlier|previous|prior|past|other)\s+runs?\b")),
    ("blocks", (r"\b(?:(?:last|previous|prior|earlier|past)\s+)?(?:four|4)(?:[\s-]+(?:completed|full))?[\s-]+"
               r"weeks?(?:['’]s?)?(?:\s+before)?|\bfour\s+before\b|\b(?:previous|prior|earlier)\s+(?:period|block)\b|"
               r"\b(?:recent|weekly|four-week)\s+average\b|\bmonth\w*\b|\busual\b")),
    ("week", r"\b(?:last|previous|prior)\s+week(?:['’]s)?\b|\b(?:the\s+)?week\s+(?:before|earlier|prior)\b"),
    ("halves", (r"\b(?:first|second|early|late|earlier|later)(?:\s+(?:moving|part))?\s*(?:half|halves)?\b|"
               r"\bhalf\b|\bhalves\b")),
)
_WORDS = {
    "up": r"higher|larger|bigger|more|rose|rises?|risen|rising|increas\w*|above|up|climbed|longer|greater|gain\w*|improv\w*",
    "down": r"lower|smaller|fewer|less|fell|falls?|fallen|falling|decreas\w*|below|down|drop\w*|shorter|declin\w*|"
            r"reduc\w*|dipp?\w*|worse\w*",
    "same": r"same|similar|steady|unchanged|stable|within|held|level|consistent|remain\w*|stay\w*|flat|equal|match\w*",
}
# Doubled or mismatched comparison words passed every meaning check in live drafts.
_GARBLED = r"\bthan\s+(?:compared|as)\b|\bas\s+(?:than|compared|in\s+place)\b|\bin\s+place\s+of\b"
_NEVER = r"\b(?:load|volume|intensity|distance|mileage|quality|score|fitness|recovery|stress|effort level|trend\w*)\b"
_NEGATION = r"\b(?:not|no|never|without|neither|nor)\b|n['’]t\b"
_METRICS = {
    "pulse": r"\b(?:heart\s*rate|pulse|bpm)\b",
    "cadence": r"\bcadence\b|\bsteps?\b",
    "sleep": r"\bsle(?:ep|pt)\w*\b",
    "wake": r"\bw[ao]k(?:e|ing)\b",
    "resting": r"\bresting\b",
    "hrv": r"\bhrv\b|\bvariability\b",
    "shortfall": r"\bshortfall\b|\bmissed\b|\btargets?\b",
    "workouts": r"\b(?:workouts?|sessions?|training)\b",
    "runs": r"\b(?:run|running)\s+(?:days?|frequency|count)\b|\bruns?\b.*\b(?:days?|often)\b|"
            r"\bdays?\b.*\brun\w*\b|\bran\b|\bfrequency\b",
    "pace": r"\b(?:pace|faster|slower|quicker|speed\w*)\b",
}
# A clause may mention these beside its own metric.
_ALSO = {"pace": {"pulse"}, "wake": {"sleep"}, "resting": {"pulse"}, "hrv": {"pulse"},
         "shortfall": {"sleep"}}
_QUANTITY = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|"
    r"fifty|sixty|ninety|hundred|half|halves|quarters?|third|dozen|couple|an\s+hour|a\s+minute)\b", re.IGNORECASE)
_FRACTION = re.compile(r"\b(?:half|an)\s+an?\s+hour\b|\ban\s+hour\b|\bquarters?\b|\bdozen\b|\bcouple\b|"
                       r"\bhalf\s+(?:an?\s+)?(?:minute|day|week)\b", re.IGNORECASE)


def trend_of(change, noise=0):
    if change == 0 or abs(change) < noise:
        return "same"
    return "up" if change > 0 else "down"


def loose_amount(text: str, sources: str) -> bool:
    """A spelled-out fraction or amount that no cited reading contains."""
    return any(match[0].lower() not in sources.lower() for match in _FRACTION.finditer(text))


def uncited_quantity(text: str, source: str) -> bool:
    if loose_amount(text, source):
        return True
    known = {match[0].lower() for match in _QUANTITY.finditer(source)}
    return any(match[0].lower() not in known for match in _QUANTITY.finditer(text))


def guide(claim: Claim) -> dict:
    """What the drafter is told, in words, about one reading."""
    if not claim.window:
        return {"measure": claim.metric}
    measure, up, down, period, against = _WORDING[claim.metric, claim.window]
    word = {"up": up, "down": down, "same": "the same", None: None}[claim.trend]
    if claim.pace:
        word = f"pace {'the same' if claim.pace == 'same' else claim.pace}, pulse {word}"
    joiner = "as" if claim.trend == "same" and not claim.pace else "than"
    return {"measure": measure, "direction": word, "period": period, "ending": f"{joiner} {against}",
            "changed": claim.changed}


def check(text: str, claim: Claim) -> str | None:
    """Return a rejection reason, or None when the clause agrees with its reading."""
    plain = " ".join(text.lower().split())
    if re.search(_GARBLED, plain) or (claim.trend in {"up", "down"} and not claim.pace and re.search(
            r"\b(?:higher|lower|more|less|fewer|longer|shorter)\b(?:(?!\bthan\b|\bcompared\b).)*\bas\b", plain)):
        return "unsupported_wording"
    if re.search(_NEVER, plain):
        return "unsupported_claim"
    if re.search(_NEGATION, plain):
        return "wrong_comparison"
    # "At a similar pace" describes how runs were matched, not a second measurement.
    measured = re.sub(_CONTEXT, " ", plain)
    named = {name for name, pattern in _METRICS.items() if re.search(pattern, measured)}
    if not re.search(claim.subject, plain) or named - {claim.metric} - _ALSO.get(claim.metric, set()):
        return "wrong_comparison"
    if claim.window in {"week", "blocks"}:
        earlier = dict(_WINDOWS)[claim.window]
        if not re.search(f"{_AGAINST}(?:{earlier})", plain):
            return "wrong_comparison"
        if claim.window == "week" and len(re.findall(earlier, plain)) != 1:
            return "wrong_comparison"
    periods = set()
    for name, pattern in _WINDOWS:
        plain, count = re.subn(pattern, " ", plain)
        if count and name != "context":
            periods.add(name)
    # "late" and "early" can sit beside another period only for readings about halves.
    if periods - {claim.window} or (claim.trend and claim.window not in periods):
        return "wrong_comparison"
    found = {name for name, words in _WORDS.items() if re.search(rf"\b(?:{words})\b", plain)}
    if claim.pace:
        faster = bool(re.search(r"\b(?:faster|quicker|sped\s+up|speed\w*\s+up)\b", plain))
        slower = bool(re.search(r"\b(?:slower|slowed)\b", plain))
        if (faster, slower) != (claim.pace == "faster", claim.pace == "slower"):
            return "wrong_comparison"
        # Remaining direction words describe pulse.
        if found - {claim.trend} or (found and not re.search(_METRICS["pulse"], plain)):
            return "wrong_comparison"
    elif claim.trend is None:
        if found & {"up", "down"}:
            return "wrong_comparison"
    elif claim.trend == "same":
        if found != {"same"}:
            return "wrong_comparison"
    elif claim.trend not in found or found - {claim.trend, "same"}:
        return "wrong_comparison"
    return None
