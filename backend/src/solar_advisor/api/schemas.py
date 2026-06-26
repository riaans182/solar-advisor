# src/solar_advisor/api/schemas.py
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator


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


class ExplanationView(BaseModel):
    explanation: str
    generated: bool
    guard_ok: bool
    unverified_numbers: list[float]
    disclaimer: str


class HistoryPoint(BaseModel):
    ts: str
    battery_soc: float
    pv_power: float
    grid_power: float
    load_power: float
    battery_power: float


class HistoryView(BaseModel):
    points: list[HistoryPoint]


class DashboardView(BaseModel):
    objective: float
    battery_soc: float
    pv_power: float
    grid_power: float
    load_power: float
    battery_power: float
    conversion_power: float
    month_to_date_grid_import_kwh: float
    usable_kwh: float
    usable_kwh_confidence: float
    daily_consumption_kwh: float
    daily_consumption_confidence: float
    tariff_rate: float
    tariff_source: str
    tariff_source_date: str | None
    expected_pv_kwh_today: float
    expected_pv_kwh_tomorrow: float
    month_spend: float
    month_remaining_cost: float
    recommended_slots: list[SlotView]
    current_daily_cost: float
    recommended_daily_cost: float
    daily_saving: float
    slots: list[SlotView]
    recommendation: RecommendationView
    disclaimer: str


class PurchaseCreate(BaseModel):
    purchased_at: date
    rand: float = Field(gt=0)
    units_kwh: float = Field(gt=0)
    note: str | None = None

    @field_validator("purchased_at")
    @classmethod
    def _not_in_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("purchased_at cannot be in the future")
        return v


class PurchaseView(BaseModel):
    id: int
    purchased_at: str
    rand: float
    units_kwh: float
    note: str | None
    effective_rate: float


class PurchaseListView(BaseModel):
    purchases: list[PurchaseView]
