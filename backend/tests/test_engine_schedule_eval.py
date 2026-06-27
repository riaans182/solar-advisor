# tests/test_engine_schedule_eval.py
from datetime import time

from solar_advisor.domain.schedule import Slot
from solar_advisor.engine.battery import BatteryModel
from solar_advisor.engine.inputs import DaylightWindow, LoadProfile, SolarForecast
from solar_advisor.engine.schedule_eval import SlotBehavior, assess_schedule
from solar_advisor.engine.tariff import FlatRateTariff


def _battery():
    return BatteryModel(
        usable_kwh=15.0,
        soc_floor_pct=20.0,
        max_charge_power_w=7600.0,
        max_discharge_power_w=7600.0,
    )


def _tariff():
    return FlatRateTariff(energy_rate=3.56, monthly_fixed_charge=600.0)


def _daylight():
    return DaylightWindow(dawn=time(7, 0), dusk=time(17, 30))


def _two_slots():
    # Night slot then a daytime slot.
    return [
        Slot(start=time(0, 0), end=time(7, 0), target_soc=90, grid_charge=True, gen_charge=False),
        Slot(
            start=time(7, 0), end=time(17, 30), target_soc=95, grid_charge=False, gen_charge=False
        ),
    ]


def test_returns_one_assessment_per_slot():
    out = assess_schedule(
        _two_slots(),
        _battery(),
        _tariff(),
        SolarForecast(expected_pv_kwh_today=20.0, expected_pv_kwh_tomorrow=20.0),
        LoadProfile(daily_kwh=24.0, essential_power_w=500.0),
        _daylight(),
        start_soc=50.0,
        month_to_date_import_kwh=0.0,
    )
    assert len(out) == 2


def test_night_grid_charge_slot_classified_grid_charging_with_cost():
    out = assess_schedule(
        _two_slots(),
        _battery(),
        _tariff(),
        SolarForecast(expected_pv_kwh_today=20.0, expected_pv_kwh_tomorrow=20.0),
        LoadProfile(daily_kwh=24.0, essential_power_w=500.0),
        _daylight(),
        start_soc=50.0,
        month_to_date_import_kwh=0.0,
    )
    night = out[0]
    assert night.behavior is SlotBehavior.GRID_CHARGING  # no solar, grid-charging to 90%
    assert night.grid_import_kwh > 0
    assert night.cost == night.grid_import_kwh * 3.56


def test_daytime_slot_with_strong_sun_charges_from_solar():
    out = assess_schedule(
        _two_slots(),
        _battery(),
        _tariff(),
        SolarForecast(expected_pv_kwh_today=40.0, expected_pv_kwh_tomorrow=40.0),
        LoadProfile(daily_kwh=12.0, essential_power_w=500.0),
        _daylight(),
        start_soc=50.0,
        month_to_date_import_kwh=0.0,
    )
    day = out[1]
    assert day.behavior is SlotBehavior.SOLAR_CHARGING
    assert day.grid_import_kwh == 0.0


def test_slot_at_floor_with_deficit_holds_not_discharges():
    slot = Slot(
        start=time(0, 0), end=time(6, 0), target_soc=20, grid_charge=False, gen_charge=False
    )
    out = assess_schedule(
        [slot],
        _battery(),
        _tariff(),
        SolarForecast(expected_pv_kwh_today=0.0, expected_pv_kwh_tomorrow=0.0),
        LoadProfile(daily_kwh=24.0, essential_power_w=500.0),
        _daylight(),
        start_soc=20.0,
        month_to_date_import_kwh=0.0,
    )
    assert out[0].behavior is SlotBehavior.HOLDING
    assert out[0].grid_import_kwh > 0


def test_grid_charge_is_capped_by_grid_charge_power_not_max_charge():
    from datetime import time

    from solar_advisor.domain.schedule import Slot
    from solar_advisor.engine.battery import BatteryModel
    from solar_advisor.engine.inputs import DaylightWindow, LoadProfile, SolarForecast
    from solar_advisor.engine.schedule_eval import assess_schedule
    from solar_advisor.engine.tariff import FlatRateTariff

    slot = Slot(
        start=time(1, 0), end=time(3, 0), target_soc=100, grid_charge=True, gen_charge=False
    )
    forecast = SolarForecast(expected_pv_kwh_today=0.0, expected_pv_kwh_tomorrow=0.0)
    load = LoadProfile(daily_kwh=0.0, essential_power_w=1000.0)
    daylight = DaylightWindow(dawn=time(7, 0), dusk=time(17, 30))

    def grid_import(grid_power_w: float) -> float:
        battery = BatteryModel(
            usable_kwh=15.0,
            soc_floor_pct=20.0,
            max_charge_power_w=8000.0,
            max_discharge_power_w=8000.0,
            max_grid_charge_power_w=grid_power_w,
        )
        out = assess_schedule(
            [slot],
            battery,
            FlatRateTariff(3.5, 600.0),
            forecast,
            load,
            daylight,
            start_soc=50.0,
            month_to_date_import_kwh=0.0,
        )
        return out[0].grid_import_kwh

    capped = grid_import(3600.0)
    full = grid_import(8000.0)
    assert round(capped, 2) == round(3600.0 / 1000.0 * 2.0, 2)
    assert full > capped


def test_grid_charge_power_zero_falls_back_to_max_charge():
    from datetime import time

    from solar_advisor.domain.schedule import Slot
    from solar_advisor.engine.battery import BatteryModel
    from solar_advisor.engine.inputs import DaylightWindow, LoadProfile, SolarForecast
    from solar_advisor.engine.schedule_eval import assess_schedule
    from solar_advisor.engine.tariff import FlatRateTariff

    slot = Slot(
        start=time(1, 0), end=time(3, 0), target_soc=100, grid_charge=True, gen_charge=False
    )
    forecast = SolarForecast(0.0, 0.0)
    load = LoadProfile(daily_kwh=0.0, essential_power_w=1000.0)
    daylight = DaylightWindow(dawn=time(7, 0), dusk=time(17, 30))

    def grid_import(model: BatteryModel) -> float:
        return assess_schedule(
            [slot],
            model,
            FlatRateTariff(3.5, 600.0),
            forecast,
            load,
            daylight,
            start_soc=50.0,
            month_to_date_import_kwh=0.0,
        )[0].grid_import_kwh

    base = dict(
        usable_kwh=15.0, soc_floor_pct=20.0, max_charge_power_w=2000.0, max_discharge_power_w=8000.0
    )
    assert grid_import(BatteryModel(**base, max_grid_charge_power_w=0.0)) == grid_import(
        BatteryModel(**base, max_grid_charge_power_w=2000.0)
    )
