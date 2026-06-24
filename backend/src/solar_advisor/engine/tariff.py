# src/solar_advisor/engine/tariff.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class TariffModel(Protocol):
    """A tariff. The protocol is kept (not collapsed to a constant) so a future
    inclining-block adapter can return without touching the engine (spec §6)."""

    def marginal_rate(self, month_to_date_kwh: float) -> float: ...
    def monthly_cost(self, import_kwh: float, days_in_month: int) -> float: ...


@dataclass(frozen=True, slots=True)
class FlatRateTariff:
    """Eskom Direct prepaid flat rate: constant per-kWh marginal rate; the monthly
    fixed charge is a sunk cost that affects only bill projection (spec §6)."""

    energy_rate: float  # R/kWh
    monthly_fixed_charge: float  # R/month

    def marginal_rate(self, month_to_date_kwh: float) -> float:
        return self.energy_rate

    def monthly_cost(self, import_kwh: float, days_in_month: int) -> float:
        # days_in_month is the protocol seam for future partial-month
        # fixed-charge proration; the flat impl ignores it.
        return self.monthly_fixed_charge + import_kwh * self.energy_rate
