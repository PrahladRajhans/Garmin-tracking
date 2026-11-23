"""Unofficial Garmin Connect source (python-garminconnect).

Richest source: covers Firstbeat metrics the official Personal API likely lacks (training
readiness/status, race predictor, endurance/hill score, lactate threshold, fitness age,
acclimation). Fragile by nature: Garmin can change auth or endpoints without notice, so the
sync engine treats every call as fallible.
"""

from __future__ import annotations

import io
import zipfile
from typing import Any

from garminconnect import Garmin

from garmin_mcp.sources.base import DataSource


class GarminConnectSource(DataSource):
    name = "garminconnect"

    def __init__(self, client: Garmin) -> None:
        super().__init__()
        c = client
        self.client = c
        # Per-day datasets. Everything the FR955 produces daily.
        self.daily = {
            "user_summary": c.get_user_summary,  # steps, calories, RHR, stress, BB, intensity
            "sleep": c.get_sleep_data,  # stages, score, SpO2/respiration during sleep
            "hrv": c.get_hrv_data,  # overnight RMSSD, 7d avg, baseline band, status
            "training_readiness": c.get_training_readiness,  # score + component factors
            "training_status": c.get_training_status,  # status, acute load, load focus, VO2max
            "stress": c.get_all_day_stress,  # stress + body battery timeline
            "heart_rate": c.get_heart_rates,  # all-day HR timeline, RHR
            "respiration": c.get_respiration_data,
            "spo2": c.get_spo2_data,
            "max_metrics": c.get_max_metrics,  # VO2max (run/cycle), fitness age inputs
            "fitness_age": c.get_fitnessage_data,
            "intensity_minutes": c.get_intensity_minutes_data,
            "hydration": c.get_hydration_data,
            "body_battery_events": c.get_body_battery_events,
            "acclimation": c.get_heat_altitude_acclimation,
            "floors": c.get_floors,
        }
        # Slow-moving metrics fetched over the sync window in one call.
        self.ranges = {
            "body_composition": c.get_body_composition,
            "race_predictions": lambda s, e: c.get_race_predictions(s, e, "daily"),
            "endurance_score": lambda s, e: c.get_endurance_score(s, e, "daily"),
            "hill_score": c.get_hill_score,
            "lactate_threshold": lambda s, e: c.get_lactate_threshold(
                latest=False, start_date=s, end_date=e
            ),
            "weigh_ins": c.get_weigh_ins,
        }
        self.activity_details = {
            "splits": lambda a: c.get_activity_splits(str(a)),
            "typed_splits": lambda a: c.get_activity_typed_splits(str(a)),
            "hr_zones": lambda a: c.get_activity_hr_in_timezones(str(a)),
            "power_zones": lambda a: c.get_activity_power_in_timezones(str(a)),
            "weather": lambda a: c.get_activity_weather(str(a)),
        }

    def list_activities(self, start: str, end: str) -> list[dict[str, Any]]:
        return self.client.get_activities_by_date(start, end) or []

    def download_fit(self, activity_id: int) -> bytes | None:
        data = self.client.download_activity(
            str(activity_id), dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL
        )
        return extract_fit(data)


def extract_fit(data: bytes | None) -> bytes | None:
    """Garmin's 'original' download is a zip containing the .fit file; accept raw .fit too."""
    if not data:
        return None
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".fit"):
                    return zf.read(name)
        return None
    return data
