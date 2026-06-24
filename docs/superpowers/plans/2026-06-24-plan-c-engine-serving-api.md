# Plan C — Live Ingest + Engine-Serving Read API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a FastAPI backend that maintains live inverter state (telemetry + the 6-slot schedule) from MQTT, loads configuration, and exposes read-only JSON endpoints that run the deterministic engine on real data — including the cost↔resilience slider — every response carrying the advisory-only disclaimer.

**Architecture:** A background task in the API process runs a read-only MQTT subscription that updates an in-memory `LiveState` (latest `Telemetry` + latest `Schedule`) and persists telemetry to the existing SQLite store. A `RecommendationService` assembles the engine's plain-value inputs from `LiveState` + the `ParameterEstimator` + a `ForecastProvider` + `AppConfig`, then calls the pure engine (`assess_schedule`, `recommend`). FastAPI exposes the results. No LLM here (that is Plan D); no writes to the inverter, ever.

**Tech Stack:** Python 3.12+, FastAPI + uvicorn, `httpx` (HA forecast + TestClient), the existing `aiomqtt` ingest, `pytest` + `pytest-asyncio`, `ruff`, `mypy --strict`, `import-linter`. The `engine` package stays pure (contract unchanged).

**Covers spec stages:** 5 (dashboard data + slider, backend half), 7 (advisory disclaimer), 9 (forecast adapter), and the §1 goal-2/4 data surface. See `docs/superpowers/specs/2026-06-22-solar-advisor-design.md` §§3.1, 5, 7, 9.

**Builds on `main`:** `domain.telemetry.Telemetry`, `domain.schedule.{Slot, build_schedule}`, `ingest.{topic_map, deye_adapter, safety, mqtt_client}`, `storage.{store.TelemetryStore, sqlite_store.SqliteTelemetryStore}`, `engine.{inputs, tariff, battery, objective, schedule_eval, optimize}`, `estimation.estimator.ParameterEstimator`, `forecast.provider.ForecastProvider`.

---

## Modelling decisions (deliberate MVP choices)

