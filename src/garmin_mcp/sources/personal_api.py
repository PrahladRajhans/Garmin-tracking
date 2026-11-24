"""Official Garmin Personal API source, built on Garmin's own client
(`garmin-connect-personal-api-python`, Apache-2.0).

Auth: the Personal API key (created at connect.garmin.com/app/settings/personalApiToken) is
exchanged for a ~24 h bearer token, cached at ~/.config/garmin/. Key lookup order (Garmin's
client): GARMIN_PERSONAL_API_KEY env var, then ~/.config/garmin/connect-personal-api-key.

Coverage (verified against the official client v1.1.0): activities + original FIT, daily
summaries, sleep, HRV, all-day HR, SpO2, Body Battery, stress, steps, hydration, VO2max,
fitness age, weight, HR zones. NOT included: training readiness/status, race predictions,
endurance/hill score, lactate threshold, acclimation -> use the garminconnect source for those.

Undocumented history caps reported by implementers: steps/stress 28 d, hydration 31 d,
HRV/weight 365 d. Range datasets are therefore fetched in 28-day chunks.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from typing import Any

from garmin_mcp.sources.base import DataSource
from garmin_mcp.sources.garminconnect_source import extract_fit

MAX_ACTIVITY_PAGES = 1000


class PersonalAPISource(DataSource):
    name = "personal_api"
    range_chunk_days = 28

    def __init__(self, api_key: str | None = None, *, client: Any = None,
                 authenticator: Any = None) -> None:
        super().__init__()
        if client is None:
            from garmin_personal_api import (
                GarminPersonalApiClient,
                PersonalApiAuthenticator,
                resolve_api_key,
            )

            supplied = os.getenv("GARMIN_PERSONAL_API_KEY")
            env = {} if supplied is not None and not supplied.strip() else None
            self._key = resolve_api_key(api_key or None, env=env)
            self._auth = authenticator or PersonalApiAuthenticator()
            client = GarminPersonalApiClient(self._auth.obtain_token(self._key).access_token)
        else:
            self._key, self._auth = api_key, authenticator
        self.client = c = client

        self.daily = {
            "pa_daily_summary": lambda d: c.get_daily_summaries(d, d),
            "pa_sleep": c.get_daily_sleep,
            "pa_hrv": c.get_daily_hrv,
            "pa_heart_rate": c.get_daily_heart_rate,
            "pa_spo2": c.get_daily_spo2,
            "pa_fitness_age": c.get_fitness_age,
        }
        self.ranges = {
            "pa_body_battery": c.get_daily_body_battery,
            "pa_stress": c.get_daily_stress,
            "pa_steps": c.get_daily_steps,
            "pa_hydration": c.get_daily_hydration,
            "pa_vo2max": c.get_daily_vo2_max,
            "pa_weight": c.get_weight_measurements,
            "pa_hrv_summaries": c.get_daily_hrv_summaries,
            "pa_sleep_summaries": c.get_daily_sleep_summaries,
        }
        # Wrap everything so an expired token is renewed once and the call retried.
        self.daily = {k: self._retrying(f) for k, f in self.daily.items()}
        self.ranges = {k: self._retrying(f) for k, f in self.ranges.items()}
        self.activity_details = {
            "pa_activity": self._retrying(lambda a: c.get_activity(a)),
        }

    def _refresh_token(self) -> bool:
        if self._auth is None or not self._key:
            return False
        token = self._auth.obtain_token(self._key, force_refresh=True)
        self.client.update_bearer_token(token.access_token)
        return True

    def _retrying(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(*args: Any) -> Any:
            try:
                return fn(*args)
            except Exception as exc:
                if getattr(exc, "status_code", None) == 401 and self._refresh_token():
                    return fn(*args)
                raise

        return wrapped

    def list_activities(self, start: str, end: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        offset, page = 0, 100
        seen = set()
        for _ in range(MAX_ACTIVITY_PAGES):
            result = self._search(offset, page, start, end)
            if not result:
                break
            signature = hashlib.sha256(json.dumps(result, sort_keys=True, default=str).encode()).digest()
            if signature in seen:
                raise RuntimeError("Garmin returned a repeated activity page; pagination stopped.")
            seen.add(signature)
            items.extend(result)
            if len(result) < page:
                break
            offset += page
        else:
            raise RuntimeError("Garmin activity pagination exceeded its request limit; no "
                               "partial list was accepted.")
        return items

    def _search(self, offset: int, page: int, start: str, end: str) -> list[dict[str, Any]]:
        def call() -> Any:
            return self.client.search_activities(
                start=offset, limit=page, start_date=start, end_date=end
            )

        result = self._retrying(call)()
        if not isinstance(result, list):
            raise TypeError("Garmin activity search returned an unexpected response.")
        return result

    def download_fit(self, activity_id: int) -> bytes | None:
        return extract_fit(self._retrying(self.client.download_activity)(activity_id))
