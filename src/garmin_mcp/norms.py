"""FRIEND 2015 treadmill CPX reference: exact Table 3 FRIEND rows, no interpolation.

Kaminsky, Arena, Myers. Mayo Clin Proc 90(11):1515–1523. DOI 10.1016/j.mayocp.2015.07.026.
Values are population reference points, not personal targets or validation of wearable estimates.
"""

from __future__ import annotations

import math
import sqlite3
from typing import Any

from garmin_mcp import loads

SOURCE = "https://pmc.ncbi.nlm.nih.gov/articles/PMC4919021/#T3"
PERCENTILES = (5, 10, 25, 50, 75, 90, 95)
FRIEND = {
    "male": {
        20: (29.0, 32.1, 40.1, 48.0, 55.2, 61.8, 66.3),
        30: (27.2, 30.2, 35.9, 42.4, 49.2, 56.5, 59.8),
        40: (24.2, 26.8, 31.9, 37.8, 45.0, 52.1, 55.6),
        50: (20.9, 22.8, 27.1, 32.6, 39.7, 45.6, 50.7),
        60: (17.4, 19.8, 23.7, 28.2, 34.5, 40.3, 43.0),
        70: (16.3, 17.1, 20.4, 24.4, 30.4, 36.6, 39.7),
    },
    "female": {
        20: (21.7, 23.9, 30.5, 37.6, 44.7, 51.3, 56.0),
        30: (19.0, 20.9, 25.3, 30.2, 36.1, 41.4, 45.8),
        40: (17.0, 18.8, 22.1, 26.7, 32.4, 38.4, 41.7),
        50: (16.0, 17.3, 19.9, 23.4, 27.6, 32.0, 35.9),
        60: (13.4, 14.6, 17.2, 20.0, 23.8, 27.0, 29.4),
        70: (13.1, 13.6, 15.6, 18.3, 20.8, 23.1, 24.1),
    },
}


def reference(age: float | None, sex: str | None) -> dict[str, Any]:
    if (not isinstance(age, (int, float)) or not math.isfinite(age)
            or not 20 <= age < 80 or sex not in FRIEND):
        return {"available": False,
                "reason": "FRIEND reference needs a recorded age 20–79 and male/female sex; "
                          "no age or sex is assumed"}
    decade = int(age // 10) * 10
    return {"available": True, "age_group": f"{decade}–{decade + 9}", "sex": sex,
            "values": dict(zip(PERCENTILES, FRIEND[sex][decade], strict=True)),
            "unit": "mL/kg/min", "source": SOURCE,
            "cohort": "FRIEND 2015 US treadmill CPX reference, without cardiovascular disease"}


def comparison(conn: sqlite3.Connection, end: str) -> dict[str, Any]:
    age = conn.execute("SELECT chronological_age FROM fitness_age WHERE day<=? AND "
                       "chronological_age IS NOT NULL ORDER BY day DESC LIMIT 1", (end,)).fetchone()
    sex = conn.execute("SELECT p.gender FROM fit_profile p JOIN activities a USING(activity_id) "
                       "WHERE substr(a.start_time_local,1,10)<=? AND p.gender IN ('male','female') "
                       "ORDER BY a.start_time_local DESC LIMIT 1", (end,)).fetchone()
    ref = reference(age[0] if age else None, sex[0] if sex else None)
    garmin = conn.execute("SELECT vo2max_run,day FROM training WHERE day<=? AND vo2max_run>0 "
                          "ORDER BY day DESC LIMIT 1", (end,)).fetchone()
    th = loads.thresholds(conn, end)
    eff = loads.effective_vo2max(conn, end, th["hr_max"], 180) if th["hr_max"] else {}
    def positive(value):
        return value if isinstance(value, (int, float)) and math.isfinite(value) and value > 0 else None

    return {**ref, "garmin": positive(garmin[0]) if garmin else None,
            "garmin_as_of": garmin[1] if garmin else None, "effective": positive(eff.get("value")),
            "effective_runs": eff.get("runs", 0), "hr_max": th["hr_max"],
            "hr_max_user_override": "hr_max" in th.get("overrides", {}),
            "caveat": "Garmin and effective VO2max are separate estimates, not laboratory "
                      "measurements. The effective pace/HR estimate is not physiologically "
                      "equivalent to measured VO2max. This US reference may not represent you."}
