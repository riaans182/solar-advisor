# tests/conftest.py
from __future__ import annotations

from datetime import datetime
from typing import Any

from solar_advisor.domain.telemetry import Telemetry

_DEFAULTS: dict[str, float] = {
    "battery_soc": 64.0,
    "battery_power": 85,
    "battery_voltage": 50,
    "battery_current": 1.7,
    "pv_power": 106,
    "grid_power": 1140,
    "load_power": 1086,
    "load_power_essential": 1136,
    "grid_energy_in": 1000,
    "grid_energy_out": 0,
    "pv_energy": 0,
    "load_energy": 0,
    "battery_energy_in": 0,
    "battery_energy_out": 0,
    "month_to_date_grid_import_kwh": 12.5,
}


def make_telemetry(ts: datetime, **overrides: Any) -> Telemetry:
    """Build a Telemetry snapshot with sensible defaults, overriding any field."""
    return Telemetry(ts=ts, **{**_DEFAULTS, **overrides})
