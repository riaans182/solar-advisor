# tests/test_forecast_providers.py
import httpx

from solar_advisor.engine.inputs import SolarForecast
from solar_advisor.forecast.ha_provider import HomeAssistantForecastProvider
from solar_advisor.forecast.provider import ForecastProvider
from solar_advisor.forecast.static_provider import StaticForecastProvider


def test_static_provider_returns_configured_values():
    p = StaticForecastProvider(today_kwh=18.0, tomorrow_kwh=21.0)
    assert isinstance(p, ForecastProvider)
    fc = p.fetch()
    assert fc == SolarForecast(expected_pv_kwh_today=18.0, expected_pv_kwh_tomorrow=21.0)


def test_ha_provider_reads_forecast_solar_sensors():
    # Fake HA REST: /api/states/<entity> returns {"state": "<kwh>"}.
    def handler(request: httpx.Request) -> httpx.Response:
        entity = request.url.path.rsplit("/", 1)[-1]
        values = {
            "sensor.energy_production_today": "12.5",
            "sensor.energy_production_tomorrow": "9.0",
        }
        return httpx.Response(200, json={"state": values[entity]})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://ha.local:8123")
    p = HomeAssistantForecastProvider(client=client, token="x")
    assert isinstance(p, ForecastProvider)
    fc = p.fetch()
    assert fc.expected_pv_kwh_today == 12.5
    assert fc.expected_pv_kwh_tomorrow == 9.0
