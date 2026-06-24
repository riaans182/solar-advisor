# src/solar_advisor/forecast/provider.py
from __future__ import annotations

from typing import Protocol, runtime_checkable

from solar_advisor.engine.inputs import SolarForecast


@runtime_checkable
class ForecastProvider(Protocol):
    """Fetches a solar forecast. The concrete HA Forecast.Solar adapter lands in
    Plan C; the engine consumes the returned SolarForecast value (spec §9)."""

    def fetch(self) -> SolarForecast: ...
