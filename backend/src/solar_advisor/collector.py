# src/solar_advisor/collector.py
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import aiomqtt

from solar_advisor.ingest.mqtt_client import ReadOnlyMqttClient
from solar_advisor.ingest.source import TelemetrySource
from solar_advisor.storage.sqlite_store import SqliteTelemetryStore
from solar_advisor.storage.store import TelemetryStore


async def run(
    source: TelemetrySource | None = None,
    store: TelemetryStore | None = None,
    *,
    max_backoff: float = 30.0,
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


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
