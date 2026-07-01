# src/solar_advisor/estimation/estimator.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from solar_advisor.domain.telemetry import Telemetry
from solar_advisor.storage.store import TelemetryStore


@dataclass(frozen=True, slots=True)
class EstimatedParameters:
    """Estimated inverter parameters.

    `daily_consumption_kwh` is only meaningful when `daily_consumption_confidence > 0`;
    with insufficient data it is reported as 0.0 (a physically-wrong "zero load"), so
    callers MUST gate on `daily_consumption_confidence` before using it."""

    usable_kwh: float
    usable_kwh_confidence: float  # 0..1
    daily_consumption_kwh: float  # meaningful only when daily_consumption_confidence > 0
    daily_consumption_confidence: float  # 0..1


class ParameterEstimator:
    """Derives values the inverter doesn't report from stored telemetry history.
    I/O lives here, outside the pure engine; results are passed to the engine as
    plain inputs (spec §5.2)."""

    def __init__(self, store: TelemetryStore, nominal_kwh: float) -> None:
        self._store = store
        self._nominal_kwh = nominal_kwh

    def estimate(self, start: datetime, end: datetime) -> EstimatedParameters:
        """Estimate parameters from stored telemetry over [start, end].

        Note: `daily_consumption_kwh` in the result is only meaningful when
        `daily_consumption_confidence > 0`; callers MUST gate on that confidence."""
        rows = self._store.query_range(start, end)
        usable_kwh, usable_conf = self._estimate_capacity(rows)
        daily_kwh, daily_conf = self._estimate_daily_consumption(rows)
        return EstimatedParameters(
            usable_kwh=usable_kwh,
            usable_kwh_confidence=usable_conf,
            daily_consumption_kwh=daily_kwh,
            daily_consumption_confidence=daily_conf,
        )

    def energy_since(self, start: datetime, end: datetime) -> tuple[float, float]:
        """(pv_kwh, load_kwh) generated/consumed over [start, end], derived from the
        cumulative meter counters (last minus first). Returns (0.0, 0.0) when the
        window has no data. Negative deltas (a counter reset) are clamped to 0."""
        rows = self._store.query_range(start, end)
        if not rows:
            return (0.0, 0.0)
        first, last = rows[0], rows[-1]
        return (
            max(0.0, last.pv_energy - first.pv_energy),
            max(0.0, last.load_energy - first.load_energy),
        )

    def _estimate_capacity(self, rows: list[Telemetry]) -> tuple[float, float]:
        """Capacity = battery_energy_out delta over a single discharge run / fractional
        SOC drop. Estimates over the largest contiguous monotonically falling-SOC run
        (NOT the global SOC max/min) so the SOC span and the energy_out delta measure the
        SAME discharge; a window with a recharge between discharges would otherwise sum
        all discharge energy against one span and inflate the estimate.
        Relies on `query_range` returning rows in ascending `ts` order."""
        if len(rows) < 2:
            return self._nominal_kwh, 0.0
        # Walk contiguous segments where battery_soc is non-increasing and pick the run
        # with the largest SOC span (ties: largest energy_out delta).
        best_span = 0.0
        best_energy_out = 0.0
        run_start = rows[0]
        for prev, curr in zip(rows, rows[1:], strict=False):
            if curr.battery_soc > prev.battery_soc:
                run_start = curr  # SOC rose => recharge; start a fresh run
                continue
            span = run_start.battery_soc - curr.battery_soc
            energy_out = curr.battery_energy_out - run_start.battery_energy_out
            if span > best_span or (span == best_span and energy_out > best_energy_out):
                best_span = span
                best_energy_out = energy_out
        if best_span <= 0 or best_energy_out <= 0:
            return self._nominal_kwh, 0.0
        usable_kwh = best_energy_out / (best_span / 100.0)
        confidence = min(1.0, best_span / 80.0)  # an ~80% swing => full confidence
        return usable_kwh, confidence

    def _estimate_daily_consumption(self, rows: list[Telemetry]) -> tuple[float, float]:
        """Daily kWh = load_energy delta normalised to a per-day rate.
        Relies on `query_range` returning rows in ascending `ts` order."""
        if len(rows) < 2:
            return 0.0, 0.0
        first, last = rows[0], rows[-1]
        days = (last.ts - first.ts).total_seconds() / 86400.0
        if days <= 0:
            return 0.0, 0.0
        daily_kwh = (last.load_energy - first.load_energy) / days
        confidence = min(1.0, days / 7.0)  # a week of data => full confidence
        return daily_kwh, confidence
