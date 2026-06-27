# Telemetry Retention Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bound the SQLite telemetry table's unbounded growth by pruning rows older than a configurable retention window on a periodic timer in the collector, while never touching the `purchases` table in the same DB file.

**Architecture:** `SqliteTelemetryStore.prune_before(cutoff)` already exists and issues `DELETE FROM telemetry WHERE ts < ?` (telemetry table only). We add a background `_prune_loop` coroutine to the collector that, on a timer, calls `prune_before(now - retention)`. The retention window is a new `SA_TELEMETRY_RETENTION_DAYS` env var surfaced through `AppConfig` (default 90) and passed into the collector's `run()` by `main()`. The collector launches the prune loop as a concurrent `asyncio.Task` alongside the existing MQTT-reconnect loop and cancels it on shutdown.

**Tech Stack:** Python 3.12, asyncio, sqlite3, pytest + pytest-asyncio (`asyncio_mode = auto`), ruff, mypy `strict`, import-linter.

---

## Background for the implementing engineer

You do not need prior context on this codebase. Key facts:

- **Run all checks from `backend/`** using the Makefile and the project venv:
  - Tests: `make test` (wraps `.venv/bin/pytest -q`). Single file: `.venv/bin/pytest tests/test_collector.py -q`.
  - Lint: `make lint` (`ruff check` + `ruff format --check`).
  - Types: `make typecheck` (`mypy`, `strict = true`).
  - Import contracts: `make contract` (`lint-imports`).
  - Everything: `make check`.
- `pytest` is configured with `asyncio_mode = "auto"`, so `async def test_...` functions run without any decorator.
- The `engine-is-pure` import contract (`.importlinter`) forbids `solar_advisor.engine` from importing I/O layers. The collector and config are **not** part of `engine`, so the imports added here are allowed. Run `make contract` to confirm regardless.
- Timestamps in the telemetry store are UTC tz-aware ISO strings; ordering and the `ts < cutoff` comparison work directly on the text. The collector stamps `datetime.now(UTC)`-class timestamps via its source.
- Existing time/log style in `collector.py`: log to stderr with `print(..., file=sys.stderr)`.

## File Structure

- **Modify** `backend/src/solar_advisor/config.py` — add `telemetry_retention_days` field + `SA_TELEMETRY_RETENTION_DAYS` env read. (Canonical home for the tunable.)
- **Modify** `backend/src/solar_advisor/collector.py` — add `_prune_loop`, wire it into `run()`, source the window from config in `main()`.
- **Modify** `backend/docker-compose.yml` — pass `SA_TELEMETRY_RETENTION_DAYS` into the `collector` service.
- **Modify** `backend/tests/test_config.py` — default + env tests for the new field.
- **Modify** `backend/tests/test_collector.py` — `_prune_loop` unit tests, `run()` wiring test, update existing reconnect test.
- **Modify** `backend/tests/test_sqlite_store.py` — regression test proving a prune leaves the `purchases` table intact.

Why the collector (not the API) prunes: the collector is the single writer and is `restart: unless-stopped`, so it is the natural owner of the maintenance timer. The API only reads.

---

## Task 1: Configurable retention window in `AppConfig`

**Files:**
- Modify: `backend/src/solar_advisor/config.py`
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_config.py` (mirrors the existing `tariff_window_days` tests at the bottom of the file):

```python
def test_telemetry_retention_days_defaults_to_90(monkeypatch):
    monkeypatch.delenv("SA_TELEMETRY_RETENTION_DAYS", raising=False)
    assert load_config().telemetry_retention_days == 90


def test_telemetry_retention_days_from_env(monkeypatch):
    monkeypatch.setenv("SA_TELEMETRY_RETENTION_DAYS", "30")
    assert load_config().telemetry_retention_days == 30
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_config.py -q`
Expected: FAIL — `AttributeError: 'AppConfig' object has no attribute 'telemetry_retention_days'`.

- [ ] **Step 3: Add the field and env read**

In `backend/src/solar_advisor/config.py`, add the field to the `AppConfig` dataclass next to the other windowed tunables (after `tariff_window_days`):

```python
    tariff_window_days: int = 90  # trailing window for the data-derived marginal rate
    telemetry_retention_days: int = 90  # collector prunes telemetry rows older than this
