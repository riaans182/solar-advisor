# src/solar_advisor/forecast/ha_provider.py
from __future__ import annotations

import httpx

from solar_advisor.engine.inputs import SolarForecast

_TODAY_ENTITY = "sensor.energy_production_today"
_TOMORROW_ENTITY = "sensor.energy_production_tomorrow"


class HomeAssistantForecastProvider:
    """Reads the existing Home Assistant Forecast.Solar sensors over HA's REST
    API, reusing the user's forecast feed rather than a second dependency (spec §9)."""

    def __init__(self, client: httpx.Client, token: str) -> None:
        self._client = client
        self._headers = {"Authorization": f"Bearer {token}"}

    def _read(self, entity: str) -> float:
        resp = self._client.get(f"/api/states/{entity}", headers=self._headers)
        resp.raise_for_status()
        return float(resp.json()["state"])

    def fetch(self) -> SolarForecast:
        return SolarForecast(
            expected_pv_kwh_today=self._read(_TODAY_ENTITY),
            expected_pv_kwh_tomorrow=self._read(_TOMORROW_ENTITY),
        )
