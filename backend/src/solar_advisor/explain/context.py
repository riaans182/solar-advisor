# src/solar_advisor/explain/context.py
from __future__ import annotations

from dataclasses import dataclass

from solar_advisor.services.recommendation import DashboardData


@dataclass(frozen=True, slots=True)
class SlotFact:
    start: str
    end: str
    target_soc: int
    grid_charge: bool
    behavior: str
    end_soc: float
    grid_import_kwh: float
    cost: float


@dataclass(frozen=True, slots=True)
class RecommendationFact:
    reserve_target_soc: float
    enable_overnight_grid_charge: bool
    grid_charge_kwh: float
    expected_daily_grid_import_kwh: float
    expected_daily_cost: float
    backup_hours: float
    monthly_cost_so_far: float


@dataclass(frozen=True, slots=True)
class ExplanationContext:
    """Pre-computed facts handed to the LLM. Every number here came from the
    deterministic engine or live telemetry; the LLM computes nothing (spec §8)."""

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
    tariff_rate: float
    expected_pv_kwh_today: float
    slots: list[SlotFact]
    recommendation: RecommendationFact
    disclaimer: str

    def allowed_numbers(self) -> list[float]:
        """The exact set of numbers the explanation may cite — the engine's
        quantitative outputs plus the structural references (slot indices, target
        SOCs) the model legitimately names. Curated here, NOT scraped from prose, so
        times and incidental digits don't grant the model free numeric range."""
        nums: list[float] = [
            self.objective,
            self.battery_soc,
            self.pv_power,
            self.grid_power,
            self.load_power,
            self.month_to_date_grid_import_kwh,
            self.usable_kwh,
            self.usable_kwh_confidence,
            self.daily_consumption_kwh,
            self.daily_consumption_confidence,
            self.tariff_rate,
            self.expected_pv_kwh_today,
            self.recommendation.reserve_target_soc,
            self.recommendation.grid_charge_kwh,
            self.recommendation.expected_daily_grid_import_kwh,
            self.recommendation.expected_daily_cost,
            self.recommendation.backup_hours,
            self.recommendation.monthly_cost_so_far,
        ]
        for i, s in enumerate(self.slots, start=1):
            nums.extend([float(i), float(s.target_soc), s.end_soc, s.grid_import_kwh, s.cost])
        return nums

    def to_facts(self) -> str:
        """Serialize the facts as the text block sent to the model. The guard's
        whitelist is derived from exactly this string."""
        lines = [
            "LIVE STATE:",
            f"- battery SOC: {self.battery_soc}%",
            f"- PV power: {self.pv_power} W",
            f"- grid power: {self.grid_power} W",
            f"- load power: {self.load_power} W",
            f"- month-to-date grid import: {self.month_to_date_grid_import_kwh} kWh",
            "ESTIMATES:",
            f"- usable battery capacity: {self.usable_kwh} kWh "
            f"(confidence {self.usable_kwh_confidence})",
            f"- typical daily consumption: {self.daily_consumption_kwh} kWh "
            f"(confidence {self.daily_consumption_confidence})",
            f"- expected solar today: {self.expected_pv_kwh_today} kWh",
            f"TARIFF: flat {self.tariff_rate} R/kWh (no cheap window).",
            f"OBJECTIVE (0=cost, 1=resilience): {self.objective}",
            "CURRENT SCHEDULE (per slot):",
        ]
        for i, s in enumerate(self.slots, start=1):
            lines.append(
                f"- slot {i} {s.start}-{s.end}: target SOC {s.target_soc}%, "
                f"grid-charge {'on' if s.grid_charge else 'off'}, behavior {s.behavior}, "
                f"projected end SOC {s.end_soc}%, grid import {s.grid_import_kwh} kWh, "
                f"cost R{s.cost}"
            )
        r = self.recommendation
        lines += [
            "RECOMMENDATION (engine output):",
            f"- reserve target SOC: {r.reserve_target_soc}%",
            f"- overnight grid-charge needed: {r.enable_overnight_grid_charge}",
            f"- grid-charge energy: {r.grid_charge_kwh} kWh",
            f"- expected daily grid import: {r.expected_daily_grid_import_kwh} kWh",
            f"- expected daily cost: R{r.expected_daily_cost}",
            f"- backup runtime at reserve: {r.backup_hours} hours",
            f"- month-to-date bill: R{r.monthly_cost_so_far}",
            f"DISCLAIMER: {self.disclaimer}",
        ]
        return "\n".join(lines)


def build_context(data: DashboardData) -> ExplanationContext:
    return ExplanationContext(
        objective=data.objective,
        battery_soc=data.telemetry.battery_soc,
        pv_power=data.telemetry.pv_power,
        grid_power=data.telemetry.grid_power,
        load_power=data.telemetry.load_power,
        month_to_date_grid_import_kwh=data.telemetry.month_to_date_grid_import_kwh,
        usable_kwh=round(data.usable_kwh, 2),
        usable_kwh_confidence=round(data.usable_kwh_confidence, 2),
        daily_consumption_kwh=round(data.daily_consumption_kwh, 2),
        daily_consumption_confidence=round(data.daily_consumption_confidence, 2),
        tariff_rate=data.tariff_rate,
        expected_pv_kwh_today=round(data.expected_pv_kwh_today, 2),
        slots=[
            SlotFact(
                start=a.slot.start.isoformat(timespec="minutes"),
                end=a.slot.end.isoformat(timespec="minutes"),
                target_soc=a.slot.target_soc,
                grid_charge=a.slot.grid_charge,
                behavior=a.behavior.value,
                end_soc=round(a.end_soc, 1),
                grid_import_kwh=round(a.grid_import_kwh, 2),
                cost=round(a.cost, 2),
            )
            for a in data.slot_assessments
        ],
        recommendation=RecommendationFact(
            reserve_target_soc=round(data.recommendation.reserve_target_soc, 1),
            enable_overnight_grid_charge=data.recommendation.enable_overnight_grid_charge,
            grid_charge_kwh=round(data.recommendation.grid_charge_kwh, 2),
            expected_daily_grid_import_kwh=round(
                data.recommendation.expected_daily_grid_import_kwh, 2
            ),
            expected_daily_cost=round(data.recommendation.expected_daily_cost, 2),
            backup_hours=round(data.recommendation.backup_hours, 1),
            monthly_cost_so_far=round(data.recommendation.monthly_cost_so_far, 2),
        ),
        disclaimer=data.disclaimer,
    )
