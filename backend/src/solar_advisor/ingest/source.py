# src/solar_advisor/ingest/source.py
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from solar_advisor.domain.telemetry import Telemetry


class TelemetrySource(Protocol):
    """A source of normalized telemetry snapshots. Implementations own all
    vendor-specific transport/topic detail (spec §3.1)."""

    def stream(self) -> AsyncIterator[Telemetry]: ...
