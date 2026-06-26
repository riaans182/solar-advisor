# src/solar_advisor/engine/recommend_schedule.py
from __future__ import annotations

from solar_advisor.domain.schedule import Slot
from solar_advisor.engine.inputs import DaylightWindow
from solar_advisor.engine.schedule_eval import _overlap_hours


def recommend_schedule(
    current: list[Slot],
    *,
    reserve_soc: int,
    grid_charge_needed: bool,
    daylight: DaylightWindow,
) -> list[Slot]:
    """Project the flat-tariff reserve policy onto the inverter's slot grid.

    Grid-charging is pure cost on a flat tariff with no cheap window, so it is off
    everywhere unless the day's energy balance can't hold the resilience reserve
    (``grid_charge_needed``), in which case the night slots top up to the reserve.
    Daytime slots target 100% so solar fills the battery without curtailment; night
    slots target the reserve so the battery may discharge to it serving load. Time
    points and the (unmodelled) gen-charge flag are preserved from the current
    schedule — only target SOC and grid-charge are advised."""

    out: list[Slot] = []
    for s in current:
        if _overlap_hours(s, daylight) > 0:
            out.append(
                Slot(
                    start=s.start,
                    end=s.end,
                    target_soc=100,
                    grid_charge=False,
                    gen_charge=s.gen_charge,
                )
            )
        else:
            out.append(
                Slot(
                    start=s.start,
                    end=s.end,
                    target_soc=reserve_soc,
                    grid_charge=grid_charge_needed,
                    gen_charge=s.gen_charge,
                )
            )
    return out
