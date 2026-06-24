# tests/test_engine_optimize.py
from solar_advisor.engine.battery import BatteryModel
from solar_advisor.engine.inputs import LoadProfile, SolarForecast
from solar_advisor.engine.optimize import Recommendation, recommend
from solar_advisor.engine.tariff import FlatRateTariff


def _common():
    return dict(
        battery=BatteryModel(
            usable_kwh=15.0,
            soc_floor_pct=20.0,
            max_charge_power_w=7600.0,
            max_discharge_power_w=7600.0,
        ),
        tariff=FlatRateTariff(energy_rate=3.56, monthly_fixed_charge=600.0),
        # Solar short of load so a deficit exists; low SOC so reserve needs grid.
        forecast=SolarForecast(expected_pv_kwh_today=8.0, expected_pv_kwh_tomorrow=8.0),
        load=LoadProfile(daily_kwh=20.0, essential_power_w=500.0),
        current_soc=30.0,
        month_to_date_import_kwh=100.0,
        days_in_month=30,
    )


def test_cost_end_no_grid_charge_reserve_at_floor():
    r = recommend(objective=0.0, **_common())
    assert isinstance(r, Recommendation)
    assert r.reserve_target_soc == 20.0
    assert r.enable_overnight_grid_charge is False
    assert r.grid_charge_kwh == 0.0
    # Only the load deficit (20 - 8 = 12 kWh) is imported.
    assert r.expected_daily_grid_import_kwh == 12.0
    assert r.expected_daily_cost == 12.0 * 3.56


def test_resilience_end_grid_charges_and_costs_more():
    cost = recommend(objective=0.0, **_common())
    resil = recommend(objective=1.0, **_common())
    assert resil.reserve_target_soc == 100.0
    assert resil.enable_overnight_grid_charge is True
    assert resil.grid_charge_kwh > 0
    assert resil.expected_daily_cost > cost.expected_daily_cost
    assert resil.backup_hours > cost.backup_hours


def test_slider_sweep_is_monotonic():
    rs = [recommend(objective=o / 10, **_common()) for o in range(11)]
    reserves = [r.reserve_target_soc for r in rs]
    costs = [r.expected_daily_cost for r in rs]
    assert reserves == sorted(reserves)
    assert costs == sorted(costs)


def test_monthly_cost_uses_fixed_charge_plus_month_to_date():
    r = recommend(objective=0.0, **_common())
    assert r.monthly_cost_so_far == 600.0 + 100.0 * 3.56
