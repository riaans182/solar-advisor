# src/solar_advisor/ingest/topic_map.py
from __future__ import annotations

import math

# Deye / SolarAssistant telemetry topics → normalized field name.
# This dict is the entire vendor-specific surface for telemetry; a different
# inverter is a new map emitting the same field names (spec §3.1).
TELEMETRY_TOPICS: dict[str, str] = {
    "solar_assistant/total/battery_state_of_charge/state": "battery_soc",
    "solar_assistant/total/battery_power/state": "battery_power",
    "solar_assistant/inverter_1/battery_voltage/state": "battery_voltage",
    "solar_assistant/inverter_1/battery_current/state": "battery_current",
    "solar_assistant/inverter_1/pv_power/state": "pv_power",
    "solar_assistant/inverter_1/grid_power/state": "grid_power",
    "solar_assistant/inverter_1/load_power/state": "load_power",
    "solar_assistant/inverter_1/load_power_essential/state": "load_power_essential",
    "solar_assistant/total/grid_energy_in/state": "grid_energy_in",
    "solar_assistant/total/grid_energy_out/state": "grid_energy_out",
    "solar_assistant/total/pv_energy/state": "pv_energy",
    "solar_assistant/total/load_energy/state": "load_energy",
    "solar_assistant/total/battery_energy_in/state": "battery_energy_in",
    "solar_assistant/total/battery_energy_out/state": "battery_energy_out",
}


def parse_value(topic: str, payload: str) -> tuple[str, float] | None:
    """Map a telemetry topic+payload to (field_name, float). None if not telemetry."""
    field = TELEMETRY_TOPICS.get(topic)
    if field is None:
        return None
    try:
        result = float(payload)
    except ValueError:
        return None
    if not math.isfinite(result):
        return None
    return field, result
