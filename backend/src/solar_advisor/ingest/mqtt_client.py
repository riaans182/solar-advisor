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
