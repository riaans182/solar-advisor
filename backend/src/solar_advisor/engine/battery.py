# src/solar_advisor/engine/battery.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BatteryModel:
    """Energy model of the battery. SOC is a percentage; energy in kWh.
    No charge/discharge efficiency or temperature derating in the MVP model."""

    usable_kwh: float
    soc_floor_pct: float
    max_charge_power_w: float
    max_discharge_power_w: float

    def soc_to_kwh(self, soc_pct: float) -> float:
        return self.usable_kwh * soc_pct / 100.0

    def energy_between(self, soc_lo_pct: float, soc_hi_pct: float) -> float:
        """Signed energy delta between two SOC levels: positive when
        soc_hi_pct > soc_lo_pct; negative means a discharge."""
        return self.usable_kwh * (soc_hi_pct - soc_lo_pct) / 100.0

    @property
    def floor_kwh(self) -> float:
        return self.soc_to_kwh(self.soc_floor_pct)
