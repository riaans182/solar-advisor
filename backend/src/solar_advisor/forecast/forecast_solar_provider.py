# src/solar_advisor/forecast/forecast_solar_provider.py
from __future__ import annotations

import time as _time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from solar_advisor.engine.inputs import SolarForecast


@dataclass(frozen=True, slots=True)
class PvArray:
    tilt: float
    azimuth: float  # Forecast.Solar convention: 0=south, -90=east, +90=west, ±180=north
    kwp: float


def _default_fetch_json(url: str) -> dict[str, Any]:
    resp = httpx.get(url, timeout=10.0)
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()
    return data


def _utc_today() -> date:
    return datetime.now(UTC).date()


class ForecastSolarProvider:
    """Sums Forecast.Solar per-plane daily estimates into a SolarForecast, cached
    with a TTL and falling back to static values on any error. fetch() is safe to
    call on every request: it only hits the network when the cache is stale, which
    keeps it well under the free tier's ~12 req/hr limit."""

    def __init__(
        self,
        *,
        lat: float,
        lon: float,
        arrays: Sequence[PvArray],
        ttl_s: float,
        fallback_today: float,
        fallback_tomorrow: float,
        fetch_json: Callable[[str], dict[str, Any]] = _default_fetch_json,
        monotonic: Callable[[], float] = _time.monotonic,
        today: Callable[[], date] = _utc_today,
    ) -> None:
        self._lat = lat
        self._lon = lon
        self._arrays = list(arrays)
        self._ttl_s = ttl_s
        self._fallback = SolarForecast(fallback_today, fallback_tomorrow)
        self._fetch_json = fetch_json
        self._monotonic = monotonic
        self._today = today
        self._cache: SolarForecast | None = None
        self._fetched_at: float | None = None

    def fetch(self) -> SolarForecast:
        now = self._monotonic()
        if (
            self._cache is not None
            and self._fetched_at is not None
            and (now - self._fetched_at) < self._ttl_s
        ):
            return self._cache
        try:
            result = self._query()
        except Exception:
            # Never hard-depend on the network: serve the last good value, or static.
            return self._cache if self._cache is not None else self._fallback
        self._cache = result
        self._fetched_at = now
        return result

    def _query(self) -> SolarForecast:
        today = self._today()
        tomorrow = today + timedelta(days=1)
        totals: dict[str, float] = {}
        for arr in self._arrays:
            url = (
                f"https://api.forecast.solar/estimate/{self._lat}/{self._lon}/"
                f"{arr.tilt}/{arr.azimuth}/{arr.kwp}"
            )
            data = self._fetch_json(url)
            for day_str, wh in data["result"]["watt_hours_day"].items():
                totals[day_str] = totals.get(day_str, 0.0) + float(wh)
        return SolarForecast(
            expected_pv_kwh_today=self._pick(totals, today),
            expected_pv_kwh_tomorrow=self._pick(totals, tomorrow),
        )

    @staticmethod
    def _pick(totals: dict[str, float], day: date) -> float:
        if not totals:
            raise KeyError("forecast returned no days")
        wh = totals.get(day.isoformat())
        if wh is None:  # horizon may not include the date; use the nearest day
            nearest = min(totals, key=lambda d: abs((date.fromisoformat(d) - day).days))
            wh = totals[nearest]
        return wh / 1000.0
