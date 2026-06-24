# src/solar_advisor/forecast/static_provider.py
from __future__ import annotations

from dataclasses import dataclass

from solar_advisor.engine.inputs import SolarForecast


@dataclass(frozen=True, slots=True)
class StaticForecastProvider:
    """Config-driven forecast. The default until the HA feed is wired (spec §9)."""

    today_kwh: float
    tomorrow_kwh: float

    def fetch(self) -> SolarForecast:
        return SolarForecast(
            expected_pv_kwh_today=self.today_kwh,
            expected_pv_kwh_tomorrow=self.tomorrow_kwh,
        )
