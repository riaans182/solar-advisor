# Plan J — Real Forecast & Prepaid Projection (Backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the static solar forecast with our own Forecast.Solar provider (split-array, cached, fallback) and add a prepaid month projection (spend vs projected energy cost) to the dashboard.

**Architecture:** A new `ForecastSolarProvider` implements the existing `ForecastProvider` protocol — sums per-plane Forecast.Solar estimates, caches with a TTL, falls back to static on any error. Config gains lat/lon/arrays/source/ttl. `RecommendationService` gains an optional purchase reader and computes `month_spend`/`month_projected_cost`/`month_balance` (energy only). New fields flow to `DashboardView`.

**Tech Stack:** Python 3.12, FastAPI + Pydantic v2, httpx (already a dep), stdlib sqlite3, pytest, ruff, mypy --strict, import-linter.

**Reference (read first):** spec `docs/superpowers/specs/2026-06-26-forecast-prepaid-projection-design.md`. Mirror: `forecast/provider.py` (Protocol), `forecast/static_provider.py`, `engine/inputs.py` (`SolarForecast`), `services/recommendation.py` (`DashboardData`/`build`), `tariff/provider.py` (`PurchaseReader` Protocol with `list_since(cutoff: date)`), `config.py`, `api/app.py` (`_to_view`, `create_production_app`), `api/schemas.py`. **From `backend/`: first `make install`, then `.venv/bin/pytest`, `.venv/bin/ruff`, `.venv/bin/mypy`, `.venv/bin/lint-imports --config .importlinter`.**

---

## File Structure

| File | Change |
|------|--------|
| `src/solar_advisor/forecast/forecast_solar_provider.py` (create) | `PvArray` + `ForecastSolarProvider`. |
| `src/solar_advisor/config.py` | add `forecast_source`, `lat`, `lon`, `forecast_ttl_s`, `pv_arrays`. |
| `src/solar_advisor/api/app.py` | select provider in `create_production_app`; pass purchase reader to the service; `_to_view` += projection fields. |
| `src/solar_advisor/services/recommendation.py` | `DashboardData` += projection fields; `build()` computes them; optional `purchases` reader. |
| `src/solar_advisor/api/schemas.py` | `DashboardView` += `month_spend`, `month_projected_cost`, `month_balance`. |
| `docker-compose.yml` | pass new `SA_*` envs to `api`. |
| tests | `test_forecast_providers.py` (or new `test_forecast_solar.py`), `test_config.py`, `test_recommendation_service.py`, `test_api.py`. |

---

## Group 1 — Forecast.Solar provider + config

### Task 1: `PvArray` + `ForecastSolarProvider`

**Files:** Create `src/solar_advisor/forecast/forecast_solar_provider.py`; Test `tests/test_forecast_solar.py`.

- [ ] **Step 1: Write the failing test** `tests/test_forecast_solar.py`:
```python
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
    # Each of the two arrays returns 6000/5000 Wh -> summed 12000/10000 Wh = 12/10 kWh.
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
    # 2 arrays => 2 HTTP calls on the first fetch; the second fetch() is cached.
    assert calls["n"] == 2


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

    # Advance the clock past the TTL on the 2nd fetch so it tries (and fails) to refresh.
    times = iter([0.0, 0.0, 20000.0, 20000.0, 20000.0])
    p = _provider(fetch, monotonic=lambda: next(times))
    assert round(p.fetch().expected_pv_kwh_today, 1) == 12.0  # warm cache
    state["fail"] = True
    assert round(p.fetch().expected_pv_kwh_today, 1) == 12.0  # refresh fails -> stale cache
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_forecast_solar.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement** `src/solar_advisor/forecast/forecast_solar_provider.py`:
```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_forecast_solar.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/solar_advisor/forecast/forecast_solar_provider.py tests/test_forecast_solar.py
git commit -m "feat: add Forecast.Solar provider (split-array, cached, static fallback)"
```

### Task 2: Config — forecast source, location, arrays

**Files:** Modify `src/solar_advisor/config.py`; Test `tests/test_config.py`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_config.py`):
```python
def test_forecast_defaults(monkeypatch):
    for k in ("SA_FORECAST_SOURCE", "SA_LAT", "SA_LON", "SA_PV_ARRAYS", "SA_FORECAST_TTL_S"):
        monkeypatch.delenv(k, raising=False)
    from solar_advisor.config import load_config

    cfg = load_config()
    assert cfg.forecast_source == "static"
    assert cfg.lat == -33.92
    assert cfg.lon == 18.42
    assert len(cfg.pv_arrays) == 2
    assert cfg.pv_arrays[0].kwp == 2.5


def test_pv_arrays_malformed_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("SA_PV_ARRAYS", "not json")
    from solar_advisor.config import load_config

    cfg = load_config()
    assert len(cfg.pv_arrays) == 2  # default NE/SW split


def test_forecast_source_from_env(monkeypatch):
    monkeypatch.setenv("SA_FORECAST_SOURCE", "forecast_solar")
    from solar_advisor.config import load_config

    assert load_config().forecast_source == "forecast_solar"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py -k "forecast or pv_arrays" -v`
