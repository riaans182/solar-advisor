# src/solar_advisor/estimation/estimator.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from solar_advisor.domain.telemetry import Telemetry
from solar_advisor.storage.store import TelemetryStore


@dataclass(frozen=True, slots=True)
class EstimatedParameters:
    usable_kwh: float
    usable_kwh_confidence: float  # 0..1
    daily_consumption_kwh: float
    daily_consumption_confidence: float  # 0..1


class ParameterEstimator:
    """Derives values the inverter doesn't report from stored telemetry history.
    I/O lives here, outside the pure engine; results are passed to the engine as
    plain inputs (spec §5.2)."""

    def __init__(self, store: TelemetryStore, nominal_kwh: float) -> None:
        self._store = store
        self._nominal_kwh = nominal_kwh

    def estimate(self, start: datetime, end: datetime) -> EstimatedParameters:
        rows = self._store.query_range(start, end)
        usable_kwh, usable_conf = self._estimate_capacity(rows)
        daily_kwh, daily_conf = self._estimate_daily_consumption(rows)
        return EstimatedParameters(
            usable_kwh=usable_kwh,
            usable_kwh_confidence=usable_conf,
            daily_consumption_kwh=daily_kwh,
            daily_consumption_confidence=daily_conf,
        )

    def _estimate_capacity(self, rows: list[Telemetry]) -> tuple[float, float]:
        """Capacity = battery_energy_out over a falling-SOC run / fractional SOC drop.
        Scans for the largest SOC span and uses the energy_out delta across it."""
        if len(rows) < 2:
            return self._nominal_kwh, 0.0
        soc_hi = max(rows, key=lambda r: r.battery_soc)
        soc_lo = min(rows, key=lambda r: r.battery_soc)
        soc_span = soc_hi.battery_soc - soc_lo.battery_soc
        energy_out = soc_lo.battery_energy_out - soc_hi.battery_energy_out
        if soc_span <= 0 or energy_out <= 0:
            return self._nominal_kwh, 0.0
        usable_kwh = energy_out / (soc_span / 100.0)
        confidence = min(1.0, soc_span / 80.0)  # an ~80% swing => full confidence
        return usable_kwh, confidence

    def _estimate_daily_consumption(self, rows: list[Telemetry]) -> tuple[float, float]:
        """Daily kWh = load_energy delta normalised to a per-day rate."""
        if len(rows) < 2:
            return 0.0, 0.0
        first, last = rows[0], rows[-1]
        days = (last.ts - first.ts).total_seconds() / 86400.0
        if days <= 0:
            return 0.0, 0.0
        daily_kwh = (last.load_energy - first.load_energy) / days
        confidence = min(1.0, days / 7.0)  # a week of data => full confidence
        return daily_kwh, confidence
