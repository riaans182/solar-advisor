# tests/test_purchase_domain.py
from datetime import date

from solar_advisor.domain.purchase import Purchase


def test_effective_rate_is_rand_over_units():
    p = Purchase(purchased_at=date(2026, 4, 12), rand=1000.0, units_kwh=280.9)
    assert round(p.effective_rate, 4) == round(1000.0 / 280.9, 4)


def test_id_and_note_default_to_none():
    p = Purchase(purchased_at=date(2026, 4, 12), rand=500.0, units_kwh=140.0)
    assert p.id is None
    assert p.note is None
