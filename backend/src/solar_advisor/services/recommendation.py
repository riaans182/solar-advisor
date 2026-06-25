# src/solar_advisor/services/recommendation.py
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol

from solar_advisor.config import AppConfig
from solar_advisor.domain.telemetry import Telemetry
from solar_advisor.engine.battery import BatteryModel
from solar_advisor.engine.inputs import DaylightWindow, LoadProfile
from solar_advisor.engine.optimize import Recommendation, recommend
from solar_advisor.engine.schedule_eval import SlotAssessment, assess_schedule
from solar_advisor.engine.tariff import FlatRateTariff
from solar_advisor.estimation.estimator import EstimatedParameters
from solar_advisor.forecast.provider import ForecastProvider
from solar_advisor.ingest.live import LiveState
from solar_advisor.tariff.derivation import DerivedRate
from solar_advisor.tariff.provider import TariffProvider

ADVISORY_DISCLAIMER = (
    "Advisory only. This app is read-only against your inverter; apply any changes yourself."
)


@dataclass(frozen=True, slots=True)
class DashboardData:
    """Everything the dashboard (and, in Plan D, the LLM) needs — all numbers
    computed by the deterministic engine."""

    telemetry: Telemetry
    objective: float
    slot_assessments: list[SlotAssessment]
    recommendation: Recommendation
    usable_kwh: float
    usable_kwh_confidence: float
    daily_consumption_kwh: float
    daily_consumption_confidence: float
    tariff_rate: float
    tariff_source: str
    tariff_source_date: date | None
    expected_pv_kwh_today: float
    expected_pv_kwh_tomorrow: float
    disclaimer: str


class _Estimator(Protocol):  # structural protocol for the estimator dependency
    def estimate(self, start: datetime, end: datetime) -> EstimatedParameters: ...


class RecommendationService:
    """Assembles engine inputs from live data + estimates + forecast + config,
    then runs the pure engine."""

    def __init__(
        self,
        config: AppConfig,
        estimator: _Estimator,
        forecast: ForecastProvider,
        tariff_provider: TariffProvider | None = None,
    ) -> None:
        self._config = config
        self._estimator = estimator
        self._forecast = forecast
        self._tariff_provider = tariff_provider

    def build(self, state: LiveState, objective: float | None) -> DashboardData:
        if state.telemetry is None or state.schedule is None:
            raise LookupError("live state not ready: telemetry or schedule missing")

        cfg = self._config
        obj = cfg.objective_default if objective is None else min(1.0, max(0.0, objective))
        telemetry = state.telemetry

        est = self._estimator.estimate(telemetry.ts - timedelta(days=14), telemetry.ts)
        usable_kwh = est.usable_kwh or cfg.battery_nominal_kwh
        daily_kwh = (
            est.daily_consumption_kwh
            if est.daily_consumption_confidence > 0
            else cfg.daily_consumption_kwh
        )

        battery = BatteryModel(
            usable_kwh=usable_kwh,
            soc_floor_pct=cfg.battery_soc_floor_pct,
            max_charge_power_w=cfg.max_charge_power_w,
            max_discharge_power_w=cfg.max_discharge_power_w,
        )
        if self._tariff_provider is not None:
            derived = self._tariff_provider.current_rate(telemetry.ts.date())
        else:
            derived = DerivedRate(rate=cfg.tariff_rate, source="config", source_date=None)
        tariff = FlatRateTariff(
            energy_rate=derived.rate, monthly_fixed_charge=cfg.tariff_fixed_charge
        )
        forecast = self._forecast.fetch()
        load = LoadProfile(daily_kwh=daily_kwh, essential_power_w=cfg.essential_power_w)
        daylight = DaylightWindow(dawn=cfg.daylight_dawn, dusk=cfg.daylight_dusk)

        assessments = assess_schedule(
            state.schedule,
            battery,
            tariff,
            forecast,
            load,
            daylight,
            start_soc=telemetry.battery_soc,
            month_to_date_import_kwh=telemetry.month_to_date_grid_import_kwh,
        )
        days_in_month = calendar.monthrange(telemetry.ts.year, telemetry.ts.month)[1]
        rec = recommend(
            battery=battery,
            tariff=tariff,
            forecast=forecast,
            load=load,
            objective=obj,
            current_soc=telemetry.battery_soc,
            month_to_date_import_kwh=telemetry.month_to_date_grid_import_kwh,
            days_in_month=days_in_month,
        )
        return DashboardData(
            telemetry=telemetry,
            objective=obj,
            slot_assessments=assessments,
            recommendation=rec,
            usable_kwh=usable_kwh,
            usable_kwh_confidence=est.usable_kwh_confidence,
            daily_consumption_kwh=daily_kwh,
            daily_consumption_confidence=est.daily_consumption_confidence,
            tariff_rate=derived.rate,
            tariff_source=derived.source,
            tariff_source_date=derived.source_date,
            expected_pv_kwh_today=forecast.expected_pv_kwh_today,
            expected_pv_kwh_tomorrow=forecast.expected_pv_kwh_tomorrow,
            disclaimer=ADVISORY_DISCLAIMER,
        )
