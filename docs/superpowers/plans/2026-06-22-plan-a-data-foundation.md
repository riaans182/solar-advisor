# Plan A — Data Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a safe, read-only telemetry pipeline for a Deye/SolarAssistant inverter: connect to MQTT, normalize topics into a vendor-neutral domain model, and persist to local SQLite — with conventions and the deterministic/LLM boundary enforced in CI from commit 1.

**Architecture:** A `TelemetrySource` adapter turns raw MQTT into immutable domain dataclasses; a `TelemetryStore` persists them to SQLite with downsampling, rollups, and retention. All inverter-specific knowledge lives in a topic-map config. The pure `engine`/`explain` packages are created empty here so the `import-linter` boundary contract is live from the start.

**Tech Stack:** Python 3.12, `aiomqtt` (async MQTT), stdlib `dataclasses` + `sqlite3`, `pytest` + `pytest-asyncio`, `ruff`, `mypy --strict`, `import-linter`, Docker Compose.

**Covers spec stages:** 0 (Conventions), 1 (Ingest), 2 (Storage). See `docs/superpowers/specs/2026-06-22-solar-advisor-design.md` §§3, 3.1, 4, 7, 9, 11, 12, 13.

---

## File structure (created by this plan)

```
backend/
├─ pyproject.toml                         # deps, ruff, mypy, pytest config
├─ Makefile                               # lint / typecheck / test / contract
├─ .importlinter                          # boundary contract
├─ src/solar_advisor/
│  ├─ __init__.py
│  ├─ domain/
│  │  ├─ __init__.py
│  │  ├─ telemetry.py                     # Telemetry (frozen dataclass)
│  │  └─ schedule.py                      # Slot, Schedule (frozen dataclasses)
│  ├─ ingest/
│  │  ├─ __init__.py
│  │  ├─ source.py                        # TelemetrySource Protocol
│  │  ├─ topic_map.py                     # TELEMETRY_TOPICS, SCHEDULE_TOPICS, parse_value
│  │  ├─ deye_adapter.py                  # DeyeAdapter: messages → snapshots
│  │  ├─ accumulator.py                   # MonthToDateAccumulator
│  │  ├─ safety.py                        # is_write_topic, READ_ONLY guards
│  │  └─ mqtt_client.py                   # ReadOnlyMqttClient (no publish)
│  ├─ storage/
│  │  ├─ __init__.py
│  │  ├─ store.py                         # TelemetryStore Protocol
│  │  └─ sqlite_store.py                  # SqliteTelemetryStore
│  ├─ engine/__init__.py                  # empty placeholder (Plan B)
│  ├─ explain/__init__.py                 # empty placeholder (Plan C)
│  ├─ forecast/__init__.py                # empty placeholder (Plan B/C)
│  ├─ estimation/__init__.py              # empty placeholder (Plan B)
│  └─ collector.py                        # runtime entrypoint: ingest → store
├─ tests/
│  ├─ __init__.py
│  ├─ test_topic_map.py
│  ├─ test_deye_adapter.py
│  ├─ test_schedule.py
│  ├─ test_accumulator.py
│  ├─ test_safety.py
│  ├─ test_mqtt_client.py
│  └─ test_sqlite_store.py
├─ docker-compose.yml
└─ README.md
```

---