```

And in `load_config()`, add the env read next to the `tariff_window_days` line:

```python
        tariff_window_days=int(os.environ.get("SA_TARIFF_WINDOW_DAYS", "90")),
        telemetry_retention_days=int(os.environ.get("SA_TELEMETRY_RETENTION_DAYS", "90")),
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_config.py -q`
Expected: PASS (all config tests green).

- [ ] **Step 5: Commit**

```bash
git add backend/src/solar_advisor/config.py backend/tests/test_config.py
git commit -m "feat(config): add SA_TELEMETRY_RETENTION_DAYS (default 90)"
```

---

## Task 2: `_prune_loop` periodic prune coroutine

**Files:**
- Modify: `backend/src/solar_advisor/collector.py`
- Test: `backend/tests/test_collector.py`

`_prune_loop` is a standalone coroutine so it can be unit-tested deterministically with an injected clock and sleep — no MQTT or event-loop timing involved. It prunes **first, then sleeps**, so a freshly started (or crash-restarted) collector with an already-large DB prunes immediately.

- [ ] **Step 1: Write the failing tests**

First, extend the existing `_FakeStore` in `backend/tests/test_collector.py` so `prune_before` records its cutoff and returns a configurable count. Replace the current `prune_before` line in `_FakeStore`:

```python
class _FakeStore:
    def __init__(self, prune_result: int = 0) -> None:
        self.saved: list[Telemetry] = []
        self.prune_cutoffs: list[datetime] = []
        self._prune_result = prune_result

    def save(self, snapshot: Telemetry) -> bool:
        self.saved.append(snapshot)
        return True

    def query_range(self, start: datetime, end: datetime) -> list[Telemetry]:
        return []

    def prune_before(self, cutoff: datetime) -> int:
        self.prune_cutoffs.append(cutoff)
        return self._prune_result
