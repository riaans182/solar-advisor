# src/solar_advisor/engine/inputs.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True, slots=True)
class SolarForecast:
    """Expected PV generation. Maps to HA Forecast.Solar today/tomorrow totals."""

    expected_pv_kwh_today: float
    expected_pv_kwh_tomorrow: float


@dataclass(frozen=True, slots=True)
class LoadProfile:
    """Consumption inputs. essential_power_w is the continuous backup-critical load
    (from load_power_essential history)."""

    daily_kwh: float
    essential_power_w: float


@dataclass(frozen=True, slots=True)
class DaylightWindow:
    """Window over which PV is assumed to generate, used to allocate forecast PV
    across schedule slots."""

    dawn: time
    dusk: time