## Task 0: Repo scaffold & Python tooling

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/Makefile`
- Create: `backend/src/solar_advisor/__init__.py` (and empty `__init__.py` for each subpackage listed above)
- Create: `backend/tests/__init__.py`

- [ ] **Step 1: Create the package skeleton (empty `__init__.py` files)**

```bash
cd backend
mkdir -p src/solar_advisor/{domain,ingest,storage,engine,explain,forecast,estimation} tests
touch src/solar_advisor/__init__.py \
      src/solar_advisor/domain/__init__.py \
      src/solar_advisor/ingest/__init__.py \
      src/solar_advisor/storage/__init__.py \
      src/solar_advisor/engine/__init__.py \
      src/solar_advisor/explain/__init__.py \
      src/solar_advisor/forecast/__init__.py \
      src/solar_advisor/estimation/__init__.py \
      tests/__init__.py
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "solar-advisor"
version = "0.0.1"
description = "Advisory-only companion for a local SolarAssistant instance"
requires-python = ">=3.12"
dependencies = [
    "aiomqtt>=2.3",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.24",
    "ruff>=0.6",
    "mypy>=1.11",
    "import-linter>=2.1",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/solar_advisor"]

[tool.ruff]
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.12"
strict = true
mypy_path = "src"
packages = ["solar_advisor"]

[tool.pytest.ini_options]
pythonpath = ["src"]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 3: Write `Makefile`**

```makefile
.PHONY: install lint typecheck contract test check

install:
	python -m pip install -e ".[dev]"

lint:
	ruff check src tests
	ruff format --check src tests

typecheck:
	mypy

contract:
	lint-imports --config .importlinter

test:
	pytest -q

check: lint typecheck contract test
```

- [ ] **Step 4: Install and verify the empty project builds**

Run: `cd backend && make install && python -c "import solar_advisor"`
Expected: installs cleanly; import prints nothing and exits 0.

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/Makefile backend/src backend/tests
git commit -m "chore: scaffold backend package and tooling"
```

---

## Task 1: Import-linter boundary contract

The deterministic `engine` must never import I/O, network, the LLM SDK, or sibling I/O packages. This is the spec's centerpiece invariant (§8) — enforced now, before any engine code exists.

**Files:**
- Create: `backend/.importlinter`

- [ ] **Step 1: Write the contract**

```ini
[importlinter]
root_package = solar_advisor

[importlinter:contract:engine-is-pure]
name = engine must not import I/O, network, or LLM layers
type = forbidden
source_modules =
    solar_advisor.engine
forbidden_modules =
    solar_advisor.ingest
    solar_advisor.storage
    solar_advisor.explain
    solar_advisor.forecast
    solar_advisor.api
    aiomqtt
    sqlite3
    anthropic
allow_indirect_imports = false
```

- [ ] **Step 2: Run the contract to verify it passes on the empty engine**

Run: `cd backend && lint-imports --config .importlinter`
Expected: `Contracts: 1 kept, 0 broken.`

- [ ] **Step 3: Prove the contract bites (temporary check, then revert)**

Add `import aiomqtt` to `src/solar_advisor/engine/__init__.py`, then:
Run: `lint-imports --config .importlinter`
Expected: `1 broken` — contract reports the forbidden import.
Then remove the line so the file is empty again and re-run: `1 kept`.

- [ ] **Step 4: Commit**

```bash
git add backend/.importlinter
git commit -m "chore: enforce engine purity via import-linter contract"
```

---

## Task 2: Docker Compose & README skeleton

**Files:**
- Create: `backend/docker-compose.yml`
- Create: `backend/README.md`

- [ ] **Step 1: Write `docker-compose.yml` (collector service, env-driven)**

```yaml
services:
  collector:
    build: .
    command: python -m solar_advisor.collector
    environment:
      SA_MQTT_HOST: ${SA_MQTT_HOST:?set in .env}
      SA_MQTT_PORT: ${SA_MQTT_PORT:-1883}
      SA_MQTT_USER: ${SA_MQTT_USER:-}
      SA_MQTT_PASS: ${SA_MQTT_PASS:-}
      SA_DB_PATH: /data/solar_advisor.db
    volumes:
      - sa_data:/data
    restart: unless-stopped

volumes:
  sa_data:
```

- [ ] **Step 2: Write `README.md` (portfolio framing, advisory-only banner)**

```markdown
# Solar Advisor

Advisory-only companion for a self-hosted [SolarAssistant](https://solar-assistant.io)
instance. Reads inverter telemetry and the work-mode schedule over local MQTT, runs a
**deterministic** optimisation engine, and uses an LLM purely to explain the engine's
output. It never writes to the inverter.

> ⚠️ **Advisory only.** This app is strictly read-only against your inverter.
> Recommendations are shown for you to apply manually.

Clean-room personal project. See `docs/superpowers/specs/` for the design and
`docs/superpowers/plans/` for the build plans.

## Status
Plan A (data foundation): read-only MQTT ingest → SQLite storage.
```

- [ ] **Step 3: Commit**

```bash
git add backend/docker-compose.yml backend/README.md
git commit -m "chore: add docker-compose and README skeleton"
```

---

## Task 3: Normalized telemetry domain model

**Files:**
- Create: `backend/src/solar_advisor/domain/telemetry.py`
- Test: `backend/tests/test_topic_map.py` (model used by Task 4 test; model itself is trivial data)

- [ ] **Step 1: Write the immutable `Telemetry` dataclass**

```python
# src/solar_advisor/domain/telemetry.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Telemetry:
    """Vendor-neutral snapshot of inverter state at a point in time.

    Power in watts (grid_power/battery_power signed: + = import/charge).
    Energy fields are lifetime-cumulative kWh as reported by the inverter.
    """

    ts: datetime
    battery_soc: float            # %
    battery_power: float          # W (+ charging)
    battery_voltage: float        # V
    battery_current: float        # A
    pv_power: float               # W
    grid_power: float             # W (+ import)
    load_power: float             # W
    load_power_essential: float   # W
    grid_energy_in: float         # kWh cumulative
    grid_energy_out: float        # kWh cumulative
    pv_energy: float              # kWh cumulative
    load_energy: float            # kWh cumulative
    battery_energy_in: float      # kWh cumulative
    battery_energy_out: float     # kWh cumulative
    month_to_date_grid_import_kwh: float  # derived (Task 6)
```

- [ ] **Step 2: Verify it imports and is frozen**

Run: `cd backend && python -c "from solar_advisor.domain.telemetry import Telemetry; from datetime import datetime; t=Telemetry(ts=datetime(2026,6,22),battery_soc=64,battery_power=85,battery_voltage=50,battery_current=1.7,pv_power=106,grid_power=1140,load_power=1086,load_power_essential=1136,grid_energy_in=0,grid_energy_out=0,pv_energy=0,load_energy=0,battery_energy_in=0,battery_energy_out=0,month_to_date_grid_import_kwh=0); print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/src/solar_advisor/domain/telemetry.py
git commit -m "feat: add normalized Telemetry domain model"
```

---

## Task 4: Topic map & value parsing

**Files:**
- Create: `backend/src/solar_advisor/ingest/topic_map.py`
- Test: `backend/tests/test_topic_map.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_topic_map.py
from solar_advisor.ingest.topic_map import TELEMETRY_TOPICS, parse_value


def test_known_telemetry_topic_maps_to_field_and_float():
    field, value = parse_value(
        "solar_assistant/total/battery_state_of_charge/state", "64"
    )
    assert field == "battery_soc"
    assert value == 64.0


def test_unknown_topic_returns_none():
    assert parse_value("solar_assistant/total/nonsense/state", "1") is None


def test_camera_noise_topic_returns_none():
    assert parse_value("frigate/driveway/snapshot", "<binary>") is None


def test_topic_map_covers_all_telemetry_fields():
    expected = {
        "battery_soc", "battery_power", "battery_voltage", "battery_current",
        "pv_power", "grid_power", "load_power", "load_power_essential",
        "grid_energy_in", "grid_energy_out", "pv_energy", "load_energy",
        "battery_energy_in", "battery_energy_out",
    }
    assert set(TELEMETRY_TOPICS.values()) == expected
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && pytest tests/test_topic_map.py -v`
Expected: FAIL with `ModuleNotFoundError: solar_advisor.ingest.topic_map`.

- [ ] **Step 3: Write the implementation**

```python
# src/solar_advisor/ingest/topic_map.py
from __future__ import annotations

# Deye / SolarAssistant telemetry topics → normalized field name.
# This dict is the entire vendor-specific surface for telemetry; a different
# inverter is a new map emitting the same field names (spec §3.1).
TELEMETRY_TOPICS: dict[str, str] = {
    "solar_assistant/total/battery_state_of_charge/state": "battery_soc",
    "solar_assistant/total/battery_power/state": "battery_power",
    "solar_assistant/inverter_1/battery_voltage/state": "battery_voltage",
    "solar_assistant/inverter_1/battery_current/state": "battery_current",
    "solar_assistant/inverter_1/pv_power/state": "pv_power",
    "solar_assistant/inverter_1/grid_power/state": "grid_power",
    "solar_assistant/inverter_1/load_power/state": "load_power",
    "solar_assistant/inverter_1/load_power_essential/state": "load_power_essential",
    "solar_assistant/total/grid_energy_in/state": "grid_energy_in",
    "solar_assistant/total/grid_energy_out/state": "grid_energy_out",
    "solar_assistant/total/pv_energy/state": "pv_energy",
    "solar_assistant/total/load_energy/state": "load_energy",
    "solar_assistant/total/battery_energy_in/state": "battery_energy_in",
    "solar_assistant/total/battery_energy_out/state": "battery_energy_out",
}


def parse_value(topic: str, payload: str) -> tuple[str, float] | None:
    """Map a telemetry topic+payload to (field_name, float). None if not telemetry."""
    field = TELEMETRY_TOPICS.get(topic)
    if field is None:
        return None
    try:
        return field, float(payload)
    except ValueError:
        return None
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && pytest tests/test_topic_map.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/solar_advisor/ingest/topic_map.py backend/tests/test_topic_map.py
git commit -m "feat: telemetry topic map and value parsing"
```

---

## Task 5: Schedule model & assembly

**Files:**
- Create: `backend/src/solar_advisor/domain/schedule.py`
- Test: `backend/tests/test_schedule.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_schedule.py
from datetime import time

from solar_advisor.domain.schedule import Slot, build_schedule


def _raw():
    # Mirrors the discovered live schedule (spec §2).
    return {
        "time_point": {1: "00:00", 2: "05:00", 3: "08:00", 4: "16:30", 5: "18:00", 6: "21:30"},
        "capacity_point": {1: 65, 2: 65, 3: 90, 4: 95, 5: 75, 6: 65},
        "grid_charge_point": {1: True, 2: True, 3: True, 4: False, 5: True, 6: True},
        "gen_charge_point": {1: False, 2: False, 3: False, 4: False, 5: False, 6: False},
    }


def test_build_schedule_has_six_slots():
    assert len(build_schedule(_raw())) == 6


def test_slot_fields_and_wraparound_end():
    slots = build_schedule(_raw())
    assert slots[0] == Slot(
        start=time(0, 0), end=time(5, 0), target_soc=65,
        grid_charge=True, gen_charge=False,
    )
    # Last slot wraps to the first slot's start.
    assert slots[5].start == time(21, 30)
    assert slots[5].end == time(0, 0)


def test_grid_charge_disabled_slot_detected():
    slots = build_schedule(_raw())
    assert slots[3].grid_charge is False  # 16:30 PV-peak slot
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && pytest tests/test_schedule.py -v`
Expected: FAIL with `ModuleNotFoundError: solar_advisor.domain.schedule`.

- [ ] **Step 3: Write the implementation**

```python
# src/solar_advisor/domain/schedule.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Any


@dataclass(frozen=True, slots=True)
class Slot:
    start: time
    end: time
    target_soc: int
    grid_charge: bool
    gen_charge: bool


def _parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


def build_schedule(raw: dict[str, dict[int, Any]]) -> list[Slot]:
    """Assemble the 6-slot TOU schedule. Each slot ends where the next begins;
    slot 6 wraps to slot 1's start."""
    starts = {i: _parse_hhmm(raw["time_point"][i]) for i in range(1, 7)}
    slots: list[Slot] = []
    for i in range(1, 7):
        nxt = 1 if i == 6 else i + 1
        slots.append(
            Slot(
                start=starts[i],
                end=starts[nxt],
                target_soc=int(raw["capacity_point"][i]),
                grid_charge=bool(raw["grid_charge_point"][i]),
                gen_charge=bool(raw["gen_charge_point"][i]),
            )
        )
    return slots
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && pytest tests/test_schedule.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/solar_advisor/domain/schedule.py backend/tests/test_schedule.py
git commit -m "feat: 6-slot TOU schedule model and assembly"
```

---

## Task 6: Month-to-date grid-import accumulator

The inverter reports lifetime-cumulative `grid_energy_in`. We derive month-to-date by remembering the value at month rollover, and tolerate counter resets.

**Files:**
- Create: `backend/src/solar_advisor/ingest/accumulator.py`
- Test: `backend/tests/test_accumulator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_accumulator.py
from datetime import datetime

from solar_advisor.ingest.accumulator import MonthToDateAccumulator


def test_first_reading_is_zero_month_to_date():
    acc = MonthToDateAccumulator()
    assert acc.update(datetime(2026, 6, 22, 8, 0), 1000.0) == 0.0


def test_accumulates_within_month():
    acc = MonthToDateAccumulator()
    acc.update(datetime(2026, 6, 22, 8, 0), 1000.0)
    assert acc.update(datetime(2026, 6, 23, 8, 0), 1012.5) == 12.5


def test_resets_at_month_rollover():
    acc = MonthToDateAccumulator()
    acc.update(datetime(2026, 6, 22, 8, 0), 1000.0)
    acc.update(datetime(2026, 6, 30, 8, 0), 1030.0)
    # New month: baseline rebases to the first reading of July.
    assert acc.update(datetime(2026, 7, 1, 8, 0), 1031.0) == 0.0
    assert acc.update(datetime(2026, 7, 2, 8, 0), 1036.0) == 5.0


def test_tolerates_counter_reset():
    acc = MonthToDateAccumulator()
    acc.update(datetime(2026, 6, 22, 8, 0), 1000.0)
    # Counter reset (e.g. inverter reboot): value drops below last seen.
    assert acc.update(datetime(2026, 6, 22, 9, 0), 5.0) == 0.0
    assert acc.update(datetime(2026, 6, 22, 10, 0), 8.0) == 3.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && pytest tests/test_accumulator.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
# src/solar_advisor/ingest/accumulator.py
from __future__ import annotations

from datetime import datetime


class MonthToDateAccumulator:
    """Derives month-to-date grid import from a lifetime-cumulative counter.

    Rebases the baseline at month rollover and on counter resets (value drops).
    """

    def __init__(self) -> None:
        self._month: tuple[int, int] | None = None
        self._baseline: float | None = None
        self._last: float | None = None

    def update(self, ts: datetime, cumulative_kwh: float) -> float:
        month = (ts.year, ts.month)
        reset = self._last is not None and cumulative_kwh < self._last
        if self._month != month or self._baseline is None or reset:
            self._month = month
            self._baseline = cumulative_kwh
        self._last = cumulative_kwh
        return round(cumulative_kwh - self._baseline, 6)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && pytest tests/test_accumulator.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/solar_advisor/ingest/accumulator.py backend/tests/test_accumulator.py
git commit -m "feat: month-to-date grid import accumulator"
```

---

## Task 7: Write-safety guard

The advisory-only invariant (spec §7): never publish to a `/set` topic. A pure predicate, unit-tested, used by the client in Task 9.

**Files:**
- Create: `backend/src/solar_advisor/ingest/safety.py`
- Test: `backend/tests/test_safety.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_safety.py
import pytest

from solar_advisor.ingest.safety import WriteAttemptError, assert_read_only, is_write_topic


@pytest.mark.parametrize("topic", [
    "solar_assistant/inverter_1/max_charge_current/set",
    "solar_assistant/inverter_1/grid_charge_point_1/set",
    "solar_assistant/set/response_message/state",
])
def test_write_topics_detected(topic):
    assert is_write_topic(topic) is True


@pytest.mark.parametrize("topic", [
    "solar_assistant/total/battery_state_of_charge/state",
    "solar_assistant/inverter_1/pv_power/state",
])
def test_read_topics_allowed(topic):
    assert is_write_topic(topic) is False


def test_assert_read_only_raises_on_write_topic():
    with pytest.raises(WriteAttemptError):
        assert_read_only("solar_assistant/inverter_1/max_charge_current/set")


def test_assert_read_only_silent_on_read_topic():
    assert_read_only("solar_assistant/inverter_1/pv_power/state")  # no raise
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && pytest tests/test_safety.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
# src/solar_advisor/ingest/safety.py
from __future__ import annotations


class WriteAttemptError(RuntimeError):
    """Raised if anything attempts to write to the inverter. Advisory-only invariant."""


def is_write_topic(topic: str) -> bool:
    """True for any inverter command/write topic."""
    return topic.endswith("/set") or topic.startswith("solar_assistant/set/")


def assert_read_only(topic: str) -> None:
    if is_write_topic(topic):
        raise WriteAttemptError(f"refusing to write to inverter topic: {topic}")
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && pytest tests/test_safety.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/solar_advisor/ingest/safety.py backend/tests/test_safety.py
git commit -m "feat: write-safety guard for advisory-only invariant"
```

---

## Task 8: Deye adapter — assemble snapshots from messages

The adapter holds the latest value per field and emits a `Telemetry` snapshot once all telemetry fields have been seen at least once.

**Files:**
- Create: `backend/src/solar_advisor/ingest/source.py`
- Create: `backend/src/solar_advisor/ingest/deye_adapter.py`
- Test: `backend/tests/test_deye_adapter.py`

- [ ] **Step 1: Write the `TelemetrySource` protocol**

```python
# src/solar_advisor/ingest/source.py
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from solar_advisor.domain.telemetry import Telemetry


class TelemetrySource(Protocol):
    """A source of normalized telemetry snapshots. Implementations own all
    vendor-specific transport/topic detail (spec §3.1)."""

    def stream(self) -> AsyncIterator[Telemetry]: ...
```

- [ ] **Step 2: Write the failing adapter test**

```python
# tests/test_deye_adapter.py
from datetime import datetime

from solar_advisor.ingest.deye_adapter import DeyeAdapter

ALL_FIELDS = {
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


def test_no_snapshot_until_all_fields_seen():
    adapter = DeyeAdapter()
    items = list(ALL_FIELDS.items())
    for topic, payload in items[:-1]:
        assert adapter.ingest(datetime(2026, 6, 22, 8, 0), topic, payload) is None
    # Last field completes the set → snapshot emitted.
    last_topic, last_payload = items[-1]
    snap = adapter.ingest(datetime(2026, 6, 22, 8, 0), last_topic, last_payload)
    assert snap is not None
    assert snap.battery_soc == 64.0
    assert snap.grid_power == 1140.0


def test_ignores_unknown_topics():
    adapter = DeyeAdapter()
    assert adapter.ingest(datetime(2026, 6, 22, 8, 0), "frigate/x/snapshot", "junk") is None


def test_month_to_date_derived_from_grid_energy_in():
    adapter = DeyeAdapter()
    for topic, payload in ALL_FIELDS.items():
        adapter.ingest(datetime(2026, 6, 22, 8, 0), topic, payload)
    snap = adapter.ingest(
        datetime(2026, 6, 23, 8, 0), "solar_assistant/total/grid_energy_in/state", "1012.5"
    )
    assert snap is not None
    assert snap.month_to_date_grid_import_kwh == 12.5
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd backend && pytest tests/test_deye_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: solar_advisor.ingest.deye_adapter`.

- [ ] **Step 4: Write the implementation**

```python
# src/solar_advisor/ingest/deye_adapter.py
from __future__ import annotations

from datetime import datetime

from solar_advisor.domain.telemetry import Telemetry
from solar_advisor.ingest.accumulator import MonthToDateAccumulator
from solar_advisor.ingest.topic_map import TELEMETRY_TOPICS, parse_value


class DeyeAdapter:
    """Accumulates latest field values from MQTT messages and emits a Telemetry
    snapshot once every telemetry field has been observed."""

    def __init__(self) -> None:
        self._values: dict[str, float] = {}
        self._accumulator = MonthToDateAccumulator()
        self._mtd: float = 0.0

    def ingest(self, ts: datetime, topic: str, payload: str) -> Telemetry | None:
        parsed = parse_value(topic, payload)
        if parsed is None:
            return None
        field, value = parsed
        self._values[field] = value

        if field == "grid_energy_in":
            self._mtd = self._accumulator.update(ts, value)

        if not self._has_all_fields():
            return None

        return Telemetry(
            ts=ts,
            month_to_date_grid_import_kwh=self._mtd,
            **{name: self._values[name] for name in TELEMETRY_TOPICS.values()},
        )

    def _has_all_fields(self) -> bool:
        return set(self._values) >= set(TELEMETRY_TOPICS.values())
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd backend && pytest tests/test_deye_adapter.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/src/solar_advisor/ingest/source.py backend/src/solar_advisor/ingest/deye_adapter.py backend/tests/test_deye_adapter.py
git commit -m "feat: Deye adapter assembles Telemetry snapshots from MQTT messages"
```

---

## Task 9: Read-only MQTT client

Wraps `aiomqtt` to subscribe only. The class exposes **no publish method** — the testable form of the advisory-only invariant.

**Files:**
- Create: `backend/src/solar_advisor/ingest/mqtt_client.py`
- Test: `backend/tests/test_mqtt_client.py`

- [ ] **Step 1: Write the failing test (no-publish invariant; no broker needed)**

```python
# tests/test_mqtt_client.py
from solar_advisor.ingest.mqtt_client import ReadOnlyMqttClient


def test_client_exposes_no_publish_capability():
    # The advisory-only invariant, made testable: the class surfaces no method
    # whose name implies writing/publishing to the broker.
    names = [n for n in dir(ReadOnlyMqttClient) if not n.startswith("_")]
    assert not [n for n in names if "publish" in n.lower() or n.lower() == "set"]


def test_subscribe_filter_is_solar_assistant_only():
    client = ReadOnlyMqttClient(host="localhost", port=1883)
    assert client.topic_filter == "solar_assistant/#"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && pytest tests/test_mqtt_client.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
# src/solar_advisor/ingest/mqtt_client.py
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import aiomqtt

from solar_advisor.domain.telemetry import Telemetry
from solar_advisor.ingest.deye_adapter import DeyeAdapter
from solar_advisor.ingest.safety import assert_read_only


class ReadOnlyMqttClient:
    """Subscribe-only MQTT client. Deliberately exposes no publish method;
    every observed topic is asserted read-only before processing (spec §7)."""

    def __init__(
        self,
        host: str,
        port: int = 1883,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username or None
        self._password = password or None
        self.topic_filter = "solar_assistant/#"

    async def stream(self) -> AsyncIterator[Telemetry]:
        adapter = DeyeAdapter()
        async with aiomqtt.Client(
            hostname=self._host,
            port=self._port,
            username=self._username,
            password=self._password,
        ) as client:
            await client.subscribe(self.topic_filter)
            async for message in client.messages:
                topic = str(message.topic)
                assert_read_only(topic)  # never act on a write topic
                payload = (
                    message.payload.decode(errors="ignore")
                    if isinstance(message.payload, bytes)
                    else str(message.payload)
                )
                snapshot = adapter.ingest(datetime.now(UTC), topic, payload)
                if snapshot is not None:
                    yield snapshot
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && pytest tests/test_mqtt_client.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Verify the client satisfies the `TelemetrySource` protocol**

Run: `cd backend && python -c "from solar_advisor.ingest.source import TelemetrySource; from solar_advisor.ingest.mqtt_client import ReadOnlyMqttClient; c=ReadOnlyMqttClient(host='x'); assert isinstance(c, TelemetrySource); print('ok')"`
Expected: prints `ok` (structural Protocol check passes because `stream` exists).

- [ ] **Step 6: Commit**

```bash
git add backend/src/solar_advisor/ingest/mqtt_client.py backend/tests/test_mqtt_client.py
git commit -m "feat: read-only MQTT client with no publish capability"
```

---

## Task 10: SQLite telemetry store

**Files:**
- Create: `backend/src/solar_advisor/storage/store.py`
- Create: `backend/src/solar_advisor/storage/sqlite_store.py`
- Test: `backend/tests/test_sqlite_store.py`

- [ ] **Step 1: Write the `TelemetryStore` protocol**

```python
# src/solar_advisor/storage/store.py
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from solar_advisor.domain.telemetry import Telemetry


class TelemetryStore(Protocol):
    def save(self, snapshot: Telemetry) -> bool: ...
    def query_range(self, start: datetime, end: datetime) -> list[Telemetry]: ...
    def prune_before(self, cutoff: datetime) -> int: ...
```

- [ ] **Step 2: Write the failing test (save/query, downsampling, retention)**

```python
# tests/test_sqlite_store.py
from datetime import datetime, timedelta

import pytest

from solar_advisor.domain.telemetry import Telemetry
from solar_advisor.storage.sqlite_store import SqliteTelemetryStore


def _snap(ts: datetime, soc: float = 64.0) -> Telemetry:
    return Telemetry(
        ts=ts, battery_soc=soc, battery_power=85, battery_voltage=50, battery_current=1.7,
        pv_power=106, grid_power=1140, load_power=1086, load_power_essential=1136,
        grid_energy_in=1000, grid_energy_out=0, pv_energy=0, load_energy=0,
        battery_energy_in=0, battery_energy_out=0, month_to_date_grid_import_kwh=12.5,
    )


@pytest.fixture
def store(tmp_path):
    return SqliteTelemetryStore(tmp_path / "t.db", min_interval=timedelta(seconds=10))


def test_save_then_query_roundtrip(store):
    t = datetime(2026, 6, 22, 8, 0, 0)
    assert store.save(_snap(t, soc=64)) is True
    rows = store.query_range(t - timedelta(minutes=1), t + timedelta(minutes=1))
    assert len(rows) == 1
    assert rows[0].battery_soc == 64
    assert rows[0].month_to_date_grid_import_kwh == 12.5


def test_downsampling_skips_writes_inside_min_interval(store):
    t = datetime(2026, 6, 22, 8, 0, 0)
    assert store.save(_snap(t)) is True
    assert store.save(_snap(t + timedelta(seconds=5))) is False   # within 10s window
    assert store.save(_snap(t + timedelta(seconds=11))) is True   # past window


def test_prune_before_removes_old_rows(store):
    old = datetime(2026, 6, 1, 8, 0, 0)
    new = datetime(2026, 6, 22, 8, 0, 0)
    store.save(_snap(old))
    store.save(_snap(new))
    removed = store.prune_before(datetime(2026, 6, 10))
    assert removed == 1
    rows = store.query_range(datetime(2026, 5, 1), datetime(2026, 7, 1))
    assert len(rows) == 1
    assert rows[0].ts == new
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd backend && pytest tests/test_sqlite_store.py -v`
Expected: FAIL with `ModuleNotFoundError: solar_advisor.storage.sqlite_store`.

- [ ] **Step 4: Write the implementation**

```python
# src/solar_advisor/storage/sqlite_store.py
from __future__ import annotations

import sqlite3
from dataclasses import asdict, fields
from datetime import datetime, timedelta
from pathlib import Path

from solar_advisor.domain.telemetry import Telemetry

_FIELDS = [f.name for f in fields(Telemetry) if f.name != "ts"]


class SqliteTelemetryStore:
    """Wide-row telemetry store with ingest-time downsampling and retention pruning."""

    def __init__(self, path: Path | str, min_interval: timedelta = timedelta(seconds=10)) -> None:
        self._conn = sqlite3.connect(str(path))
        self._min_interval = min_interval
        self._last_saved_ts: datetime | None = None
        columns = ", ".join(f"{name} REAL" for name in _FIELDS)
        self._conn.execute(
            f"CREATE TABLE IF NOT EXISTS telemetry (ts TEXT PRIMARY KEY, {columns})"
        )
        self._conn.commit()

    def save(self, snapshot: Telemetry) -> bool:
        if (
            self._last_saved_ts is not None
            and snapshot.ts - self._last_saved_ts < self._min_interval
        ):
            return False
        data = asdict(snapshot)
        placeholders = ", ".join(["?"] * (len(_FIELDS) + 1))
        cols = "ts, " + ", ".join(_FIELDS)
        values = [snapshot.ts.isoformat()] + [data[name] for name in _FIELDS]
        self._conn.execute(
            f"INSERT OR REPLACE INTO telemetry ({cols}) VALUES ({placeholders})", values
        )
        self._conn.commit()
        self._last_saved_ts = snapshot.ts
        return True

    def query_range(self, start: datetime, end: datetime) -> list[Telemetry]:
        cur = self._conn.execute(
            "SELECT * FROM telemetry WHERE ts >= ? AND ts <= ? ORDER BY ts",
            (start.isoformat(), end.isoformat()),
        )
        rows = cur.fetchall()
        out: list[Telemetry] = []
        for row in rows:
            ts = datetime.fromisoformat(row[0])
            kwargs = dict(zip(_FIELDS, row[1:], strict=True))
            out.append(Telemetry(ts=ts, **kwargs))
        return out

    def prune_before(self, cutoff: datetime) -> int:
        cur = self._conn.execute("DELETE FROM telemetry WHERE ts < ?", (cutoff.isoformat(),))
        self._conn.commit()
        return cur.rowcount
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd backend && pytest tests/test_sqlite_store.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/src/solar_advisor/storage/store.py backend/src/solar_advisor/storage/sqlite_store.py backend/tests/test_sqlite_store.py
git commit -m "feat: SQLite telemetry store with downsampling and retention"
```

---

## Task 11: Collector entrypoint — wire ingest → store

**Files:**
- Create: `backend/src/solar_advisor/collector.py`

- [ ] **Step 1: Write the entrypoint (config from env; runtime wiring)**

```python
# src/solar_advisor/collector.py
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from solar_advisor.ingest.mqtt_client import ReadOnlyMqttClient
from solar_advisor.storage.sqlite_store import SqliteTelemetryStore


async def run() -> None:
    source = ReadOnlyMqttClient(
        host=os.environ["SA_MQTT_HOST"],
        port=int(os.environ.get("SA_MQTT_PORT", "1883")),
        username=os.environ.get("SA_MQTT_USER") or None,
        password=os.environ.get("SA_MQTT_PASS") or None,
    )
    store = SqliteTelemetryStore(Path(os.environ.get("SA_DB_PATH", "solar_advisor.db")))
    async for snapshot in source.stream():
        store.save(snapshot)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it imports (no broker connection)**

Run: `cd backend && python -c "from solar_advisor.collector import main; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Run the full check suite**

Run: `cd backend && make check`
Expected: ruff clean, mypy clean, `Contracts: 1 kept, 0 broken.`, all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/src/solar_advisor/collector.py
git commit -m "feat: collector entrypoint wiring ingest to storage"
```

---

## Definition of done (Plan A)

- `make check` is green: ruff, `mypy --strict`, import-linter contract (1 kept), all tests pass.
- The read-only MQTT client exposes no publish capability (asserted by test) and refuses any `/set` topic.
- Telemetry from the real topic names is normalized into `Telemetry` and persisted to SQLite with downsampling and retention.
- Month-to-date grid import is derived correctly across month rollover and counter resets.
- The deterministic-engine boundary is enforced in CI even though the engine is still empty.

**Next:** Plan B — Deterministic Engine (tariff, battery, schedule eval, estimation, optimizer + slider). Written when Plan A is complete so it reflects the real domain types.

---

## Self-review notes

- **Spec coverage:** §0 conventions (Tasks 0–2), §3/§3.1 transport + adapter + topic map (Tasks 4, 8, 9), §4 domain model (Tasks 3, 5), §7 safety (Tasks 7, 9), §9 storage (Task 10), §3 month-to-date accumulation (Task 6), collector runtime (Task 11). Estimation/forecast/engine/optimizer/explain/dashboard are out of scope for Plan A by design (Plans B/C).
- **Type consistency:** `Telemetry` field names are the single source of truth — `TELEMETRY_TOPICS.values()` (Task 4), the adapter's `**kwargs` (Task 8), and the store's `_FIELDS` (Task 10) all derive from / match them; a test in Task 4 pins the field set. `Slot` fields used identically in Tasks 5. `ReadOnlyMqttClient.stream` matches the `TelemetrySource` protocol (verified Task 9 Step 5).
- **No placeholders:** every code step contains complete, runnable code and exact commands with expected output.
