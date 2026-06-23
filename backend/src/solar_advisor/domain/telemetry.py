# src/solar_advisor/domain/telemetry.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Telemetry:
    """Vendor-neutral snapshot of inverter state at a point in time.

    Power in watts (grid_power/battery_power signed: + = import/charge).
    Energy fields are lifetime-cumulative kWh as reported by the inverter.
    """

    ts: datetime
    battery_soc: float            # %
    battery_power: float          # W (+ charging)
    battery_voltage: float        # V
    battery_current: float        # A
    pv_power: float               # W
    grid_power: float             # W (+ import)
    load_power: float             # W
    load_power_essential: float   # W
    grid_energy_in: float         # kWh cumulative
    grid_energy_out: float        # kWh cumulative
    pv_energy: float              # kWh cumulative
    load_energy: float            # kWh cumulative
    battery_energy_in: float      # kWh cumulative
    battery_energy_out: float     # kWh cumulative
    month_to_date_grid_import_kwh: float  # derived (Task 6)
