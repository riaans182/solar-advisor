# src/solar_advisor/collector.py
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

# Prune a few times a day: deletes stay small and the 90-day boundary never lags far.
_PRUNE_INTERVAL_S = 6 * 60 * 60


async def _prune_loop(
    store: TelemetryStore,
    retention: timedelta,
    interval_s: float,
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
        await sleep(interval_s)


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


def main() -> None:
    cfg = load_config()
    asyncio.run(run(retention_days=cfg.telemetry_retention_days))


if __name__ == "__main__":
    main()
