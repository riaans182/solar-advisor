# tests/test_forecast_provider.py
from solar_advisor.engine.inputs import SolarForecast
from solar_advisor.forecast.provider import ForecastProvider


class _StubProvider:
    def fetch(self) -> SolarForecast:
        return SolarForecast(expected_pv_kwh_today=10.0, expected_pv_kwh_tomorrow=12.0)


def test_stub_satisfies_forecast_provider_protocol():
    p: ForecastProvider = _StubProvider()
    assert isinstance(p, ForecastProvider)
    assert p.fetch().expected_pv_kwh_today == 10.0
