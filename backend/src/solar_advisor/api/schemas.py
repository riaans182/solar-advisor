# src/solar_advisor/api/schemas.py
from __future__ import annotations

from pydantic import BaseModel


class SlotView(BaseModel):
    start: str
    end: str
    target_soc: int
    grid_charge: bool
    behavior: str
    end_soc: float
    grid_import_kwh: float
    cost: float


class RecommendationView(BaseModel):
    reserve_target_soc: float
    enable_overnight_grid_charge: bool
    grid_charge_kwh: float
    expected_daily_grid_import_kwh: float
    expected_daily_cost: float
    backup_hours: float
    monthly_cost_so_far: float


class DashboardView(BaseModel):
    objective: float
    battery_soc: float
    pv_power: float
    grid_power: float
    load_power: float
    month_to_date_grid_import_kwh: float
    usable_kwh: float
    usable_kwh_confidence: float
    daily_consumption_kwh: float
    daily_consumption_confidence: float
    slots: list[SlotView]
    recommendation: RecommendationView
    disclaimer: str
