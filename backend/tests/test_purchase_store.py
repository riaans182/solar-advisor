# tests/test_purchase_store.py
from datetime import date

import pytest

from solar_advisor.domain.purchase import Purchase
from solar_advisor.storage.purchase_store import PurchaseStore, SqlitePurchaseStore


@pytest.fixture
def store(tmp_path):
    return SqlitePurchaseStore(tmp_path / "p.db")


def _p(d: date, rand=1000.0, units=280.9, note=None) -> Purchase:
    return Purchase(purchased_at=d, rand=rand, units_kwh=units, note=note)


def test_add_returns_row_with_id(store):
    saved = store.add(_p(date(2026, 6, 1)))
    assert saved.id is not None
    assert saved.purchased_at == date(2026, 6, 1)


def test_list_all_is_newest_first(store):
    store.add(_p(date(2026, 6, 1)))
    store.add(_p(date(2026, 6, 15)))
    store.add(_p(date(2026, 6, 10)))
    dates = [p.purchased_at for p in store.list_all()]
    assert dates == [date(2026, 6, 15), date(2026, 6, 10), date(2026, 6, 1)]


def test_list_since_filters_by_cutoff(store):
    store.add(_p(date(2026, 1, 1)))
    store.add(_p(date(2026, 6, 1)))
    since = store.list_since(date(2026, 3, 1))
    assert [p.purchased_at for p in since] == [date(2026, 6, 1)]


def test_delete_existing_and_missing(store):
    saved = store.add(_p(date(2026, 6, 1)))
    assert store.delete(saved.id) is True
    assert store.delete(saved.id) is False  # already gone
    assert store.list_all() == []


def test_note_round_trips(store):
    store.add(_p(date(2026, 6, 1), note="City of CT prepaid"))
    assert store.list_all()[0].note == "City of CT prepaid"


def test_data_persists_across_reopen(tmp_path):
    db = tmp_path / "p.db"
    store = SqlitePurchaseStore(db)
    store.add(_p(date(2026, 6, 1)))
    store.close()
    reopened = SqlitePurchaseStore(db)
    assert len(reopened.list_all()) == 1


def test_satisfies_protocol(store):
    assert isinstance(store, PurchaseStore)
