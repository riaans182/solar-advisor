# tests/test_tariff_provider.py
from datetime import date

from solar_advisor.domain.purchase import Purchase
from solar_advisor.tariff.provider import TariffProvider


class _FakeReader:
    def __init__(self, purchases: list[Purchase]) -> None:
        self._purchases = purchases
        self.called_cutoff: date | None = None

    def list_since(self, cutoff: date) -> list[Purchase]:
        self.called_cutoff = cutoff
        return [p for p in self._purchases if p.purchased_at >= cutoff]


def test_uses_cutoff_from_window_days():
    reader = _FakeReader([])
    provider = TariffProvider(reader=reader, fallback_rate=3.56, window_days=90)
    provider.current_rate(date(2026, 6, 25))
    assert reader.called_cutoff == date(2026, 3, 27)


def test_derives_from_purchases_when_present():
    reader = _FakeReader([Purchase(purchased_at=date(2026, 6, 1), rand=1000.0, units_kwh=280.9)])
    provider = TariffProvider(reader=reader, fallback_rate=9.99, window_days=90)
    derived = provider.current_rate(date(2026, 6, 25))
    assert derived.source == "purchase"
    assert round(derived.rate, 2) == 3.56


def test_falls_back_when_no_purchases():
    provider = TariffProvider(reader=_FakeReader([]), fallback_rate=3.56, window_days=90)
    derived = provider.current_rate(date(2026, 6, 25))
    assert derived.source == "config"
    assert derived.rate == 3.56
