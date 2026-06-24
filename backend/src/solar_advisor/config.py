from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time


def _parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Configuration the engine needs that does not come from the inverter
    (spec §2 ASK-ME) plus stable battery limits and the live-ingest connection."""

    # Tariff (ask-me)
    tariff_rate: float  # R/kWh (flat marginal)
    tariff_fixed_charge: float  # R/month (sunk)
    # Battery limits (stable; seeded from the discovered dump)
    battery_nominal_kwh: float
    battery_soc_floor_pct: float
    max_charge_power_w: float
    max_discharge_power_w: float
    # Load / daylight / objective
    essential_power_w: float
    daylight_dawn: time
    daylight_dusk: time
    objective_default: float
    # MQTT (reuse the collector's env)
    mqtt_host: str
    mqtt_port: int
    mqtt_user: str | None
    mqtt_pass: str | None
    db_path: str
    # Forecast (static fallback values, kWh)
    forecast_today_kwh: float
    forecast_tomorrow_kwh: float


def load_config() -> AppConfig:
    o = float(os.environ.get("SA_OBJECTIVE_DEFAULT", "0.5"))
    return AppConfig(
        tariff_rate=float(os.environ.get("SA_TARIFF_RATE", "3.56")),
        tariff_fixed_charge=float(os.environ.get("SA_TARIFF_FIXED_CHARGE", "600")),
        battery_nominal_kwh=float(os.environ.get("SA_BATTERY_NOMINAL_KWH", "15")),
        battery_soc_floor_pct=float(os.environ.get("SA_BATTERY_SOC_FLOOR_PCT", "20")),
        max_charge_power_w=float(os.environ.get("SA_MAX_CHARGE_POWER_W", "7950")),
        max_discharge_power_w=float(os.environ.get("SA_MAX_DISCHARGE_POWER_W", "7950")),
        essential_power_w=float(os.environ.get("SA_ESSENTIAL_POWER_W", "1136")),
        daylight_dawn=_parse_hhmm(os.environ.get("SA_DAYLIGHT_DAWN", "07:00")),
        daylight_dusk=_parse_hhmm(os.environ.get("SA_DAYLIGHT_DUSK", "17:30")),
        objective_default=min(1.0, max(0.0, o)),
        mqtt_host=os.environ.get("SA_MQTT_HOST", "localhost"),
        mqtt_port=int(os.environ.get("SA_MQTT_PORT", "1883")),
        mqtt_user=os.environ.get("SA_MQTT_USER") or None,
        mqtt_pass=os.environ.get("SA_MQTT_PASS") or None,
        db_path=os.environ.get("SA_DB_PATH", "solar_advisor.db"),
        forecast_today_kwh=float(os.environ.get("SA_FORECAST_TODAY_KWH", "20")),
        forecast_tomorrow_kwh=float(os.environ.get("SA_FORECAST_TOMORROW_KWH", "20")),
    )
