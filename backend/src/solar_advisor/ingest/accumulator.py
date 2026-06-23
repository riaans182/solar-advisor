# src/solar_advisor/ingest/accumulator.py
from __future__ import annotations

import math
from datetime import datetime


class MonthToDateAccumulator:
    """Derives month-to-date grid import from a lifetime-cumulative counter.

    Rebases the baseline at month rollover and on counter resets (value drops).
    Non-finite readings (NaN/inf) are ignored and do not corrupt state: the
    accumulator returns the last good month-to-date and leaves its state intact.
    """

    def __init__(self) -> None:
        self._month: tuple[int, int] | None = None
        self._baseline: float | None = None
        self._last: float | None = None

    def update(self, ts: datetime, cumulative_kwh: float) -> float:
        if not math.isfinite(cumulative_kwh):
            # Ignore non-finite readings; do not mutate state.
            if self._baseline is not None and self._last is not None:
                return round(self._last - self._baseline, 6)
            return 0.0
        month = (ts.year, ts.month)
        reset = self._last is not None and cumulative_kwh < self._last
        if self._month != month or self._baseline is None or reset:
            self._month = month
            self._baseline = cumulative_kwh
        self._last = cumulative_kwh
        return round(cumulative_kwh - self._baseline, 6)