Expected: FAIL — fields missing.

- [ ] **Step 3: Implement.** In `src/solar_advisor/config.py`:

Add imports at top:
```python
import json

from solar_advisor.forecast.forecast_solar_provider import PvArray
```

Add fields to `AppConfig` (in the defaulted block, after `tariff_window_days`):
```python
    tariff_window_days: int = 90  # trailing window for the data-derived marginal rate
    forecast_source: str = "static"  # "static" | "forecast_solar"
    lat: float = -33.92
    lon: float = 18.42
    forecast_ttl_s: float = 10800.0  # 3h cache for the Forecast.Solar call
    pv_arrays: tuple[PvArray, ...] = ()
```

Add a parse helper above `load_config`:
```python
_DEFAULT_PV_ARRAYS: tuple[PvArray, ...] = (
    PvArray(tilt=26.0, azimuth=-135.0, kwp=2.5),  # 5 panels NE
    PvArray(tilt=26.0, azimuth=45.0, kwp=2.5),  # 5 panels SW
)


def _parse_pv_arrays(raw: str | None) -> tuple[PvArray, ...]:
    if not raw:
        return _DEFAULT_PV_ARRAYS
    try:
        items = json.loads(raw)
        parsed = tuple(
            PvArray(tilt=float(i["tilt"]), azimuth=float(i["azimuth"]), kwp=float(i["kwp"]))
            for i in items
        )
        return parsed or _DEFAULT_PV_ARRAYS
    except (ValueError, TypeError, KeyError):
        return _DEFAULT_PV_ARRAYS
```

In `load_config()`, add to the returned `AppConfig(...)`:
```python
        tariff_window_days=int(os.environ.get("SA_TARIFF_WINDOW_DAYS", "90")),
        forecast_source=os.environ.get("SA_FORECAST_SOURCE", "static"),
        lat=float(os.environ.get("SA_LAT", "-33.92")),
        lon=float(os.environ.get("SA_LON", "18.42")),
        forecast_ttl_s=float(os.environ.get("SA_FORECAST_TTL_S", "10800")),
        pv_arrays=_parse_pv_arrays(os.environ.get("SA_PV_ARRAYS")),
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py -k "forecast or pv_arrays" -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/solar_advisor/config.py tests/test_config.py
git commit -m "feat: add forecast source, location and PV-array config"
```

---

## Group 2 — Wiring + month projection

### Task 3: Select the provider; wire it + compose

**Files:** Modify `src/solar_advisor/api/app.py`, `docker-compose.yml`.

- [ ] **Step 1: Edit `create_production_app()` in `api/app.py`.** Read the function first. Add imports:
```python
from solar_advisor.forecast.forecast_solar_provider import ForecastSolarProvider
```
(`StaticForecastProvider` is already imported.) Replace the existing `forecast = StaticForecastProvider(...)` construction with source selection:
```python
    if config.forecast_source == "forecast_solar":
        forecast: ForecastProvider = ForecastSolarProvider(
            lat=config.lat,
            lon=config.lon,
            arrays=config.pv_arrays,
            ttl_s=config.forecast_ttl_s,
            fallback_today=config.forecast_today_kwh,
            fallback_tomorrow=config.forecast_tomorrow_kwh,
        )
    else:
        forecast = StaticForecastProvider(
            today_kwh=config.forecast_today_kwh, tomorrow_kwh=config.forecast_tomorrow_kwh
        )
```
Add the import for the annotation: `from solar_advisor.forecast.provider import ForecastProvider` (if not already imported).

