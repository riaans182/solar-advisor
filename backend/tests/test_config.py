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


def test_daily_consumption_kwh_from_env(monkeypatch):
    monkeypatch.setenv("SA_DAILY_CONSUMPTION_KWH", "18")
    assert load_config().daily_consumption_kwh == 18.0


def test_daily_consumption_kwh_default(monkeypatch):
    monkeypatch.delenv("SA_DAILY_CONSUMPTION_KWH", raising=False)
    assert load_config().daily_consumption_kwh == 24.0


def test_explain_settings_from_env(monkeypatch):
    monkeypatch.setenv("SA_EXPLAIN_MODEL", "claude-opus-4-8")
    monkeypatch.setenv("SA_EXPLAIN_ENABLED", "false")
    monkeypatch.setenv("SA_EXPLAIN_MIN_INTERVAL_S", "30")
    cfg = load_config()
    assert cfg.explain_model == "claude-opus-4-8"
    assert cfg.explain_enabled is False
    assert cfg.explain_min_interval_s == 30.0


def test_explain_settings_defaults(monkeypatch):
    for var in ("SA_EXPLAIN_MODEL", "SA_EXPLAIN_ENABLED", "SA_EXPLAIN_MIN_INTERVAL_S"):
        monkeypatch.delenv(var, raising=False)
    cfg = load_config()
    assert cfg.explain_model == "claude-haiku-4-5"
    assert cfg.explain_enabled is True
    assert cfg.explain_min_interval_s == 10.0


def test_explain_max_tokens_default_and_env(monkeypatch):
    monkeypatch.delenv("SA_EXPLAIN_MAX_TOKENS", raising=False)
    assert load_config().explain_max_tokens == 2048
    monkeypatch.setenv("SA_EXPLAIN_MAX_TOKENS", "512")
    assert load_config().explain_max_tokens == 512


def test_tariff_window_days_defaults_to_90(monkeypatch):
    monkeypatch.delenv("SA_TARIFF_WINDOW_DAYS", raising=False)
    from solar_advisor.config import load_config

    assert load_config().tariff_window_days == 90


def test_tariff_window_days_from_env(monkeypatch):
    monkeypatch.setenv("SA_TARIFF_WINDOW_DAYS", "120")
    from solar_advisor.config import load_config

    assert load_config().tariff_window_days == 120
