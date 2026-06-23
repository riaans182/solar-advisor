# src/solar_advisor/ingest/accumulator.py
from __future__ import annotations

from datetime import datetime


class MonthToDateAccumulator:
    """Derives month-to-date grid import from a lifetime-cumulative counter.

    Rebases the baseline at month rollover and on counter resets (value drops).
    """

    def __init__(self) -> None:
        self._month: tuple[int, int] | None = None
        self._baseline: float | None = None
        self._last: float | None = None

    def update(self, ts: datetime, cumulative_kwh: float) -> float:
        month = (ts.year, ts.month)
        reset = self._last is not None and cumulative_kwh < self._last
        if self._month != month or self._baseline is None or reset:
            self._month = month
            self._baseline = cumulative_kwh
        self._last = cumulative_kwh
        return round(cumulative_kwh - self._baseline, 6)
