# tests/test_tariff_derivation.py
from datetime import date

from solar_advisor.domain.purchase import Purchase
from solar_advisor.tariff.derivation import DerivedRate, derive_marginal_rate

TODAY = date(2026, 6, 25)


def _p(d: date, rand: float, units: float) -> Purchase:
    return Purchase(purchased_at=d, rand=rand, units_kwh=units)


def test_empty_falls_back_to_config():
    result = derive_marginal_rate([], window_days=90, today=TODAY, fallback_rate=3.56)
    assert result == DerivedRate(rate=3.56, source="config", source_date=None)


def test_picks_minimum_effective_rate_ignoring_fixed_charge_contamination():
    # First-of-month buy is inflated (units lost to the fixed charge); a later
    # same-month buy reveals the true marginal rate. The MIN must win.
    contaminated = _p(date(2026, 6, 1), rand=1000.0, units=250.0)  # 4.00 R/kWh
    clean = _p(date(2026, 6, 15), rand=1000.0, units=280.9)  # ~3.56 R/kWh
    result = derive_marginal_rate(
        [contaminated, clean], window_days=90, today=TODAY, fallback_rate=9.99
    )
    assert result.source == "purchase"
    assert result.source_date == date(2026, 6, 15)
    assert round(result.rate, 2) == 3.56


def test_purchases_outside_window_are_ignored():
    old_cheap = _p(date(2026, 1, 1), rand=1000.0, units=400.0)  # 2.50, but >90d old
    recent = _p(date(2026, 6, 10), rand=1000.0, units=280.9)  # ~3.56
    result = derive_marginal_rate(
        [old_cheap, recent], window_days=90, today=TODAY, fallback_rate=9.99
    )
    assert result.source_date == date(2026, 6, 10)
    assert round(result.rate, 2) == 3.56


def test_april_step_up_as_old_cheap_buys_age_out():
    # Before April: 3.30. After the hike: 3.56. Once the cheap buys leave the
    # window, the derived marginal rate steps UP to the new floor.
    purchases = [
        _p(date(2026, 3, 5), rand=1000.0, units=303.0),  # ~3.30 (pre-hike)
        _p(date(2026, 6, 5), rand=1000.0, units=280.9),  # ~3.56 (post-hike)
    ]
    # Wide window still sees the cheap March buy.
    wide = derive_marginal_rate(purchases, window_days=180, today=TODAY, fallback_rate=9.99)
    assert round(wide.rate, 2) == 3.30
    # 90-day window: March 5 is >90 days before June 25, so it ages out.
    narrow = derive_marginal_rate(purchases, window_days=90, today=TODAY, fallback_rate=9.99)
    assert round(narrow.rate, 2) == 3.56


def test_purchase_exactly_on_window_boundary_is_included():
    boundary = _p(date(2026, 3, 27), rand=1000.0, units=300.0)  # exactly 90 days before
    result = derive_marginal_rate([boundary], window_days=90, today=TODAY, fallback_rate=9.99)
    assert result.source == "purchase"
    assert round(result.rate, 3) == round(1000.0 / 300.0, 3)


def test_future_dated_and_nonpositive_rows_are_skipped():
    future = _p(date(2026, 7, 1), rand=10.0, units=100.0)  # 0.10 but in the future
    zero_units = _p(date(2026, 6, 1), rand=1000.0, units=0.0)
    good = _p(date(2026, 6, 2), rand=1000.0, units=280.9)
    result = derive_marginal_rate(
        [future, zero_units, good], window_days=90, today=TODAY, fallback_rate=9.99
    )
    assert result.source_date == date(2026, 6, 2)
