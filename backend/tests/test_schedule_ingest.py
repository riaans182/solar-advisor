# tests/test_schedule_ingest.py
from datetime import time

from solar_advisor.domain.schedule import Slot
from solar_advisor.ingest.schedule_accumulator import ScheduleAccumulator
from solar_advisor.ingest.schedule_topics import parse_schedule_value


def test_parse_schedule_value_known_topics():
    assert parse_schedule_value("solar_assistant/inverter_1/time_point_3/state", "08:00") == (
        "time_point",
        3,
        "08:00",
    )
    assert parse_schedule_value("solar_assistant/inverter_1/capacity_point_4/state", "95") == (
        "capacity_point",
        4,
        "95",
    )
    assert parse_schedule_value("solar_assistant/inverter_1/grid_charge_point_1/state", "true") == (
        "grid_charge_point",
        1,
        "true",
    )


def test_parse_schedule_value_ignores_other_topics():
    assert parse_schedule_value("solar_assistant/inverter_1/pv_power/state", "100") is None


def _feed_live_schedule(acc):
    raw = {
        "time_point": {1: "00:00", 2: "05:00", 3: "08:00", 4: "16:30", 5: "18:00", 6: "21:30"},
        "capacity_point": {1: "65", 2: "65", 3: "90", 4: "95", 5: "75", 6: "65"},
        "grid_charge_point": {1: "true", 2: "true", 3: "true", 4: "false", 5: "true", 6: "true"},
        "gen_charge_point": {i: "false" for i in range(1, 7)},
    }
    last = None
    for field, slots in raw.items():
        for i, val in slots.items():
            last = acc.ingest(f"solar_assistant/inverter_1/{field}_{i}/state", val)
    return last


def test_accumulator_emits_schedule_once_complete():
    acc = ScheduleAccumulator()
    schedule = _feed_live_schedule(acc)
    assert schedule is not None
    assert len(schedule) == 6
    assert schedule[0] == Slot(
        start=time(0, 0),
        end=time(5, 0),
        target_soc=65,
        grid_charge=True,
        gen_charge=False,
    )
    assert schedule[3].grid_charge is False  # 16:30 PV-peak slot


def test_accumulator_returns_none_until_complete():
    acc = ScheduleAccumulator()
    assert acc.ingest("solar_assistant/inverter_1/time_point_1/state", "00:00") is None
