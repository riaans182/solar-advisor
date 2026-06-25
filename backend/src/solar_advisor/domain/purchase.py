# src/solar_advisor/domain/purchase.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class Purchase:
    """A user-entered prepaid electricity purchase.

    ``effective_rate`` (rand/unit) is derived, never stored, so it cannot drift
    from the two recorded numbers.
    """

    purchased_at: date
    rand: float
    units_kwh: float
    note: str | None = None
    id: int | None = None

    @property
    def effective_rate(self) -> float:
        return self.rand / self.units_kwh
