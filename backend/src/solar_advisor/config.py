from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import time

from solar_advisor.forecast.forecast_solar_provider import PvArray


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
    daily_consumption_kwh: float = 24.0  # fallback when the estimator's confidence is 0
    tariff_window_days: int = 90  # trailing window for the data-derived marginal rate
    forecast_source: str = "static"  # "static" | "forecast_solar"
    lat: float = -33.92
    lon: float = 18.42
    forecast_ttl_s: float = 10800.0  # 3h cache for the Forecast.Solar call
    pv_arrays: tuple[PvArray, ...] = ()
    timezone: str = "Africa/Johannesburg"  # local day used for the PV forecast's today/tomorrow
    telemetry_retention_days: int = 90  # collector prunes telemetry rows older than this
    # Explain layer (Plan D)
    explain_model: str = "claude-haiku-4-5"
    explain_enabled: bool = True
    explain_min_interval_s: float = 10.0
    explain_max_tokens: int = 2048


_DEFAULT_PV_ARRAYS: tuple[PvArray, ...] = (
    PvArray(tilt=26.0, azimuth=-135.0, kwp=2.5),  # 5 panels NE
    PvArray(tilt=26.0, azimuth=45.0, kwp=2.5),  # 5 panels SW
)


def _parse_pv_arrays(raw: str | None) -> tuple[PvArray, ...]:
    if not raw:
        return _DEFAULT_PV_ARRAYS
    try:
        items = json.loads(raw)
        parsed = tuple(
            PvArray(tilt=float(i["tilt"]), azimuth=float(i["azimuth"]), kwp=float(i["kwp"]))
            for i in items
        )
        return parsed or _DEFAULT_PV_ARRAYS
    except (ValueError, TypeError, KeyError):
        return _DEFAULT_PV_ARRAYS


def load_config() -> AppConfig:
    o = float(os.environ.get("SA_OBJECTIVE_DEFAULT", "0.5"))
    retention_days = int(os.environ.get("SA_TELEMETRY_RETENTION_DAYS", "90"))
    if retention_days < 1:
        raise ValueError(
            f"SA_TELEMETRY_RETENTION_DAYS must be >= 1 (got {retention_days}); "
            "refusing to start to avoid deleting telemetry."
        )
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
        daily_consumption_kwh=float(os.environ.get("SA_DAILY_CONSUMPTION_KWH", "24")),
        tariff_window_days=int(os.environ.get("SA_TARIFF_WINDOW_DAYS", "90")),
        forecast_source=os.environ.get("SA_FORECAST_SOURCE", "static"),
        lat=float(os.environ.get("SA_LAT", "-33.92")),
        lon=float(os.environ.get("SA_LON", "18.42")),
        forecast_ttl_s=float(os.environ.get("SA_FORECAST_TTL_S", "10800")),
        pv_arrays=_parse_pv_arrays(os.environ.get("SA_PV_ARRAYS")),
        timezone=os.environ.get("SA_TIMEZONE", "Africa/Johannesburg"),
        telemetry_retention_days=retention_days,
        explain_model=os.environ.get("SA_EXPLAIN_MODEL", "claude-haiku-4-5"),
        explain_enabled=os.environ.get("SA_EXPLAIN_ENABLED", "true").strip().lower() != "false",
        explain_min_interval_s=float(os.environ.get("SA_EXPLAIN_MIN_INTERVAL_S", "10")),
        explain_max_tokens=int(os.environ.get("SA_EXPLAIN_MAX_TOKENS", "2048")),
    )
