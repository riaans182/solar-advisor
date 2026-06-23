# tests/test_collector.py
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import aiomqtt
import pytest

from solar_advisor import collector
from solar_advisor.domain.telemetry import Telemetry


def _snap(ts: datetime) -> Telemetry:
    return Telemetry(
        ts=ts,
        battery_soc=64.0,
        battery_power=85,
        battery_voltage=50,
        battery_current=1.7,
        pv_power=106,
        grid_power=1140,
        load_power=1086,
        load_power_essential=1136,
        grid_energy_in=1000,
        grid_energy_out=0,
        pv_energy=0,
        load_energy=0,
        battery_energy_in=0,
        battery_energy_out=0,
        month_to_date_grid_import_kwh=12.5,
    )


class _StopTest(Exception):
    """Sentinel used to break the otherwise-infinite reconnect loop."""


class _FakeSource:
    """Raises MqttError on the first stream() call, then yields one snapshot
    on the second call and stops the loop -- proving a reconnect happened."""

    def __init__(self) -> None:
        self.calls = 0
        self.snapshot = _snap(datetime(2026, 6, 22, 8, 0, 0, tzinfo=UTC))

    async def stream(self) -> AsyncIterator[Telemetry]:
        self.calls += 1
        if self.calls == 1:
            raise aiomqtt.MqttError("simulated disconnect")
        yield self.snapshot
        raise _StopTest


class _FakeStore:
    def __init__(self) -> None:
        self.saved: list[Telemetry] = []

    def save(self, snapshot: Telemetry) -> bool:
        self.saved.append(snapshot)
        return True

    def query_range(self, start: datetime, end: datetime) -> list[Telemetry]:
        return []

    def prune_before(self, cutoff: datetime) -> int:
        return 0


async def test_run_reconnects_after_mqtt_error(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _FakeSource()
    store = _FakeStore()

    # Don't actually wait for backoff.
    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(collector.asyncio, "sleep", _no_sleep)

    with pytest.raises(_StopTest):
        await collector.run(source, store, max_backoff=30.0)

    # First stream() raised MqttError; the loop retried and the second stream()
    # produced exactly the one post-reconnect snapshot.
    assert source.calls == 2
    assert store.saved == [source.snapshot]