```

Then add these tests (and extend the imports at the top of the file — see Step 3's note):

```python
async def test_prune_loop_prunes_at_retention_cutoff() -> None:
    store = _FakeStore(prune_result=5)
    fixed_now = datetime(2026, 6, 26, 12, 0, 0, tzinfo=UTC)
    sleep_calls = 0

    async def fake_sleep(_seconds: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        raise _StopTest  # break after the first prune+sleep cycle

    with pytest.raises(_StopTest):
        await collector._prune_loop(
            store,
            timedelta(days=90),
            3600.0,
            clock=lambda: fixed_now,
            sleep=fake_sleep,
        )

    assert store.prune_cutoffs == [fixed_now - timedelta(days=90)]
    assert sleep_calls == 1


async def test_prune_loop_prunes_every_cycle() -> None:
    store = _FakeStore()
    fixed_now = datetime(2026, 6, 26, 12, 0, 0, tzinfo=UTC)
    sleep_calls = 0

    async def fake_sleep(_seconds: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls >= 3:
            raise _StopTest

    with pytest.raises(_StopTest):
        await collector._prune_loop(
            store,
            timedelta(days=7),
            60.0,
            clock=lambda: fixed_now,
            sleep=fake_sleep,
        )

    # Pruned once per cycle: cycles 1, 2, 3 each prune, the 3rd sleep stops the loop.
    assert len(store.prune_cutoffs) == 3
    assert store.prune_cutoffs[0] == fixed_now - timedelta(days=7)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_collector.py -q`
Expected: FAIL — `AttributeError: module 'solar_advisor.collector' has no attribute '_prune_loop'`.

- [ ] **Step 3: Implement `_prune_loop`**

In `backend/src/solar_advisor/collector.py`, update the imports at the top of the file to add `collections.abc` and `datetime` symbols (keep the existing imports):

```python
from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiomqtt

from solar_advisor.config import load_config
from solar_advisor.ingest.mqtt_client import ReadOnlyMqttClient
from solar_advisor.ingest.source import TelemetrySource
from solar_advisor.storage.sqlite_store import SqliteTelemetryStore
from solar_advisor.storage.store import TelemetryStore
```

Add the module-level default interval constant and the coroutine, above `def run(...)`:

```python
# Prune a few times a day: deletes stay small and the 90-day boundary never lags far.
_PRUNE_INTERVAL_S = 6 * 60 * 60


async def _prune_loop(
    store: TelemetryStore,
    retention: timedelta,
    interval: float,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Periodically delete telemetry older than ``retention``.

    Only the telemetry table is affected: ``prune_before`` issues
    ``DELETE FROM telemetry``, so the ``purchases`` table sharing the same DB
    file is never pruned. Prunes first, then sleeps, so a restart with an
    already-large DB reclaims space immediately.
    """
    while True:
        removed = store.prune_before(clock() - retention)
        if removed:
            print(
                f"collector: pruned {removed} telemetry rows older than {retention}",
                file=sys.stderr,
            )
        await sleep(interval)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_collector.py -q`
Expected: PASS for the two new `_prune_loop` tests. (The existing `test_run_reconnects_after_mqtt_error` is updated in Task 3.)

- [ ] **Step 5: Commit**

```bash
git add backend/src/solar_advisor/collector.py backend/tests/test_collector.py
git commit -m "feat(collector): add _prune_loop periodic telemetry prune"
```

---

## Task 3: Wire `_prune_loop` into `run()` and `main()`

**Files:**
- Modify: `backend/src/solar_advisor/collector.py`
- Test: `backend/tests/test_collector.py`

`run()` launches `_prune_loop` as a background task and cancels it on shutdown. `prune_interval=None` disables the timer (used by the reconnect test to stay focused). `main()` sources the window from `AppConfig`, keeping `config.py` the single source of truth for the default.

- [ ] **Step 1: Write/update the failing tests**

Add `AsyncMock` to the imports at the top of `backend/tests/test_collector.py`:

```python
from unittest.mock import AsyncMock
```

Update the existing reconnect test to opt out of the prune timer (so it exercises only reconnect). Change its `collector.run(...)` call:

```python
    with pytest.raises(_StopTest):
        await collector.run(source, store, max_backoff=30.0, prune_interval=None)
```

Add a new wiring test that proves `run()` starts `_prune_loop` with the retention window converted to a `timedelta` and the given interval:

```python
async def test_run_starts_prune_loop_with_retention(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_prune = AsyncMock()
    monkeypatch.setattr(collector, "_prune_loop", fake_prune)

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(collector.asyncio, "sleep", _no_sleep)

    source = _FakeSource()
    store = _FakeStore()

    with pytest.raises(_StopTest):
        await collector.run(
            source, store, max_backoff=30.0, retention_days=30, prune_interval=123.0
        )

    fake_prune.assert_called_once()
    args, _kwargs = fake_prune.call_args
    assert args[0] is store
    assert args[1] == timedelta(days=30)
    assert args[2] == 123.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_collector.py -q`
Expected: FAIL — `test_run_starts_prune_loop_with_retention` fails because `run()` does not yet accept `retention_days`/`prune_interval` (`TypeError: run() got an unexpected keyword argument`).

- [ ] **Step 3: Wire the prune task into `run()` and `main()`**

In `backend/src/solar_advisor/collector.py`, change the `run()` signature and body. Replace the current `async def run(...) -> None:` definition through the end of the reconnect loop with:

```python
async def run(
    source: TelemetrySource | None = None,
    store: TelemetryStore | None = None,
    *,
    max_backoff: float = 30.0,
    retention_days: int = 90,
    prune_interval: float | None = _PRUNE_INTERVAL_S,
) -> None:
    if source is None:
        source = ReadOnlyMqttClient(
            host=os.environ["SA_MQTT_HOST"],
            port=int(os.environ.get("SA_MQTT_PORT", "1883")),
            username=os.environ.get("SA_MQTT_USER") or None,
            password=os.environ.get("SA_MQTT_PASS") or None,
        )
    if store is None:
        store = SqliteTelemetryStore(Path(os.environ.get("SA_DB_PATH", "solar_advisor.db")))

    prune_task: asyncio.Task[None] | None = None
    if prune_interval is not None:
        prune_task = asyncio.create_task(
            _prune_loop(store, timedelta(days=retention_days), prune_interval)
        )

    try:
        backoff = 1.0
        while True:
            try:
                async for snapshot in source.stream():
                    store.save(snapshot)  # False (downsampled) is normal; ignore.
                    backoff = 1.0  # Reset after any successful message.
            except aiomqtt.MqttError as exc:
                print(
                    f"collector: broker connection lost ({exc}); reconnecting in {backoff:.0f}s",
                    file=sys.stderr,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)
    finally:
        if prune_task is not None:
            prune_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await prune_task
```

Update `main()` to source the window from config:

```python
def main() -> None:
    cfg = load_config()
    asyncio.run(run(retention_days=cfg.telemetry_retention_days))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_collector.py -q`
Expected: PASS — reconnect test, both `_prune_loop` tests, and the new wiring test all green.

- [ ] **Step 5: Commit**

```bash
git add backend/src/solar_advisor/collector.py backend/tests/test_collector.py
git commit -m "feat(collector): run periodic prune task; main() reads retention from config"
```

---

## Task 4: Regression test — pruning never touches `purchases`

**Files:**
- Test: `backend/tests/test_sqlite_store.py`

This is the IMPORTANT safety constraint: the `purchases` table lives in the same DB file but must survive a telemetry prune. `prune_before` already scopes its `DELETE` to the `telemetry` table; this test locks that in so a future change can't regress it.

- [ ] **Step 1: Write the failing test**

Add to the top imports of `backend/tests/test_sqlite_store.py` (it currently imports only `datetime`, `timedelta`, `pytest`, the store, and `make_telemetry`):

```python
from datetime import date

from solar_advisor.domain.purchase import Purchase
from solar_advisor.storage.purchase_store import SqlitePurchaseStore
```

Add the test:

```python
def test_prune_does_not_touch_purchases(tmp_path):
    db = tmp_path / "t.db"
    tstore = SqliteTelemetryStore(db, min_interval=timedelta(0))
    pstore = SqlitePurchaseStore(db)  # same DB file, separate table

    tstore.save(make_telemetry(datetime(2026, 1, 1, 8, 0, 0)))  # old telemetry
    pstore.add(
        Purchase(purchased_at=date(2026, 1, 1), rand=100.0, units_kwh=50.0, note=None)
    )

    removed = tstore.prune_before(datetime(2026, 6, 1))

    assert removed == 1  # the old telemetry row was deleted
    assert tstore.query_range(datetime(2025, 1, 1), datetime(2027, 1, 1)) == []
    assert len(pstore.list_all()) == 1  # the purchase survived the prune
```

- [ ] **Step 2: Run the test to verify it passes immediately (guard test)**

Run: `.venv/bin/pytest tests/test_sqlite_store.py::test_prune_does_not_touch_purchases -q`
Expected: PASS — `prune_before` already scopes to the `telemetry` table, so this passes on the current implementation. It is a guard against future regressions. (If it FAILS, stop: the prune is incorrectly deleting cross-table data — investigate before proceeding.)

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_sqlite_store.py
git commit -m "test(storage): prune must not delete purchases in the shared DB file"
```

---

## Task 5: Wire `SA_TELEMETRY_RETENTION_DAYS` through docker-compose

**Files:**
- Modify: `backend/docker-compose.yml`

Only the `collector` service runs the prune loop, so the env var goes there (matching how `SA_DB_PATH` is set per-service).

- [ ] **Step 1: Add the env var to the collector service**

In `backend/docker-compose.yml`, under `services.collector.environment`, add the variable after `SA_DB_PATH`:

```yaml
  collector:
    build: .
    command: python -m solar_advisor.collector
    environment:
      SA_MQTT_HOST: ${SA_MQTT_HOST:?set in .env}
      SA_MQTT_PORT: ${SA_MQTT_PORT:-1883}
      SA_MQTT_USER: ${SA_MQTT_USER:-}
      SA_MQTT_PASS: ${SA_MQTT_PASS:-}
      SA_DB_PATH: /data/solar_advisor.db
      SA_TELEMETRY_RETENTION_DAYS: ${SA_TELEMETRY_RETENTION_DAYS:-90}
    volumes:
      - sa_data:/data
    restart: unless-stopped
```

- [ ] **Step 2: Validate the compose file**

Run: `docker compose -f backend/docker-compose.yml config >/dev/null && echo OK`
Expected: prints `OK` (compose file parses; the var resolves to its `:-90` default when unset).
If `docker` is unavailable in this environment, skip and instead visually confirm the YAML indentation matches the block above.

- [ ] **Step 3: Commit**

```bash
git add backend/docker-compose.yml
git commit -m "chore(compose): pass SA_TELEMETRY_RETENTION_DAYS to the collector"
```

---

## Final verification

- [ ] **Step 1: Run the full check suite from `backend/`**

Run: `make check`
Expected: `ruff check` + `ruff format --check` clean, `mypy` (strict) clean, `lint-imports` reports all contracts kept, `pytest` all green.

- [ ] **Step 2: If `mypy` flags the `sleep=asyncio.sleep` default**

`asyncio.sleep` is assignable to `Callable[[float], Awaitable[None]]` (its second arg has a default). If mypy strict objects in this environment, wrap it instead of changing behavior:

```python
async def _default_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)
```

and use `sleep: Callable[[float], Awaitable[None]] = _default_sleep`. Re-run `make typecheck`.

- [ ] **Step 3: Confirm done**

All five tasks committed, `make check` green. The collector now prunes telemetry older than `SA_TELEMETRY_RETENTION_DAYS` (default 90) every 6 hours; the `purchases` table is never touched.

---

## Self-review notes (completed during planning)

- **Spec coverage:** periodic prune in collector loop (Tasks 2–3), `SA_*` env var in `config.py` (Task 1), docker-compose wiring (Task 5), purchases-not-pruned (Task 4 + scoping already in `prune_before`), test for the prune timer/window (Tasks 2–3). TDD + ruff/mypy/import-linter via `make check` (Final).
- **Type consistency:** `_prune_loop(store, retention: timedelta, interval: float, *, clock, sleep)` is called identically in `run()` and asserted with the same arg positions in the wiring test. `telemetry_retention_days: int` is read as `int(...)` and passed as `retention_days: int` → `timedelta(days=...)`.
- **No placeholders:** every code/test step shows complete code and exact commands with expected output.
