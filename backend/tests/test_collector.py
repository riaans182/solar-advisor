# tests/test_collector.py
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import aiomqtt
import pytest

from solar_advisor import collector
from solar_advisor.domain.telemetry import Telemetry
from tests.conftest import make_telemetry


class _StopTest(Exception):
    """Sentinel used to break the otherwise-infinite reconnect loop."""


class _FakeSource:
    """Raises MqttError on the first stream() call, then yields one snapshot
    on the second call and stops the loop -- proving a reconnect happened."""

    def __init__(self) -> None:
        self.calls = 0
        self.snapshot = make_telemetry(datetime(2026, 6, 22, 8, 0, 0, tzinfo=UTC))

    async def stream(self) -> AsyncIterator[Telemetry]:
        self.calls += 1
        if self.calls == 1:
            raise aiomqtt.MqttError("simulated disconnect")
        yield self.snapshot
        raise _StopTest


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


async def test_run_reconnects_after_mqtt_error(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _FakeSource()
    store = _FakeStore()

    # Don't actually wait for backoff.
    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(collector.asyncio, "sleep", _no_sleep)

    with pytest.raises(_StopTest):
        await collector.run(source, store, max_backoff=30.0, prune_interval=None)

    # First stream() raised MqttError; the loop retried and the second stream()
    # produced exactly the one post-reconnect snapshot.
    assert source.calls == 2
    assert store.saved == [source.snapshot]


async def test_prune_loop_prunes_at_retention_cutoff() -> None:
    store = _FakeStore(prune_result=5)
    fixed_now = datetime(2026, 6, 26, 12, 0, 0, tzinfo=UTC)
    sleep_calls = 0

    async def fake_sleep(seconds: float) -> None:
        nonlocal sleep_calls
        assert seconds == 3600.0
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
    expected = fixed_now - timedelta(days=7)
    assert store.prune_cutoffs == [expected, expected, expected]


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
