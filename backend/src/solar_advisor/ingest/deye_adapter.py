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
