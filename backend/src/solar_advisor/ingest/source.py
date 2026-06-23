# src/solar_advisor/ingest/source.py
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from solar_advisor.domain.telemetry import Telemetry


@runtime_checkable
class TelemetrySource(Protocol):
    """A source of normalized telemetry snapshots. Implementations own all
    vendor-specific transport/topic detail (spec §3.1)."""

    def stream(self) -> AsyncIterator[Telemetry]: ...
