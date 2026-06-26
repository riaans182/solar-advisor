from datetime import date

from solar_advisor.api.app import _local_today_fn


def test_timezone_config_default_and_env(monkeypatch):
    monkeypatch.delenv("SA_TIMEZONE", raising=False)
    from solar_advisor.config import load_config

    assert load_config().timezone == "Africa/Johannesburg"
    monkeypatch.setenv("SA_TIMEZONE", "UTC")
    assert load_config().timezone == "UTC"


def test_local_today_fn_uses_tz_and_falls_back():
    assert isinstance(_local_today_fn("Africa/Johannesburg")(), date)
    # An invalid zone name must not raise — it falls back to UTC.
    assert isinstance(_local_today_fn("Not/ARealZone")(), date)
