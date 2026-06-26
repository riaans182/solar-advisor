# tests/test_forecast_solar.py
from datetime import date

from solar_advisor.forecast.forecast_solar_provider import ForecastSolarProvider, PvArray


def _resp(today_wh: float, tomorrow_wh: float) -> dict:
    return {"result": {"watt_hours_day": {"2026-06-26": today_wh, "2026-06-27": tomorrow_wh}}}


def _provider(fetch, **kw):
    arrays = [PvArray(tilt=26, azimuth=-135, kwp=2.5), PvArray(tilt=26, azimuth=45, kwp=2.5)]
    defaults = dict(
        lat=-33.92,
        lon=18.42,
        arrays=arrays,
        ttl_s=10800.0,
        fallback_today=20.0,
        fallback_tomorrow=20.0,
        fetch_json=fetch,
        monotonic=lambda: 0.0,
        today=lambda: date(2026, 6, 26),
    )
    defaults.update(kw)
    return ForecastSolarProvider(**defaults)


def test_sums_planes_for_today_and_tomorrow():
    p = _provider(lambda url: _resp(6000, 5000))
    fc = p.fetch()
    assert round(fc.expected_pv_kwh_today, 1) == 12.0
    assert round(fc.expected_pv_kwh_tomorrow, 1) == 10.0


def test_caches_within_ttl():
    calls = {"n": 0}

    def fetch(url):
        calls["n"] += 1
        return _resp(6000, 5000)

    p = _provider(fetch, monotonic=lambda: 100.0)
    p.fetch()
    p.fetch()
    assert calls["n"] == 2  # 2 arrays -> 2 calls on first fetch; second fetch cached


def test_falls_back_to_static_on_error_when_cold():
    def boom(url):
        raise RuntimeError("network down")

    p = _provider(boom)
    fc = p.fetch()
    assert fc.expected_pv_kwh_today == 20.0
    assert fc.expected_pv_kwh_tomorrow == 20.0


def test_serves_stale_cache_on_later_error():
    state = {"fail": False}

    def fetch(url):
        if state["fail"]:
            raise RuntimeError("rate limited")
        return _resp(6000, 5000)

    times = iter([0.0, 0.0, 20000.0, 20000.0, 20000.0])
    p = _provider(fetch, monotonic=lambda: next(times))
    assert round(p.fetch().expected_pv_kwh_today, 1) == 12.0
    state["fail"] = True
    assert round(p.fetch().expected_pv_kwh_today, 1) == 12.0
