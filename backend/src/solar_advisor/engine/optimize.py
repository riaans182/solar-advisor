# src/solar_advisor/engine/optimize.py
from __future__ import annotations

from dataclasses import dataclass

from solar_advisor.engine.battery import BatteryModel
from solar_advisor.engine.inputs import LoadProfile, SolarForecast
from solar_advisor.engine.objective import reserve_target_soc
from solar_advisor.engine.tariff import TariffModel


@dataclass(frozen=True, slots=True)
class Recommendation:
    reserve_target_soc: float  # % backup reserve the policy targets
    enable_overnight_grid_charge: bool
    grid_charge_kwh: float  # grid energy needed to reach the reserve (0 if solar suffices)
    expected_daily_grid_import_kwh: float  # load deficit + grid charge
    expected_daily_cost: float  # marginal cost of the day's grid import
    backup_hours: float  # how long the reserve powers the essential load
    monthly_cost_so_far: float  # fixed charge + month-to-date import (bill projection)


def recommend(
    *,
    battery: BatteryModel,
    tariff: TariffModel,
    forecast: SolarForecast,
    load: LoadProfile,
    objective: float,
    current_soc: float,
    month_to_date_import_kwh: float,
    days_in_month: int,
) -> Recommendation:
    """Daily energy-balance policy. With a flat tariff and no cheap window,
    self-consumption minimises the bill; grid-charging is pure cost justified only
    by the resilience reserve the objective scalar asks for (spec §5.4)."""
    reserve_soc = reserve_target_soc(objective, battery.soc_floor_pct)
    reserve_kwh = battery.soc_to_kwh(reserve_soc)

    expected_pv = forecast.expected_pv_kwh_today
    load_deficit = max(0.0, load.daily_kwh - expected_pv)

    current_kwh = battery.soc_to_kwh(current_soc)
    solar_surplus = max(0.0, expected_pv - load.daily_kwh)
    projected_kwh = min(battery.usable_kwh, current_kwh + solar_surplus)
    grid_charge_kwh = max(0.0, reserve_kwh - projected_kwh)

    daily_import = load_deficit + grid_charge_kwh
    rate = tariff.marginal_rate(month_to_date_import_kwh)
    backup_hours = (
        reserve_kwh * 1000.0 / load.essential_power_w if load.essential_power_w > 0 else 0.0
    )

    return Recommendation(
        reserve_target_soc=reserve_soc,
        enable_overnight_grid_charge=grid_charge_kwh > 0,
        grid_charge_kwh=grid_charge_kwh,
        expected_daily_grid_import_kwh=daily_import,
        expected_daily_cost=daily_import * rate,
        backup_hours=backup_hours,
        monthly_cost_so_far=tariff.monthly_cost(month_to_date_import_kwh, days_in_month),
    )
