# tests/test_recommend_schedule.py
from datetime import time

from solar_advisor.domain.schedule import Slot
from solar_advisor.engine.inputs import DaylightWindow
from solar_advisor.engine.recommend_schedule import recommend_schedule

DAYLIGHT = DaylightWindow(dawn=time(7, 0), dusk=time(17, 30))


def _slot(start, end, target, grid):
    return Slot(
        start=time(start, 0),
        end=time(end, 0),
        target_soc=target,
        grid_charge=grid,
        gen_charge=False,
    )


def test_daytime_slots_fill_from_solar_no_grid_charge():
    rec = recommend_schedule(
        [_slot(10, 16, 65, True)], reserve_soc=60, grid_charge_needed=False, daylight=DAYLIGHT
    )
    assert rec[0].target_soc == 100
    assert rec[0].grid_charge is False


def test_night_slots_hold_reserve_no_charge_when_not_needed():
    rec = recommend_schedule(
        [_slot(21, 5, 95, True)], reserve_soc=60, grid_charge_needed=False, daylight=DAYLIGHT
    )
    assert rec[0].target_soc == 60
    assert rec[0].grid_charge is False


def test_night_slots_grid_charge_only_when_needed():
    rec = recommend_schedule(
        [_slot(21, 5, 95, False)], reserve_soc=60, grid_charge_needed=True, daylight=DAYLIGHT
    )
    assert rec[0].grid_charge is True
    assert rec[0].target_soc == 60


def test_preserves_time_points_and_gen_charge():
    src = [Slot(start=time(0, 0), end=time(5, 0), target_soc=65, grid_charge=True, gen_charge=True)]
    rec = recommend_schedule(src, reserve_soc=60, grid_charge_needed=False, daylight=DAYLIGHT)
    assert rec[0].start == time(0, 0)
    assert rec[0].end == time(5, 0)
    assert rec[0].gen_charge is True
