# src/solar_advisor/tariff/derivation.py
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from solar_advisor.domain.purchase import Purchase


@dataclass(frozen=True, slots=True)
class DerivedRate:
    """The marginal R/kWh the engine should use, plus where it came from."""

    rate: float
    source: Literal["purchase", "config"]
    source_date: date | None


def derive_marginal_rate(
    purchases: Sequence[Purchase],
    *,
    window_days: int,
    today: date,
    fallback_rate: float,
) -> DerivedRate:
    """Marginal rate = the lowest effective R/kWh among purchases in the trailing
    window. The minimum is the least fixed-charge-contaminated estimate of the true
    flat energy rate. Falls back to ``fallback_rate`` when the window is empty."""

    cutoff = today - timedelta(days=window_days)
    best: Purchase | None = None
    best_rate = math.inf
    for p in purchases:
        if p.purchased_at < cutoff or p.purchased_at > today:
            continue
        if p.units_kwh <= 0 or p.rand <= 0:
            continue
        rate = p.rand / p.units_kwh
        if not math.isfinite(rate):
            continue
        if rate < best_rate:
            best, best_rate = p, rate
    if best is None:
        return DerivedRate(rate=fallback_rate, source="config", source_date=None)
    return DerivedRate(rate=best_rate, source="purchase", source_date=best.purchased_at)
