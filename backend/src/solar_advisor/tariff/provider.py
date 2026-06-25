# src/solar_advisor/tariff/provider.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

from solar_advisor.domain.purchase import Purchase
from solar_advisor.tariff.derivation import DerivedRate, derive_marginal_rate


class PurchaseReader(Protocol):
    def list_since(self, cutoff: date) -> list[Purchase]: ...


@dataclass(frozen=True, slots=True)
class TariffProvider:
    """Wires the purchase store to the pure derivation. Reads only the trailing
    window for efficiency; the derivation re-applies the window bound authoritatively."""

    reader: PurchaseReader
    fallback_rate: float
    window_days: int = 90

    def current_rate(self, today: date) -> DerivedRate:
        cutoff = today - timedelta(days=self.window_days)
        purchases = self.reader.list_since(cutoff)
        return derive_marginal_rate(
            purchases,
            window_days=self.window_days,
            today=today,
            fallback_rate=self.fallback_rate,
        )
