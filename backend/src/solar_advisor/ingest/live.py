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
    persistence reuses the store's append-only API (spec §7).

    Consistency contract: `telemetry` and `schedule` are each independently the
    latest known value, updated atomically via whole-reference reassignment of
    immutable snapshots (no lock). A reader may therefore observe a `telemetry`
    and a `schedule` captured at slightly different moments; this is acceptable
    for advisory display."""

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
                    topic = str(message.topic)
                    try:
                        state.handle(datetime.now(UTC), topic, payload)
                    except Exception as exc:
                        print(
                            f"live-ingest: skipping bad message on {topic}: {exc}",
                            file=sys.stderr,
                        )
                        continue
                    backoff = 1.0
        except aiomqtt.MqttError as exc:
            print(f"live-ingest: connection lost ({exc}); retry in {backoff:.0f}s", file=sys.stderr)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
