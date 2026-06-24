# tests/test_schedule.py
from datetime import time

from solar_advisor.domain.schedule import Slot, build_schedule


def _raw():
    # Mirrors the discovered live schedule (spec §2).
    return {
        "time_point": {1: "00:00", 2: "05:00", 3: "08:00", 4: "16:30", 5: "18:00", 6: "21:30"},
        "capacity_point": {1: 65, 2: 65, 3: 90, 4: 95, 5: 75, 6: 65},
        "grid_charge_point": {1: True, 2: True, 3: True, 4: False, 5: True, 6: True},
        "gen_charge_point": {1: False, 2: False, 3: False, 4: False, 5: False, 6: False},
    }


def test_build_schedule_has_six_slots():
    assert len(build_schedule(_raw())) == 6


def test_slot_fields_and_wraparound_end():
    slots = build_schedule(_raw())
    assert slots[0] == Slot(
        start=time(0, 0),
        end=time(5, 0),
        target_soc=65,
        grid_charge=True,
        gen_charge=False,
    )
    # Last slot wraps to the first slot's start.
    assert slots[5].start == time(21, 30)
    assert slots[5].end == time(0, 0)


def test_grid_charge_disabled_slot_detected():
    slots = build_schedule(_raw())
    assert slots[3].grid_charge is False  # 16:30 PV-peak slot


def test_build_schedule_coerces_string_bools():
    # The landmine: bool("false") is True. build_schedule must own typing and
    # treat the string "false" as False, "true" as True.
    raw = _raw()
    raw["grid_charge_point"] = {i: "false" for i in range(1, 7)}
    raw["gen_charge_point"] = {i: "true" for i in range(1, 7)}
    slots = build_schedule(raw)
    assert all(s.grid_charge is False for s in slots)
    assert all(s.gen_charge is True for s in slots)
