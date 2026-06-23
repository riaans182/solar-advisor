# src/solar_advisor/storage/store.py
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from solar_advisor.domain.telemetry import Telemetry


class TelemetryStore(Protocol):
    def save(self, snapshot: Telemetry) -> bool: ...
    def query_range(self, start: datetime, end: datetime) -> list[Telemetry]: ...
    def prune_before(self, cutoff: datetime) -> int: ...
