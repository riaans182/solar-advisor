# src/solar_advisor/domain/schedule.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Any


@dataclass(frozen=True, slots=True)
class Slot:
    start: time
    end: time
    target_soc: int
    grid_charge: bool
    gen_charge: bool


def _parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


def build_schedule(raw: dict[str, dict[int, Any]]) -> list[Slot]:
    """Assemble the 6-slot TOU schedule. Each slot ends where the next begins;
    slot 6 wraps to slot 1's start."""
    starts = {i: _parse_hhmm(raw["time_point"][i]) for i in range(1, 7)}
    slots: list[Slot] = []
    for i in range(1, 7):
        nxt = 1 if i == 6 else i + 1
        slots.append(
            Slot(
                start=starts[i],
                end=starts[nxt],
                target_soc=int(raw["capacity_point"][i]),
                grid_charge=bool(raw["grid_charge_point"][i]),
                gen_charge=bool(raw["gen_charge_point"][i]),
            )
        )
    return slots