- **The API process owns the live MQTT subscription** (read-only) and updates `LiveState` + persists telemetry. The standalone `collector.py` from Plan A remains a valid headless persister but is not required when the API runs. Two read-only subscriptions are harmless.
- **Battery power limits and SOC floor come from `AppConfig`** (seeded from the discovered dump: floor 20%, max charge ≈ 7950 W from 150 A × ~53 V), not from ingesting the inverter's settings topics. Settings ingestion is a future enhancement; the values are stable config.
- **`usable_kwh` and `daily_kwh` come from `ParameterEstimator`** (Plan B), reading the SQLite history, with a nominal fallback (15 kWh) and an `essential_power_w` config default (≈ 1136 W from the dump) until a dedicated estimator exists.
- **Forecast** has two adapters behind the `ForecastProvider` interface: a `StaticForecastProvider` (config kWh values, the default) and a `HomeAssistantForecastProvider` (reads Forecast.Solar sensors over HA's REST API). The engine consumes the returned `SolarForecast` either way.
- **Read-only:** no endpoint and no client in this plan can write to the inverter. The MQTT subscription reuses `ReadOnlyMqttClient`'s no-publish guarantee.

---

## File structure (created/modified by this plan)

```
backend/
├─ pyproject.toml                                  # MODIFY: add fastapi, uvicorn, httpx
├─ Dockerfile.api                                  # NEW: API image
├─ docker-compose.yml                              # MODIFY: add `api` service
├─ src/solar_advisor/
│  ├─ config.py                                    # NEW: AppConfig + load_config()
│  ├─ ingest/
│  │  ├─ schedule_topics.py                        # NEW: SCHEDULE_TOPICS + parse_schedule_value
│  │  ├─ schedule_accumulator.py                   # NEW: ScheduleAccumulator → Schedule
│  │  └─ live.py                                   # NEW: LiveState + run_live_ingest()
│  ├─ forecast/
│  │  ├─ static_provider.py                        # NEW: StaticForecastProvider
│  │  └─ ha_provider.py                            # NEW: HomeAssistantForecastProvider
│  ├─ services/
│  │  ├─ __init__.py                               # NEW
│  │  └─ recommendation.py                         # NEW: DashboardData + RecommendationService
│  └─ api/
│     ├─ __init__.py                               # NEW
│     ├─ schemas.py                                # NEW: response models (Pydantic)
│     └─ app.py                                    # NEW: FastAPI app, lifespan, endpoints
└─ tests/
   ├─ test_config.py
   ├─ test_schedule_ingest.py
   ├─ test_forecast_providers.py
   ├─ test_recommendation_service.py
   └─ test_api.py
```

Tooling runs via the self-contained Makefile: `cd backend && make check`. The `engine`-purity import-linter contract is unchanged — `api`, `services`, `ingest`, `forecast` may import `engine`, never the reverse.

---

## Task 1: Add web dependencies

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add runtime + dev deps**

In `[project].dependencies`, add `"fastapi>=0.115"`, `"uvicorn>=0.30"`, `"httpx>=0.27"`. In `[project.optional-dependencies].dev`, add `"pytest-asyncio>=0.24"` (already present from Plan A — leave if so).

- [ ] **Step 2: Install and confirm baseline still green**

Run: `cd backend && .venv/bin/python -m pip install -e ".[dev]" && make check`
Expected: deps install; ruff + mypy + import-linter + pytest all green (63 tests).

- [ ] **Step 3: Commit**

```bash
git add backend/pyproject.toml
git commit -m "build: add fastapi, uvicorn, httpx for the API layer"
```

---

## Task 2: Application config

**Files:**
- Create: `backend/src/solar_advisor/config.py`
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: solar_advisor.config`.

- [ ] **Step 3: Write the implementation**

```python
# src/solar_advisor/config.py
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time


def _parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Configuration the engine needs that does not come from the inverter
    (spec §2 ASK-ME) plus stable battery limits and the live-ingest connection."""

    # Tariff (ask-me)
    tariff_rate: float            # R/kWh (flat marginal)
    tariff_fixed_charge: float    # R/month (sunk)
    # Battery limits (stable; seeded from the discovered dump)
    battery_nominal_kwh: float
    battery_soc_floor_pct: float
    max_charge_power_w: float
    max_discharge_power_w: float
    # Load / daylight / objective
    essential_power_w: float
    daylight_dawn: time
    daylight_dusk: time
    objective_default: float
    # MQTT (reuse the collector's env)
    mqtt_host: str
    mqtt_port: int
    mqtt_user: str | None
    mqtt_pass: str | None
    db_path: str
    # Forecast (static fallback values, kWh)
    forecast_today_kwh: float
    forecast_tomorrow_kwh: float


def load_config() -> AppConfig:
    o = float(os.environ.get("SA_OBJECTIVE_DEFAULT", "0.5"))
    return AppConfig(
        tariff_rate=float(os.environ.get("SA_TARIFF_RATE", "3.56")),
        tariff_fixed_charge=float(os.environ.get("SA_TARIFF_FIXED_CHARGE", "600")),
        battery_nominal_kwh=float(os.environ.get("SA_BATTERY_NOMINAL_KWH", "15")),
        battery_soc_floor_pct=float(os.environ.get("SA_BATTERY_SOC_FLOOR_PCT", "20")),
        max_charge_power_w=float(os.environ.get("SA_MAX_CHARGE_POWER_W", "7950")),
        max_discharge_power_w=float(os.environ.get("SA_MAX_DISCHARGE_POWER_W", "7950")),
        essential_power_w=float(os.environ.get("SA_ESSENTIAL_POWER_W", "1136")),
        daylight_dawn=_parse_hhmm(os.environ.get("SA_DAYLIGHT_DAWN", "07:00")),
        daylight_dusk=_parse_hhmm(os.environ.get("SA_DAYLIGHT_DUSK", "17:30")),
        objective_default=min(1.0, max(0.0, o)),
        mqtt_host=os.environ.get("SA_MQTT_HOST", "localhost"),
        mqtt_port=int(os.environ.get("SA_MQTT_PORT", "1883")),
        mqtt_user=os.environ.get("SA_MQTT_USER") or None,
        mqtt_pass=os.environ.get("SA_MQTT_PASS") or None,
        db_path=os.environ.get("SA_DB_PATH", "solar_advisor.db"),
        forecast_today_kwh=float(os.environ.get("SA_FORECAST_TODAY_KWH", "20")),
        forecast_tomorrow_kwh=float(os.environ.get("SA_FORECAST_TOMORROW_KWH", "20")),
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_config.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/solar_advisor/config.py backend/tests/test_config.py
git commit -m "feat: application config from environment"
```

---

## Task 3: Schedule topic map & accumulator

**Files:**
- Create: `backend/src/solar_advisor/ingest/schedule_topics.py`
- Create: `backend/src/solar_advisor/ingest/schedule_accumulator.py`
- Test: `backend/tests/test_schedule_ingest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_schedule_ingest.py
from datetime import time

from solar_advisor.domain.schedule import Slot
from solar_advisor.ingest.schedule_accumulator import ScheduleAccumulator
from solar_advisor.ingest.schedule_topics import parse_schedule_value


def test_parse_schedule_value_known_topics():
    assert parse_schedule_value("solar_assistant/inverter_1/time_point_3/state", "08:00") == (
        "time_point", 3, "08:00",
    )
    assert parse_schedule_value("solar_assistant/inverter_1/capacity_point_4/state", "95") == (
        "capacity_point", 4, "95",
    )
    assert parse_schedule_value("solar_assistant/inverter_1/grid_charge_point_1/state", "true") == (
        "grid_charge_point", 1, "true",
    )


def test_parse_schedule_value_ignores_other_topics():
    assert parse_schedule_value("solar_assistant/inverter_1/pv_power/state", "100") is None


def _feed_live_schedule(acc):
    raw = {
        "time_point": {1: "00:00", 2: "05:00", 3: "08:00", 4: "16:30", 5: "18:00", 6: "21:30"},
        "capacity_point": {1: "65", 2: "65", 3: "90", 4: "95", 5: "75", 6: "65"},
        "grid_charge_point": {1: "true", 2: "true", 3: "true", 4: "false", 5: "true", 6: "true"},
        "gen_charge_point": {i: "false" for i in range(1, 7)},
    }
    last = None
    for field, slots in raw.items():
        for i, val in slots.items():
            last = acc.ingest(f"solar_assistant/inverter_1/{field}_{i}/state", val)
    return last


def test_accumulator_emits_schedule_once_complete():
    acc = ScheduleAccumulator()
    schedule = _feed_live_schedule(acc)
    assert schedule is not None
    assert len(schedule) == 6
    assert schedule[0] == Slot(
        start=time(0, 0), end=time(5, 0), target_soc=65, grid_charge=True, gen_charge=False,
    )
    assert schedule[3].grid_charge is False  # 16:30 PV-peak slot


def test_accumulator_returns_none_until_complete():
    acc = ScheduleAccumulator()
    assert acc.ingest("solar_assistant/inverter_1/time_point_1/state", "00:00") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_schedule_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write `schedule_topics.py`**

```python
# src/solar_advisor/ingest/schedule_topics.py
from __future__ import annotations

import re

# The four per-slot schedule fields (i = 1..6). All vendor-specific knowledge
# for the TOU schedule lives here (spec §3.1).
SCHEDULE_FIELDS = ("time_point", "capacity_point", "grid_charge_point", "gen_charge_point")

_PATTERN = re.compile(
    r"^solar_assistant/inverter_1/(time_point|capacity_point|grid_charge_point|gen_charge_point)_([1-6])/state$"
)


def parse_schedule_value(topic: str, payload: str) -> tuple[str, int, str] | None:
    """Map a schedule topic to (field, slot_index, raw_payload). None if not a
    schedule topic. The payload stays raw; build_schedule does the typing."""
    match = _PATTERN.match(topic)
    if match is None:
        return None
    return match.group(1), int(match.group(2)), payload
```

- [ ] **Step 4: Write `schedule_accumulator.py`**

```python
# src/solar_advisor/ingest/schedule_accumulator.py
from __future__ import annotations

from typing import Any

from solar_advisor.domain.schedule import Slot, build_schedule
from solar_advisor.ingest.schedule_topics import SCHEDULE_FIELDS, parse_schedule_value

_BOOL_FIELDS = {"grid_charge_point", "gen_charge_point"}


class ScheduleAccumulator:
    """Collects the 24 schedule topic values and emits a Schedule once every
    field/slot is present. Returns None until then."""

    def __init__(self) -> None:
        self._raw: dict[str, dict[int, Any]] = {field: {} for field in SCHEDULE_FIELDS}

    def ingest(self, topic: str, payload: str) -> list[Slot] | None:
        parsed = parse_schedule_value(topic, payload)
        if parsed is None:
            return None
        field, slot, raw = parsed
        if field in _BOOL_FIELDS:
            self._raw[field][slot] = raw.strip().lower() == "true"
        else:
            self._raw[field][slot] = raw
        if not self._is_complete():
            return None
        return build_schedule(self._raw)

    def _is_complete(self) -> bool:
        return all(len(self._raw[field]) == 6 for field in SCHEDULE_FIELDS)
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_schedule_ingest.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/src/solar_advisor/ingest/schedule_topics.py backend/src/solar_advisor/ingest/schedule_accumulator.py backend/tests/test_schedule_ingest.py
git commit -m "feat(ingest): 6-slot schedule topic map and accumulator"
```

---

## Task 4: Forecast providers

**Files:**
- Create: `backend/src/solar_advisor/forecast/static_provider.py`
- Create: `backend/src/solar_advisor/forecast/ha_provider.py`
- Test: `backend/tests/test_forecast_providers.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_forecast_providers.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write `static_provider.py`**

```python
# src/solar_advisor/forecast/static_provider.py
from __future__ import annotations

from dataclasses import dataclass

from solar_advisor.engine.inputs import SolarForecast


@dataclass(frozen=True, slots=True)
class StaticForecastProvider:
    """Config-driven forecast. The default until the HA feed is wired (spec §9)."""

    today_kwh: float
    tomorrow_kwh: float

    def fetch(self) -> SolarForecast:
        return SolarForecast(
            expected_pv_kwh_today=self.today_kwh,
            expected_pv_kwh_tomorrow=self.tomorrow_kwh,
        )
```

- [ ] **Step 4: Write `ha_provider.py`**

```python
# src/solar_advisor/forecast/ha_provider.py
from __future__ import annotations

import httpx

from solar_advisor.engine.inputs import SolarForecast

_TODAY_ENTITY = "sensor.energy_production_today"
_TOMORROW_ENTITY = "sensor.energy_production_tomorrow"


class HomeAssistantForecastProvider:
    """Reads the existing Home Assistant Forecast.Solar sensors over HA's REST
    API, reusing the user's forecast feed rather than a second dependency (spec §9)."""

    def __init__(self, client: httpx.Client, token: str) -> None:
        self._client = client
        self._headers = {"Authorization": f"Bearer {token}"}

    def _read(self, entity: str) -> float:
        resp = self._client.get(f"/api/states/{entity}", headers=self._headers)
        resp.raise_for_status()
        return float(resp.json()["state"])

    def fetch(self) -> SolarForecast:
        return SolarForecast(
            expected_pv_kwh_today=self._read(_TODAY_ENTITY),
            expected_pv_kwh_tomorrow=self._read(_TOMORROW_ENTITY),
        )
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_forecast_providers.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/src/solar_advisor/forecast/static_provider.py backend/src/solar_advisor/forecast/ha_provider.py backend/tests/test_forecast_providers.py
git commit -m "feat(forecast): static and Home Assistant forecast providers"
```

---

## Task 5: Live state + background ingest

The API process subscribes read-only to MQTT, routing each message to the telemetry adapter and the schedule accumulator, updating in-memory `LiveState` and persisting telemetry.

**Files:**
- Create: `backend/src/solar_advisor/ingest/live.py`
- Test: `backend/tests/test_live_ingest.py`

- [ ] **Step 1: Write the failing test (no broker — drive the handler directly)**

```python
# tests/test_live_ingest.py
from datetime import UTC, datetime, timedelta

from solar_advisor.ingest.live import LiveState
from solar_advisor.storage.sqlite_store import SqliteTelemetryStore
from tests.conftest import make_telemetry

ALL_TELEMETRY = {
    "solar_assistant/total/battery_state_of_charge/state": "64",
    "solar_assistant/total/battery_power/state": "85",
    "solar_assistant/inverter_1/battery_voltage/state": "50.0",
    "solar_assistant/inverter_1/battery_current/state": "1.7",
    "solar_assistant/inverter_1/pv_power/state": "106",
    "solar_assistant/inverter_1/grid_power/state": "1140",
    "solar_assistant/inverter_1/load_power/state": "1086",
    "solar_assistant/inverter_1/load_power_essential/state": "1136",
    "solar_assistant/total/grid_energy_in/state": "1000",
    "solar_assistant/total/grid_energy_out/state": "0",
    "solar_assistant/total/pv_energy/state": "0",
    "solar_assistant/total/load_energy/state": "0",
    "solar_assistant/total/battery_energy_in/state": "0",
    "solar_assistant/total/battery_energy_out/state": "0",
}


def test_live_state_updates_telemetry_and_persists(tmp_path):
    store = SqliteTelemetryStore(tmp_path / "live.db", min_interval=timedelta(0))
    state = LiveState(store=store)
    ts = datetime(2026, 6, 22, 8, 0, tzinfo=UTC)
    for topic, payload in ALL_TELEMETRY.items():
        state.handle(ts, topic, payload)
    assert state.telemetry is not None
    assert state.telemetry.battery_soc == 64.0
    # Persisted to the store.
    rows = store.query_range(ts - timedelta(minutes=1), ts + timedelta(minutes=1))
    assert len(rows) == 1


def test_live_state_updates_schedule():
    state = LiveState(store=None)
    raw = {
        "time_point": {1: "00:00", 2: "05:00", 3: "08:00", 4: "16:30", 5: "18:00", 6: "21:30"},
        "capacity_point": {1: "65", 2: "65", 3: "90", 4: "95", 5: "75", 6: "65"},
        "grid_charge_point": {1: "true", 2: "true", 3: "true", 4: "false", 5: "true", 6: "true"},
        "gen_charge_point": {i: "false" for i in range(1, 7)},
    }
    ts = datetime(2026, 6, 22, 8, 0, tzinfo=UTC)
    for field, slots in raw.items():
        for i, val in slots.items():
            state.handle(ts, f"solar_assistant/inverter_1/{field}_{i}/state", val)
    assert state.schedule is not None
    assert len(state.schedule) == 6


def test_live_state_ignores_write_topics():
    import pytest

    from solar_advisor.ingest.safety import WriteAttemptError

    state = LiveState(store=None)
    with pytest.raises(WriteAttemptError):
        state.handle(datetime.now(UTC), "solar_assistant/inverter_1/max_charge_current/set", "150")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_live_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write `live.py`**

```python
# src/solar_advisor/ingest/live.py
from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

import aiomqtt

from solar_advisor.domain.schedule import Slot
from solar_advisor.domain.telemetry import Telemetry
from solar_advisor.ingest.deye_adapter import DeyeAdapter
from solar_advisor.ingest.safety import assert_read_only
from solar_advisor.ingest.schedule_accumulator import ScheduleAccumulator
from solar_advisor.storage.store import TelemetryStore


class LiveState:
    """Holds the latest telemetry snapshot and schedule, updated from MQTT.
    Read-only against the inverter: every topic is asserted read-only, and
    persistence reuses the store's append-only API (spec §7)."""

    def __init__(self, store: TelemetryStore | None) -> None:
        self._store = store
        self._telemetry_adapter = DeyeAdapter()
        self._schedule_adapter = ScheduleAccumulator()
        self.telemetry: Telemetry | None = None
        self.schedule: list[Slot] | None = None

    def handle(self, ts: datetime, topic: str, payload: str) -> None:
        assert_read_only(topic)  # never act on a write topic
        snapshot = self._telemetry_adapter.ingest(ts, topic, payload)
        if snapshot is not None:
            self.telemetry = snapshot
            if self._store is not None:
                self._store.save(snapshot)
            return
        schedule = self._schedule_adapter.ingest(topic, payload)
        if schedule is not None:
            self.schedule = schedule


async def run_live_ingest(
    state: LiveState,
    *,
    host: str,
    port: int,
    username: str | None,
    password: str | None,
    max_backoff: float = 30.0,
) -> None:
    """Background loop: subscribe read-only and feed messages into LiveState.
    Reconnects with backoff, like the collector."""
    backoff = 1.0
    while True:
        try:
            async with aiomqtt.Client(
                hostname=host, port=port, username=username, password=password
            ) as client:
                await client.subscribe("solar_assistant/#")
                async for message in client.messages:
                    payload = (
                        message.payload.decode(errors="replace")
                        if isinstance(message.payload, bytes)
                        else str(message.payload)
                    )
                    state.handle(datetime.now(UTC), str(message.topic), payload)
                    backoff = 1.0
        except aiomqtt.MqttError as exc:
            print(f"live-ingest: connection lost ({exc}); retry in {backoff:.0f}s", file=sys.stderr)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_live_ingest.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/solar_advisor/ingest/live.py backend/tests/test_live_ingest.py
git commit -m "feat(ingest): in-memory live state with read-only MQTT loop"
```

---

## Task 6: Recommendation service

Assembles the engine's plain-value inputs from `LiveState` + estimator + forecast + config, runs the pure engine, and returns a `DashboardData` DTO.

**Files:**
- Create: `backend/src/solar_advisor/services/__init__.py` (empty)
- Create: `backend/src/solar_advisor/services/recommendation.py`
- Test: `backend/tests/test_recommendation_service.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_recommendation_service.py
from datetime import UTC, datetime, time

from solar_advisor.config import AppConfig
from solar_advisor.domain.schedule import build_schedule
from solar_advisor.engine.inputs import SolarForecast
from solar_advisor.estimation.estimator import EstimatedParameters
from solar_advisor.ingest.live import LiveState
from solar_advisor.services.recommendation import DashboardData, RecommendationService
from tests.conftest import make_telemetry


class _FakeEstimator:
    def estimate(self, start, end):
        return EstimatedParameters(
            usable_kwh=15.0, usable_kwh_confidence=0.6,
            daily_consumption_kwh=20.0, daily_consumption_confidence=0.5,
        )


class _FakeForecast:
    def fetch(self):
        return SolarForecast(expected_pv_kwh_today=8.0, expected_pv_kwh_tomorrow=8.0)


def _config():
    return AppConfig(
        tariff_rate=3.56, tariff_fixed_charge=600.0, battery_nominal_kwh=15.0,
        battery_soc_floor_pct=20.0, max_charge_power_w=7950.0, max_discharge_power_w=7950.0,
        essential_power_w=1136.0, daylight_dawn=time(7, 0), daylight_dusk=time(17, 30),
        objective_default=0.5, mqtt_host="x", mqtt_port=1883, mqtt_user=None, mqtt_pass=None,
        db_path=":memory:", forecast_today_kwh=8.0, forecast_tomorrow_kwh=8.0,
    )


def _live_state():
    state = LiveState(store=None)
    state.telemetry = make_telemetry(
        datetime(2026, 6, 22, 8, 0, tzinfo=UTC), battery_soc=30.0,
        month_to_date_grid_import_kwh=100.0,
    )
    state.schedule = build_schedule({
        "time_point": {1: "00:00", 2: "05:00", 3: "08:00", 4: "16:30", 5: "18:00", 6: "21:30"},
        "capacity_point": {1: 65, 2: 65, 3: 90, 4: 95, 5: 75, 6: 65},
        "grid_charge_point": {1: True, 2: True, 3: True, 4: False, 5: True, 6: True},
        "gen_charge_point": {i: False for i in range(1, 7)},
    })
    return state


def test_build_dashboard_runs_engine():
    svc = RecommendationService(
        config=_config(), estimator=_FakeEstimator(), forecast=_FakeForecast(),
    )
    data = svc.build(_live_state(), objective=1.0)
    assert isinstance(data, DashboardData)
    assert len(data.slot_assessments) == 6
    assert data.recommendation.reserve_target_soc == 100.0
    assert data.recommendation.enable_overnight_grid_charge is True
    assert data.usable_kwh_confidence == 0.6


def test_objective_defaults_to_config_when_none():
    svc = RecommendationService(
        config=_config(), estimator=_FakeEstimator(), forecast=_FakeForecast(),
    )
    data = svc.build(_live_state(), objective=None)
    assert data.objective == 0.5  # config default
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_recommendation_service.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
# src/solar_advisor/services/recommendation.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from solar_advisor.config import AppConfig
from solar_advisor.domain.telemetry import Telemetry
from solar_advisor.engine.battery import BatteryModel
from solar_advisor.engine.inputs import DaylightWindow, LoadProfile
from solar_advisor.engine.optimize import Recommendation, recommend
from solar_advisor.engine.schedule_eval import SlotAssessment, assess_schedule
from solar_advisor.engine.tariff import FlatRateTariff
from solar_advisor.estimation.estimator import EstimatedParameters
from solar_advisor.forecast.provider import ForecastProvider
from solar_advisor.ingest.live import LiveState

ADVISORY_DISCLAIMER = (
    "Advisory only. This app is read-only against your inverter; apply any "
    "changes yourself."
)


@dataclass(frozen=True, slots=True)
class DashboardData:
    """Everything the dashboard (and, in Plan D, the LLM) needs — all numbers
    computed by the deterministic engine."""

    telemetry: Telemetry
    objective: float
    slot_assessments: list[SlotAssessment]
    recommendation: Recommendation
    usable_kwh: float
    usable_kwh_confidence: float
    daily_consumption_kwh: float
    daily_consumption_confidence: float
    disclaimer: str


class _Estimator(Protocol):  # structural protocol for the estimator dependency
    def estimate(self, start: datetime, end: datetime) -> EstimatedParameters: ...


class RecommendationService:
    """Assembles engine inputs from live data + estimates + forecast + config,
    then runs the pure engine."""

    def __init__(
        self, config: AppConfig, estimator: _Estimator, forecast: ForecastProvider
    ) -> None:
        self._config = config
        self._estimator = estimator
        self._forecast = forecast

    def build(self, state: LiveState, objective: float | None) -> DashboardData:
        if state.telemetry is None or state.schedule is None:
            raise LookupError("live state not ready: telemetry or schedule missing")

        cfg = self._config
        obj = cfg.objective_default if objective is None else min(1.0, max(0.0, objective))
        telemetry = state.telemetry

        est = self._estimator.estimate(
            telemetry.ts - timedelta(days=14), telemetry.ts
        )
        usable_kwh = est.usable_kwh or cfg.battery_nominal_kwh
        daily_kwh = est.daily_consumption_kwh or 0.0

        battery = BatteryModel(
            usable_kwh=usable_kwh,
            soc_floor_pct=cfg.battery_soc_floor_pct,
            max_charge_power_w=cfg.max_charge_power_w,
            max_discharge_power_w=cfg.max_discharge_power_w,
        )
        tariff = FlatRateTariff(
            energy_rate=cfg.tariff_rate, monthly_fixed_charge=cfg.tariff_fixed_charge
        )
        forecast = self._forecast.fetch()
        load = LoadProfile(daily_kwh=daily_kwh, essential_power_w=cfg.essential_power_w)
        daylight = DaylightWindow(dawn=cfg.daylight_dawn, dusk=cfg.daylight_dusk)

        assessments = assess_schedule(
            state.schedule, battery, tariff, forecast, load, daylight,
            start_soc=telemetry.battery_soc,
            month_to_date_import_kwh=telemetry.month_to_date_grid_import_kwh,
        )
        rec = recommend(
            battery=battery, tariff=tariff, forecast=forecast, load=load, objective=obj,
            current_soc=telemetry.battery_soc,
            month_to_date_import_kwh=telemetry.month_to_date_grid_import_kwh,
            days_in_month=30,
        )
        return DashboardData(
            telemetry=telemetry,
            objective=obj,
            slot_assessments=assessments,
            recommendation=rec,
            usable_kwh=usable_kwh,
            usable_kwh_confidence=est.usable_kwh_confidence,
            daily_consumption_kwh=daily_kwh,
            daily_consumption_confidence=est.daily_consumption_confidence,
            disclaimer=ADVISORY_DISCLAIMER,
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_recommendation_service.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/solar_advisor/services/__init__.py backend/src/solar_advisor/services/recommendation.py backend/tests/test_recommendation_service.py
git commit -m "feat(services): recommendation service wiring live data into the engine"
```

---

## Task 7: FastAPI app & endpoints

**Files:**
- Create: `backend/src/solar_advisor/api/__init__.py` (empty)
- Create: `backend/src/solar_advisor/api/schemas.py`
- Create: `backend/src/solar_advisor/api/app.py`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: Write the response schemas**

```python
# src/solar_advisor/api/schemas.py
from __future__ import annotations

from pydantic import BaseModel


class SlotView(BaseModel):
    start: str
    end: str
    target_soc: int
    grid_charge: bool
    behavior: str
    end_soc: float
    grid_import_kwh: float
    cost: float


class RecommendationView(BaseModel):
    reserve_target_soc: float
    enable_overnight_grid_charge: bool
    grid_charge_kwh: float
    expected_daily_grid_import_kwh: float
    expected_daily_cost: float
    backup_hours: float
    monthly_cost_so_far: float


class DashboardView(BaseModel):
    objective: float
    battery_soc: float
    pv_power: float
    grid_power: float
    load_power: float
    month_to_date_grid_import_kwh: float
    usable_kwh: float
    usable_kwh_confidence: float
    daily_consumption_kwh: float
    daily_consumption_confidence: float
    slots: list[SlotView]
    recommendation: RecommendationView
    disclaimer: str
```

- [ ] **Step 2: Write the failing test (uses dependency override; no broker)**

```python
# tests/test_api.py
from datetime import UTC, datetime, time

from fastapi.testclient import TestClient

from solar_advisor.api.app import build_app, get_service
from solar_advisor.config import AppConfig
from solar_advisor.domain.schedule import build_schedule
from solar_advisor.engine.inputs import SolarForecast
from solar_advisor.estimation.estimator import EstimatedParameters
from solar_advisor.ingest.live import LiveState
from solar_advisor.services.recommendation import RecommendationService
from tests.conftest import make_telemetry


class _FakeEstimator:
    def estimate(self, start, end):
        return EstimatedParameters(15.0, 0.6, 20.0, 0.5)


class _FakeForecast:
    def fetch(self):
        return SolarForecast(8.0, 8.0)


def _config():
    return AppConfig(
        tariff_rate=3.56, tariff_fixed_charge=600.0, battery_nominal_kwh=15.0,
        battery_soc_floor_pct=20.0, max_charge_power_w=7950.0, max_discharge_power_w=7950.0,
        essential_power_w=1136.0, daylight_dawn=time(7, 0), daylight_dusk=time(17, 30),
        objective_default=0.5, mqtt_host="x", mqtt_port=1883, mqtt_user=None, mqtt_pass=None,
        db_path=":memory:", forecast_today_kwh=8.0, forecast_tomorrow_kwh=8.0,
    )


def _ready_state():
    state = LiveState(store=None)
    state.telemetry = make_telemetry(
        datetime(2026, 6, 22, 8, 0, tzinfo=UTC), battery_soc=30.0,
        month_to_date_grid_import_kwh=100.0,
    )
    state.schedule = build_schedule({
        "time_point": {1: "00:00", 2: "05:00", 3: "08:00", 4: "16:30", 5: "18:00", 6: "21:30"},
        "capacity_point": {1: 65, 2: 65, 3: 90, 4: 95, 5: 75, 6: 65},
        "grid_charge_point": {1: True, 2: True, 3: True, 4: False, 5: True, 6: True},
        "gen_charge_point": {i: False for i in range(1, 7)},
    })
    return state


def _client(state):
    app = build_app(state=state)
    svc = RecommendationService(config=_config(), estimator=_FakeEstimator(), forecast=_FakeForecast())
    app.dependency_overrides[get_service] = lambda: svc
    return TestClient(app)


def test_health_ok():
    assert _client(_ready_state()).get("/api/health").status_code == 200


def test_dashboard_returns_engine_output_with_disclaimer():
    resp = _client(_ready_state()).get("/api/dashboard?objective=1.0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["objective"] == 1.0
    assert len(body["slots"]) == 6
    assert body["recommendation"]["reserve_target_soc"] == 100.0
    assert "read-only" in body["disclaimer"].lower()


def test_dashboard_503_when_state_not_ready():
    resp = _client(LiveState(store=None)).get("/api/dashboard")
    assert resp.status_code == 503
```

- [ ] **Step 3: Write `app.py`**

```python
# src/solar_advisor/api/app.py
from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from solar_advisor.api.schemas import DashboardView, RecommendationView, SlotView
from solar_advisor.config import AppConfig, load_config
from solar_advisor.estimation.estimator import ParameterEstimator
from solar_advisor.forecast.static_provider import StaticForecastProvider
from solar_advisor.ingest.live import LiveState, run_live_ingest
from solar_advisor.services.recommendation import DashboardData, RecommendationService
from solar_advisor.storage.sqlite_store import SqliteTelemetryStore

# Module-level handles set in the lifespan; overridable in tests.
_STATE: LiveState | None = None
_SERVICE: RecommendationService | None = None


def get_service() -> RecommendationService:
    if _SERVICE is None:
        raise HTTPException(status_code=500, detail="service not initialised")
    return _SERVICE


def get_state() -> LiveState:
    if _STATE is None:
        raise HTTPException(status_code=500, detail="state not initialised")
    return _STATE


def _to_view(data: DashboardData) -> DashboardView:
    return DashboardView(
        objective=data.objective,
        battery_soc=data.telemetry.battery_soc,
        pv_power=data.telemetry.pv_power,
        grid_power=data.telemetry.grid_power,
        load_power=data.telemetry.load_power,
        month_to_date_grid_import_kwh=data.telemetry.month_to_date_grid_import_kwh,
        usable_kwh=data.usable_kwh,
        usable_kwh_confidence=data.usable_kwh_confidence,
        daily_consumption_kwh=data.daily_consumption_kwh,
        daily_consumption_confidence=data.daily_consumption_confidence,
        slots=[
            SlotView(
                start=a.slot.start.isoformat(timespec="minutes"),
                end=a.slot.end.isoformat(timespec="minutes"),
                target_soc=a.slot.target_soc,
                grid_charge=a.slot.grid_charge,
                behavior=a.behavior.value,
                end_soc=round(a.end_soc, 1),
                grid_import_kwh=round(a.grid_import_kwh, 2),
                cost=round(a.cost, 2),
            )
            for a in data.slot_assessments
        ],
        recommendation=RecommendationView(
            reserve_target_soc=round(data.recommendation.reserve_target_soc, 1),
            enable_overnight_grid_charge=data.recommendation.enable_overnight_grid_charge,
            grid_charge_kwh=round(data.recommendation.grid_charge_kwh, 2),
            expected_daily_grid_import_kwh=round(
                data.recommendation.expected_daily_grid_import_kwh, 2
            ),
            expected_daily_cost=round(data.recommendation.expected_daily_cost, 2),
            backup_hours=round(data.recommendation.backup_hours, 1),
            monthly_cost_so_far=round(data.recommendation.monthly_cost_so_far, 2),
        ),
        disclaimer=data.disclaimer,
    )


def build_app(state: LiveState, config: AppConfig | None = None) -> FastAPI:
    """Build the FastAPI app around a given LiveState. The live MQTT loop is
    started in the lifespan only when a config is supplied (skipped in tests)."""

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        task: asyncio.Task[None] | None = None
        if config is not None:
            task = asyncio.create_task(
                run_live_ingest(
                    state,
                    host=config.mqtt_host,
                    port=config.mqtt_port,
                    username=config.mqtt_user,
                    password=config.mqtt_pass,
                )
            )
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="Solar Advisor", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],  # Vite dev server (Plan E)
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    global _STATE
    _STATE = state

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {"status": "ok", "telemetry_ready": state.telemetry is not None,
                "schedule_ready": state.schedule is not None}

    @app.get("/api/dashboard", response_model=DashboardView)
    def dashboard(
        objective: float | None = Query(default=None, ge=0.0, le=1.0),
        service: RecommendationService = Depends(get_service),
    ) -> DashboardView:
        try:
            data = service.build(get_state(), objective=objective)
        except LookupError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return _to_view(data)

    return app


def create_production_app() -> FastAPI:
    """Entry point for uvicorn: wires real config, store, estimator, forecast."""
    global _SERVICE
    config = load_config()
    store = SqliteTelemetryStore(config.db_path)
    state = LiveState(store=store)
    estimator = ParameterEstimator(store, nominal_kwh=config.battery_nominal_kwh)
    forecast = StaticForecastProvider(
        today_kwh=config.forecast_today_kwh, tomorrow_kwh=config.forecast_tomorrow_kwh
    )
    _SERVICE = RecommendationService(config=config, estimator=estimator, forecast=forecast)
    return build_app(state=state, config=config)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_api.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full suite**

Run: `cd backend && make check`
Expected: ruff, mypy strict, import-linter (1 kept), all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/src/solar_advisor/api/ backend/tests/test_api.py
git commit -m "feat(api): FastAPI dashboard endpoint serving live engine output"
```

---

## Task 8: API container & compose service

**Files:**
- Create: `backend/Dockerfile.api`
- Modify: `backend/docker-compose.yml`

- [ ] **Step 1: Write `Dockerfile.api`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
CMD ["uvicorn", "solar_advisor.api.app:create_production_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Add the `api` service to `docker-compose.yml`**

Add alongside the existing `collector` service (share the `sa_data` volume so the API reads the same SQLite history):

```yaml
  api:
    build:
      context: .
      dockerfile: Dockerfile.api
    environment:
      SA_MQTT_HOST: ${SA_MQTT_HOST:?set in .env}
      SA_MQTT_PORT: ${SA_MQTT_PORT:-1883}
      SA_MQTT_USER: ${SA_MQTT_USER:-}
      SA_MQTT_PASS: ${SA_MQTT_PASS:-}
      SA_DB_PATH: /data/solar_advisor.db
      SA_TARIFF_RATE: ${SA_TARIFF_RATE:-3.56}
      SA_TARIFF_FIXED_CHARGE: ${SA_TARIFF_FIXED_CHARGE:-600}
    ports:
      - "8000:8000"
    volumes:
      - sa_data:/data
    restart: unless-stopped
```

- [ ] **Step 3: Validate compose config**

Run (if docker available): `cd backend && SA_MQTT_HOST=x docker compose config -q && echo OK`
Expected: prints `OK` (or note that the Docker daemon is unavailable and confirm the file is textually consistent with `Dockerfile.api` + the `create_production_app` factory path).

- [ ] **Step 4: Commit**

```bash
git add backend/Dockerfile.api backend/docker-compose.yml
git commit -m "build: API container image and compose service"
```

---

## Definition of done (Plan C)

- `make check` green: ruff, `mypy --strict`, import-linter (engine still pure), all tests pass.
- The API maintains live telemetry + the 6-slot schedule from MQTT (read-only; write topics rejected) and persists telemetry to SQLite.
- `GET /api/dashboard?objective=<0..1>` runs the deterministic engine on live data and returns per-slot assessments + a recommendation + scores + estimate confidences + the advisory disclaimer; `objective` drives the slider; 503 until live state is ready.
- No code path can write to the inverter.

**Next:** Plan D — Explain layer (`ExplanationContext` + numeric-provenance guard + Anthropic client + `/api/explain`), then Plan E — Vue dashboard consuming these endpoints.

---

## Self-review notes

- **Spec coverage:** §3.1 schedule ingestion via a data-driven topic map (Tasks 3, 5); §9 forecast behind the `ForecastProvider` interface with HA + static adapters (Task 4); §5 slider → engine re-run (Task 7 `objective` query param → `recommend`); §5 dashboard data surface (Task 6 `DashboardData`); §7 advisory disclaimer on every dashboard response (Tasks 6, 7). Estimation reuses Plan B's `ParameterEstimator`.
- **Type consistency:** `LiveState.telemetry`/`.schedule` feed `RecommendationService.build`, which calls `assess_schedule(...)` and `recommend(...)` with the exact signatures/keyword args defined in Plan B. `SlotAssessment`/`Recommendation` fields map 1:1 into `SlotView`/`RecommendationView`. `build_schedule` raw-dict shape matches Plan A. `make_telemetry` from `tests/conftest.py` reused per existing convention.
- **Purity:** `api`, `services`, `ingest`, `forecast` import `engine` (allowed); nothing makes `engine` import them. The import-linter contract is unchanged and stays green.
- **No placeholders:** every code step is complete and runnable; commands carry expected output.
- **Read-only:** the live loop reuses `assert_read_only` per message; no publish path exists anywhere in this plan.
```