- [ ] **Step 2: Pass new envs in `docker-compose.yml`** under the `api` service `environment:` block:
```yaml
      SA_FORECAST_SOURCE: ${SA_FORECAST_SOURCE:-static}
      SA_LAT: ${SA_LAT:--33.92}
      SA_LON: ${SA_LON:-18.42}
      SA_PV_ARRAYS: ${SA_PV_ARRAYS:-}
      SA_FORECAST_TTL_S: ${SA_FORECAST_TTL_S:-10800}
```

- [ ] **Step 3: Verify the app still builds**

Run: `SA_FORECAST_SOURCE=forecast_solar .venv/bin/python -c "from solar_advisor.api.app import create_production_app; print(create_production_app().title)"`
Expected: prints `Solar Advisor` (the provider is constructed; no network call happens at construction).

- [ ] **Step 4: Commit**

```bash
git add src/solar_advisor/api/app.py docker-compose.yml
git commit -m "feat: select forecast provider via SA_FORECAST_SOURCE; wire compose envs"
```

### Task 4: Month projection in the service + schema

**Files:** Modify `src/solar_advisor/services/recommendation.py`, `src/solar_advisor/api/schemas.py`; Test `tests/test_recommendation_service.py`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_recommendation_service.py`; reuses `_config()/_live_state()/_FakeEstimator/_FakeForecast` and the `_FakeReader` already defined there for the tariff tests). `_live_state()` stamps telemetry at 2026-06-22 (day 22) with `month_to_date_grid_import_kwh=100.0`; June has 30 days:
```python
from datetime import date

from solar_advisor.domain.purchase import Purchase


def test_month_projection_energy_only():
    # 2 purchases this month total R1500; one last month excluded.
    reader = _FakeReader(
        [
            Purchase(purchased_at=date(2026, 6, 3), rand=1000.0, units_kwh=280.0),
            Purchase(purchased_at=date(2026, 6, 18), rand=500.0, units_kwh=140.0),
            Purchase(purchased_at=date(2026, 5, 20), rand=900.0, units_kwh=260.0),
        ]
    )
    svc = RecommendationService(
        config=_config(),
        estimator=_FakeEstimator(),
        forecast=_FakeForecast(),
        purchases=reader,
    )
    data = svc.build(_live_state(), objective=0.5)
    assert data.month_spend == 1500.0  # May purchase excluded
    # projected = (100 kWh / 22 days) * 30 days * 3.56 R/kWh, energy only (no fixed charge)
    expected = (100.0 / 22.0) * 30.0 * 3.56
    assert round(data.month_projected_cost, 2) == round(expected, 2)
    assert round(data.month_balance, 2) == round(1500.0 - expected, 2)


def test_month_projection_zero_without_reader():
    svc = RecommendationService(
        config=_config(), estimator=_FakeEstimator(), forecast=_FakeForecast()
    )
    data = svc.build(_live_state(), objective=0.5)
    assert data.month_spend == 0.0
```
(Note: `_FakeReader.list_since(cutoff)` returns purchases with `purchased_at >= cutoff`. The service must still filter to the same month/year so a cutoff of the 1st can't leak — here all are ≥ cutoff anyway, so the May one is excluded by the month filter.)

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_recommendation_service.py -k month_projection -v`
Expected: FAIL — no `month_spend`.

- [ ] **Step 3: Implement.** In `services/recommendation.py`:

Import the reader protocol:
```python
from solar_advisor.tariff.provider import PurchaseReader, TariffProvider
```

Add fields to `DashboardData` (after `expected_pv_kwh_tomorrow: float`):
```python
    expected_pv_kwh_tomorrow: float
    month_spend: float
    month_projected_cost: float
    month_balance: float
    disclaimer: str
```

Add the `purchases` param to `__init__`:
```python
    def __init__(
        self,
        config: AppConfig,
        estimator: _Estimator,
        forecast: ForecastProvider,
        tariff_provider: TariffProvider | None = None,
        purchases: PurchaseReader | None = None,
    ) -> None:
        self._config = config
        self._estimator = estimator
        self._forecast = forecast
        self._tariff_provider = tariff_provider
        self._purchases = purchases
```

In `build()`, after `days_in_month = ...` and the `rec = recommend(...)` block (and after `conversion_power` is computed), add:
```python
        today = telemetry.ts.date()
        first_of_month = today.replace(day=1)
        month_spend = (
            sum(
                p.rand
                for p in self._purchases.list_since(first_of_month)
                if p.purchased_at.year == today.year and p.purchased_at.month == today.month
            )
            if self._purchases is not None
            else 0.0
        )
        month_projected_cost = (
            telemetry.month_to_date_grid_import_kwh / today.day * days_in_month * derived.rate
        )
        month_balance = month_spend - month_projected_cost
```

