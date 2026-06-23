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
