# src/solar_advisor/storage/store.py
from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from solar_advisor.domain.telemetry import Telemetry


@runtime_checkable
class TelemetryStore(Protocol):
    def save(self, snapshot: Telemetry) -> bool: ...
    # query_range returns rows ordered by ascending `ts`.
    def query_range(self, start: datetime, end: datetime) -> list[Telemetry]: ...
    # query_bucketed aggregates the range into time buckets (SQL AVG per metric),
    # returning one Telemetry per bucket ordered by ascending ts.
    def query_bucketed(
        self, start: datetime, end: datetime, bucket_seconds: int
    ) -> list[Telemetry]: ...
    def prune_before(self, cutoff: datetime) -> int: ...
