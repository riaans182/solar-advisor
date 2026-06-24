from datetime import time

from solar_advisor.config import AppConfig, load_config


def test_load_config_from_env(monkeypatch):
    monkeypatch.setenv("SA_TARIFF_RATE", "3.56")
    monkeypatch.setenv("SA_TARIFF_FIXED_CHARGE", "600")
    monkeypatch.setenv("SA_BATTERY_NOMINAL_KWH", "15")
    monkeypatch.setenv("SA_BATTERY_SOC_FLOOR_PCT", "20")
    monkeypatch.setenv("SA_MAX_CHARGE_POWER_W", "7950")
    monkeypatch.setenv("SA_MAX_DISCHARGE_POWER_W", "7950")
    monkeypatch.setenv("SA_ESSENTIAL_POWER_W", "1136")
    monkeypatch.setenv("SA_DAYLIGHT_DAWN", "07:00")
    monkeypatch.setenv("SA_DAYLIGHT_DUSK", "17:30")
    monkeypatch.setenv("SA_OBJECTIVE_DEFAULT", "0.5")
    cfg = load_config()
    assert isinstance(cfg, AppConfig)
    assert cfg.tariff_rate == 3.56
    assert cfg.tariff_fixed_charge == 600.0
    assert cfg.battery_nominal_kwh == 15.0
    assert cfg.daylight_dawn == time(7, 0)
    assert cfg.daylight_dusk == time(17, 30)
    assert cfg.objective_default == 0.5


def test_objective_default_is_clamped(monkeypatch):
    monkeypatch.setenv("SA_OBJECTIVE_DEFAULT", "5")
    assert load_config().objective_default == 1.0