Add the three to the returned `DashboardData(...)` (after `expected_pv_kwh_tomorrow=...`):
```python
            expected_pv_kwh_tomorrow=forecast.expected_pv_kwh_tomorrow,
            month_spend=month_spend,
            month_projected_cost=month_projected_cost,
            month_balance=month_balance,
```

In `api/schemas.py`, add to `DashboardView` (after `expected_pv_kwh_tomorrow: float`):
```python
    expected_pv_kwh_tomorrow: float
    month_spend: float
    month_projected_cost: float
    month_balance: float
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_recommendation_service.py -k month_projection -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/solar_advisor/services/recommendation.py src/solar_advisor/api/schemas.py tests/test_recommendation_service.py
git commit -m "feat: compute prepaid month projection (energy only) on dashboard data"
```

### Task 5: Surface projection in `_to_view`; wire the reader

**Files:** Modify `src/solar_advisor/api/app.py`; Test `tests/test_api.py`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_api.py`). The `_client` helper overrides `get_service` with a service built from `_config()` + fakes — to exercise the projection, pass a purchase reader into that service. Easiest: add a dedicated test that builds the service with a reader and a small fake purchase store, OR assert the fields are present + numeric on the existing client. Minimum viable:
```python
def test_dashboard_view_includes_month_projection_fields():
    body = _client(_ready_state()).get("/api/dashboard?objective=0.5").json()
    assert "month_spend" in body
    assert "month_projected_cost" in body
    assert "month_balance" in body
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_api.py -k month_projection -v`
Expected: FAIL — keys missing / `DashboardView` validation error.

- [ ] **Step 3: Implement.** In `api/app.py` `_to_view`, add after `expected_pv_kwh_tomorrow=...`:
```python
        expected_pv_kwh_tomorrow=round(data.expected_pv_kwh_tomorrow, 2),
        month_spend=round(data.month_spend),
        month_projected_cost=round(data.month_projected_cost),
        month_balance=round(data.month_balance),
```
And in `create_production_app()`, pass the purchase reader to the service (it already builds `purchase_store`):
```python
    service = RecommendationService(
        config=config,
        estimator=estimator,
        forecast=forecast,
        tariff_provider=tariff_provider,
        purchases=purchase_store,
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_api.py -k month_projection -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/solar_advisor/api/app.py tests/test_api.py
git commit -m "feat: surface month projection on /api/dashboard; wire purchase reader"
```

---

## Group 3 — Full gate

### Task 6: Gate — tests, lint, types, import contract

- [ ] **Step 1:** `.venv/bin/pytest -q` — all green. NOTE: the new required `DashboardData` fields will break the `DashboardData(...)` fixture in `tests/test_explain_context.py` — add `month_spend=0.0, month_projected_cost=0.0, month_balance=0.0` to that fixture (same pattern as the earlier `conversion_power`/`tariff_source` fixes). Fix and re-run.
- [ ] **Step 2:** `.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy && .venv/bin/lint-imports --config .importlinter` — all clean. Engine-purity contract must still hold (the forecast provider is in `forecast/`, config imports it — neither is `engine`).
- [ ] **Step 3:** Fix anything failing; re-run until clean.
- [ ] **Step 4:** Commit fixes: `git add -A && git commit -m "chore: satisfy gates for forecast/projection backend"`.

---

## Self-Review

**Spec coverage:** J1 forecast provider (split-array sum, cache, fallback, source switch, config, compose) → Tasks 1–3; J2 month projection (energy only, no fixed charge, spend from month purchases, run-rate projection, balance) → Tasks 4–5. ✓

**Placeholder scan:** none — complete code/commands throughout.

**Type consistency:** `PvArray(tilt, azimuth, kwp)` defined once in the provider, imported by config + wiring; `ForecastSolarProvider` constructed with the same kwargs in the test and in `create_production_app`; `month_spend`/`month_projected_cost`/`month_balance` flow `DashboardData` → `DashboardView` → `_to_view`; `PurchaseReader.list_since(date)` reused for the month sum; `forecast_source` default `"static"` keeps current behaviour until opted in. ✓
