# src/solar_advisor/engine/schedule_eval.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from enum import Enum

from solar_advisor.domain.schedule import Slot
from solar_advisor.engine.battery import BatteryModel
from solar_advisor.engine.inputs import DaylightWindow, LoadProfile, SolarForecast
from solar_advisor.engine.tariff import TariffModel


class SlotBehavior(Enum):
    SOLAR_CHARGING = "solar_charging"
    GRID_CHARGING = "grid_charging"
    DISCHARGING = "discharging"
    HOLDING = "holding"


@dataclass(frozen=True, slots=True)
class SlotAssessment:
    slot: Slot
    behavior: SlotBehavior
    end_soc: float  # projected SOC % at slot end
    grid_import_kwh: float  # grid energy drawn during the slot (load deficit + grid charge)
    cost: float  # grid_import_kwh * marginal rate


def _to_hours(t: time) -> float:
    return t.hour + t.minute / 60.0


def _slot_hours(slot: Slot) -> float:
    start, end = _to_hours(slot.start), _to_hours(slot.end)
    span = end - start
    return span + 24.0 if span <= 0 else span  # wrap past midnight


def _overlap_hours(slot: Slot, daylight: DaylightWindow) -> float:
    """Hours of the slot that fall within the daylight window. Slots that wrap
    midnight are treated as not overlapping daylight (night slots)."""
    start, end = _to_hours(slot.start), _to_hours(slot.end)
    if end <= start:  # wraps midnight -> night slot
        return 0.0
    lo = max(start, _to_hours(daylight.dawn))
    hi = min(end, _to_hours(daylight.dusk))
    return max(0.0, hi - lo)


def assess_schedule(
    schedule: list[Slot],
    battery: BatteryModel,
    tariff: TariffModel,
    forecast: SolarForecast,
    load: LoadProfile,
    daylight: DaylightWindow,
    start_soc: float,
    month_to_date_import_kwh: float,
) -> list[SlotAssessment]:
    """Simulate the schedule chronologically and classify each slot. PV is
    allocated across slots in proportion to their daylight overlap; load is served
    solar-first, then battery down to the floor, then grid. Grid charging happens
    only in a slot whose grid_charge flag is set, up to target_soc, capped by power.
    """
    rate = tariff.marginal_rate(month_to_date_import_kwh)
    total_overlap = sum(_overlap_hours(s, daylight) for s in schedule)
    soc_kwh = battery.soc_to_kwh(start_soc)
    floor_kwh = battery.floor_kwh

    out: list[SlotAssessment] = []
    for slot in schedule:
        hours = _slot_hours(slot)
        load_kwh = load.daily_kwh * hours / 24.0
        solar_kwh = (
            forecast.expected_pv_kwh_today * _overlap_hours(slot, daylight) / total_overlap
            if total_overlap > 0
            else 0.0
        )
        net = solar_kwh - load_kwh
        grid_import = 0.0

        if net >= 0:
            soc_kwh = min(battery.usable_kwh, soc_kwh + net)
        else:
            deficit = -net
            from_batt = min(max(0.0, soc_kwh - floor_kwh), deficit)
            soc_kwh -= from_batt
            grid_import += deficit - from_batt

        grid_charge = 0.0
        target_kwh = battery.soc_to_kwh(slot.target_soc)
        if slot.grid_charge and soc_kwh < target_kwh:
            max_charge_kwh = battery.max_charge_power_w / 1000.0 * hours
            grid_charge = min(target_kwh - soc_kwh, max_charge_kwh)
            soc_kwh += grid_charge
            grid_import += grid_charge

        if grid_charge > 0:
            behavior = SlotBehavior.GRID_CHARGING
        elif net > 0:
            behavior = SlotBehavior.SOLAR_CHARGING
        elif net < 0:
            behavior = SlotBehavior.DISCHARGING
        else:
            behavior = SlotBehavior.HOLDING

        out.append(
            SlotAssessment(
                slot=slot,
                behavior=behavior,
                end_soc=soc_kwh / battery.usable_kwh * 100.0,
                grid_import_kwh=grid_import,
                cost=grid_import * rate,
            )
        )
    return out
