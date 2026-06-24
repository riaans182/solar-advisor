# tests/test_engine_battery.py
from solar_advisor.engine.battery import BatteryModel


def _batt():
    # 15 kWh nominal (3x Dyness 5 kWh), 20% floor, ~7.6 kW charge/discharge
    return BatteryModel(
        usable_kwh=15.0,
        soc_floor_pct=20.0,
        max_charge_power_w=7600.0,
        max_discharge_power_w=7600.0,
    )


def test_soc_to_kwh():
    assert _batt().soc_to_kwh(50.0) == 7.5


def test_floor_kwh():
    assert _batt().floor_kwh == 3.0  # 15 * 20%


def test_energy_between_soc_levels():
    assert _batt().energy_between(40.0, 90.0) == 7.5  # 15 * 50%
