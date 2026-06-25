# Plan F — Purchase Tracker Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture prepaid electricity purchases in the app's own database and derive the engine's marginal tariff (min effective R/kWh over a trailing window) from them, falling back to config when no purchases exist.

**Architecture:** A pure `derive_marginal_rate` function (no I/O) computes the rate + provenance from a list of `Purchase` records. A `SqlitePurchaseStore` (the app's first write target, NOT the inverter) persists purchases in the telemetry database file. A `TariffProvider` wires store→derivation and is injected into `RecommendationService`, which now builds `FlatRateTariff` from the derived rate. Three new endpoints (`POST`/`GET`/`DELETE /api/purchases`) are the app's first non-GET routes; they write only to our own DB, so the read-only-against-the-inverter invariant holds.

**Tech Stack:** Python 3.12, FastAPI + Pydantic v2, stdlib sqlite3, pytest, ruff, mypy --strict, import-linter.

**Reference (read before starting):** spec `docs/superpowers/specs/2026-06-25-purchase-tracker-design.md`. Existing patterns to mirror: `backend/src/solar_advisor/storage/sqlite_store.py` (sqlite store), `backend/src/solar_advisor/storage/store.py` (Protocol), `backend/src/solar_advisor/domain/telemetry.py` (frozen dataclass), `backend/tests/test_sqlite_store.py`, `backend/tests/test_recommendation_service.py`, `backend/tests/test_api.py` (test style + `_config()` helper). All commands run from `backend/`.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/solar_advisor/domain/purchase.py` (create) | `Purchase` frozen dataclass + `effective_rate` property. |
| `src/solar_advisor/tariff/__init__.py` (create) | New package marker. (Distinct from `engine/tariff.py`: this package *derives* a rate from purchases; `engine/tariff.py` *uses* a rate in cost math.) |
| `src/solar_advisor/tariff/derivation.py` (create) | Pure `derive_marginal_rate()` + `DerivedRate`. No storage/IO imports. |
| `src/solar_advisor/tariff/provider.py` (create) | `TariffProvider` (store→derivation) + `PurchaseReader` Protocol. |
| `src/solar_advisor/storage/purchase_store.py` (create) | `SqlitePurchaseStore` + `PurchaseStore` Protocol (CRUD). |
| `src/solar_advisor/config.py` (modify) | Add `tariff_window_days` (env `SA_TARIFF_WINDOW_DAYS`, default 90). |
| `src/solar_advisor/services/recommendation.py` (modify) | Inject optional `tariff_provider`; build `FlatRateTariff` from derived rate; add `tariff_source`/`tariff_source_date` to `DashboardData`. |
| `src/solar_advisor/api/schemas.py` (modify) | `PurchaseCreate`, `PurchaseView`, `PurchaseListView`; add `tariff_source`/`tariff_source_date` to `DashboardView`. |
| `src/solar_advisor/api/app.py` (modify) | `get_purchase_store` dep; POST/GET/DELETE `/api/purchases`; CORS allow POST/DELETE; wire store + provider in `create_production_app`. |
| `tests/test_purchase_domain.py` (create) | `Purchase.effective_rate`. |
| `tests/test_tariff_derivation.py` (create) | The derivation logic (heart of the feature). |
| `tests/test_purchase_store.py` (create) | Store round-trip. |
| `tests/test_tariff_provider.py` (create) | Provider wiring. |
| `tests/test_recommendation_service.py` (modify) | Derived-rate integration. |
| `tests/test_api_purchases.py` (create) | Endpoint behavior. |

---

## Group 1 — Domain & pure derivation

### Task 1: `Purchase` domain model

**Files:**
- Create: `src/solar_advisor/domain/purchase.py`
- Test: `tests/test_purchase_domain.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_purchase_domain.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'solar_advisor.domain.purchase'`

- [ ] **Step 3: Write minimal implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_purchase_domain.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/solar_advisor/domain/purchase.py tests/test_purchase_domain.py
git commit -m "feat: add Purchase domain model"
```

### Task 2: `derive_marginal_rate` pure function

**Files:**
- Create: `src/solar_advisor/tariff/__init__.py` (empty)
- Create: `src/solar_advisor/tariff/derivation.py`
- Test: `tests/test_tariff_derivation.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tariff_derivation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'solar_advisor.tariff'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/solar_advisor/tariff/__init__.py
```

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tariff_derivation.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/solar_advisor/tariff/__init__.py src/solar_advisor/tariff/derivation.py tests/test_tariff_derivation.py
git commit -m "feat: derive marginal tariff from purchases (min effective rate over window)"
```

---

## Group 2 — Storage & provider

### Task 3: `SqlitePurchaseStore` + `PurchaseStore` Protocol

**Files:**
- Create: `src/solar_advisor/storage/purchase_store.py`
- Test: `tests/test_purchase_store.py`

- [ ] **Step 1: Write the failing test**

```python
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
    saved = store.add(_p(date(2026, 6, 1), note="City of CT prepaid"))
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_purchase_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'solar_advisor.storage.purchase_store'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/solar_advisor/storage/purchase_store.py
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Protocol, runtime_checkable

from solar_advisor.domain.purchase import Purchase


@runtime_checkable
class PurchaseStore(Protocol):
    def add(self, purchase: Purchase) -> Purchase: ...
    def list_all(self) -> list[Purchase]: ...
    def list_since(self, cutoff: date) -> list[Purchase]: ...
    def delete(self, purchase_id: int) -> bool: ...


class SqlitePurchaseStore:
    """User-entered prepaid purchase log.

    This is the app's only write target besides telemetry, and it is NOT the
    inverter — writing purchases here does not relax the read-only-against-the-
    inverter invariant (no MQTT publish path is added). It shares the telemetry
    database file via its own connection; manual entry makes writes rare, so lock
    contention with the telemetry collector is negligible. check_same_thread=False
    lets the FastAPI threadpool serve reads/writes (sqlite3 serialises internally).

    ISO date strings sort lexicographically in chronological order, so range
    comparisons (``purchased_at >= ?``) and ``ORDER BY`` work directly on the text.
    """

    def __init__(self, path: Path | str) -> None:
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS purchases ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "purchased_at TEXT NOT NULL, "
            "rand REAL NOT NULL, "
            "units_kwh REAL NOT NULL, "
            "note TEXT)"
        )
        self._conn.commit()

    def add(self, purchase: Purchase) -> Purchase:
        cur = self._conn.execute(
            "INSERT INTO purchases (purchased_at, rand, units_kwh, note) VALUES (?, ?, ?, ?)",
            (
                purchase.purchased_at.isoformat(),
                purchase.rand,
                purchase.units_kwh,
                purchase.note,
            ),
        )
        self._conn.commit()
        return Purchase(
            id=cur.lastrowid,
            purchased_at=purchase.purchased_at,
            rand=purchase.rand,
            units_kwh=purchase.units_kwh,
            note=purchase.note,
        )

    def list_all(self) -> list[Purchase]:
        cur = self._conn.execute(
            "SELECT id, purchased_at, rand, units_kwh, note FROM purchases "
            "ORDER BY purchased_at DESC, id DESC"
        )
        return [self._row(r) for r in cur.fetchall()]

    def list_since(self, cutoff: date) -> list[Purchase]:
        cur = self._conn.execute(
            "SELECT id, purchased_at, rand, units_kwh, note FROM purchases "
            "WHERE purchased_at >= ? ORDER BY purchased_at DESC, id DESC",
            (cutoff.isoformat(),),
        )
        return [self._row(r) for r in cur.fetchall()]

    def delete(self, purchase_id: int) -> bool:
        cur = self._conn.execute("DELETE FROM purchases WHERE id = ?", (purchase_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _row(r: tuple[int, str, float, float, str | None]) -> Purchase:
        return Purchase(
            id=r[0],
            purchased_at=date.fromisoformat(r[1]),
            rand=r[2],
            units_kwh=r[3],
            note=r[4],
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_purchase_store.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/solar_advisor/storage/purchase_store.py tests/test_purchase_store.py
git commit -m "feat: add SqlitePurchaseStore (app's own DB, not the inverter)"
```

### Task 4: `TariffProvider`

**Files:**
- Create: `src/solar_advisor/tariff/provider.py`
- Test: `tests/test_tariff_provider.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tariff_provider.py -v`
Expected: FAIL — `ImportError: cannot import name 'TariffProvider'`

- [ ] **Step 3: Write minimal implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tariff_provider.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/solar_advisor/tariff/provider.py tests/test_tariff_provider.py
git commit -m "feat: add TariffProvider wiring purchase store to derivation"
```

---

## Group 3 — Service wiring, schemas, endpoints

### Task 5: Config — trailing-window setting

**Files:**
- Modify: `src/solar_advisor/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_config.py`)

```python
def test_tariff_window_days_defaults_to_90(monkeypatch):
    monkeypatch.delenv("SA_TARIFF_WINDOW_DAYS", raising=False)
    from solar_advisor.config import load_config

    assert load_config().tariff_window_days == 90


def test_tariff_window_days_from_env(monkeypatch):
    monkeypatch.setenv("SA_TARIFF_WINDOW_DAYS", "120")
    from solar_advisor.config import load_config

    assert load_config().tariff_window_days == 120
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -k tariff_window -v`
Expected: FAIL — `AttributeError: 'AppConfig' object has no attribute 'tariff_window_days'`

- [ ] **Step 3: Add the field** to `AppConfig` (after `daily_consumption_kwh`, in the defaulted block) in `src/solar_advisor/config.py`:

```python
    daily_consumption_kwh: float = 24.0  # fallback when the estimator's confidence is 0
    tariff_window_days: int = 90  # trailing window for the data-derived marginal rate
```

And in `load_config()` (after the `daily_consumption_kwh=...` line):

```python
        daily_consumption_kwh=float(os.environ.get("SA_DAILY_CONSUMPTION_KWH", "24")),
        tariff_window_days=int(os.environ.get("SA_TARIFF_WINDOW_DAYS", "90")),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -k tariff_window -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/solar_advisor/config.py tests/test_config.py
git commit -m "feat: add SA_TARIFF_WINDOW_DAYS config (default 90)"
```

### Task 6: Wire derived tariff into `RecommendationService`

**Files:**
- Modify: `src/solar_advisor/services/recommendation.py`
- Test: `tests/test_recommendation_service.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_recommendation_service.py`; the existing `_config()`/`_live_state()`/`_FakeEstimator`/`_FakeForecast` helpers are reused)

```python
from datetime import date

from solar_advisor.domain.purchase import Purchase
from solar_advisor.tariff.provider import TariffProvider


class _FakeReader:
    def __init__(self, purchases):
        self._purchases = purchases

    def list_since(self, cutoff):
        return [p for p in self._purchases if p.purchased_at >= cutoff]


def test_tariff_derived_from_purchases_when_provider_present():
    # _live_state() stamps telemetry at 2026-06-22; a 2026-06-10 buy is in-window.
    reader = _FakeReader([Purchase(purchased_at=date(2026, 6, 10), rand=1000.0, units_kwh=250.0)])
    provider = TariffProvider(reader=reader, fallback_rate=3.56, window_days=90)
    svc = RecommendationService(
        config=_config(),
        estimator=_FakeEstimator(),
        forecast=_FakeForecast(),
        tariff_provider=provider,
    )
    data = svc.build(_live_state(), objective=0.5)
    assert data.tariff_source == "purchase"
    assert data.tariff_source_date == date(2026, 6, 10)
    assert round(data.tariff_rate, 2) == 4.00  # 1000 / 250


def test_tariff_falls_back_to_config_without_provider():
    svc = RecommendationService(
        config=_config(), estimator=_FakeEstimator(), forecast=_FakeForecast()
    )
    data = svc.build(_live_state(), objective=0.5)
    assert data.tariff_source == "config"
    assert data.tariff_source_date is None
    assert data.tariff_rate == 3.56
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_recommendation_service.py -k tariff -v`
Expected: FAIL — `TypeError: RecommendationService.__init__() got an unexpected keyword argument 'tariff_provider'`

- [ ] **Step 3: Edit `src/solar_advisor/services/recommendation.py`**

Add imports near the top (after the existing `from solar_advisor.engine.tariff import FlatRateTariff`):

```python
from datetime import date
from solar_advisor.tariff.derivation import DerivedRate
from solar_advisor.tariff.provider import TariffProvider
```

(Note: `datetime`/`timedelta` are already imported on the existing `from datetime import datetime, timedelta` line — extend it to `from datetime import date, datetime, timedelta` instead of adding a second line.)

Add two fields to `DashboardData` (after `tariff_rate: float`):

```python
    tariff_rate: float
    tariff_source: str
    tariff_source_date: date | None
```

Change `__init__` to accept the provider:

```python
    def __init__(
        self,
        config: AppConfig,
        estimator: _Estimator,
        forecast: ForecastProvider,
        tariff_provider: TariffProvider | None = None,
    ) -> None:
        self._config = config
        self._estimator = estimator
        self._forecast = forecast
        self._tariff_provider = tariff_provider
```

In `build()`, replace the `tariff = FlatRateTariff(...)` block with:

```python
        if self._tariff_provider is not None:
            derived = self._tariff_provider.current_rate(telemetry.ts.date())
        else:
            derived = DerivedRate(rate=cfg.tariff_rate, source="config", source_date=None)
        tariff = FlatRateTariff(
            energy_rate=derived.rate, monthly_fixed_charge=cfg.tariff_fixed_charge
        )
```

In the returned `DashboardData(...)`, change `tariff_rate=cfg.tariff_rate` to use the derived values:

```python
            tariff_rate=derived.rate,
            tariff_source=derived.source,
            tariff_source_date=derived.source_date,
```

- [ ] **Step 4: Run the full service test file** (verifies new + existing tests still pass)

Run: `python -m pytest tests/test_recommendation_service.py -v`
Expected: PASS (all — the 4 original + 2 new; `data.tariff_rate == 3.56` still holds via config fallback)

- [ ] **Step 5: Commit**

```bash
git add src/solar_advisor/services/recommendation.py tests/test_recommendation_service.py
git commit -m "feat: RecommendationService uses derived tariff with config fallback"
```

### Task 7: API schemas

**Files:**
- Modify: `src/solar_advisor/api/schemas.py`
- Test: `tests/test_api_purchases.py` (created next task; schema is exercised there)

- [ ] **Step 1: Add schemas** to `src/solar_advisor/api/schemas.py`

Add the import at the top (after `from pydantic import BaseModel`):

```python
from datetime import date

from pydantic import BaseModel, Field
```

Add two fields to `DashboardView` (after `tariff_rate: float`):

```python
    tariff_rate: float
    tariff_source: str
    tariff_source_date: str | None
```

Add the purchase schemas at the end of the file:

```python
class PurchaseCreate(BaseModel):
    purchased_at: date
    rand: float = Field(gt=0)
    units_kwh: float = Field(gt=0)
    note: str | None = None

    @field_validator("purchased_at")
    @classmethod
    def _not_in_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("purchased_at cannot be in the future")
        return v


class PurchaseView(BaseModel):
    id: int
    purchased_at: str
    rand: float
    units_kwh: float
    note: str | None
    effective_rate: float


class PurchaseListView(BaseModel):
    purchases: list[PurchaseView]
```

Update the pydantic import to include `field_validator`:

```python
from pydantic import BaseModel, Field, field_validator
```

- [ ] **Step 2: Verify it imports**

Run: `python -c "from solar_advisor.api.schemas import PurchaseCreate, PurchaseView, PurchaseListView, DashboardView; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/solar_advisor/api/schemas.py
git commit -m "feat: add purchase API schemas and dashboard tariff provenance fields"
```

### Task 8: Purchase endpoints + CORS + container wiring

**Files:**
- Modify: `src/solar_advisor/api/app.py`
- Test: `tests/test_api_purchases.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_purchases.py
from fastapi.testclient import TestClient

from solar_advisor.api.app import build_app, get_purchase_store
from solar_advisor.domain.purchase import Purchase
from solar_advisor.ingest.live import LiveState
from solar_advisor.storage.purchase_store import SqlitePurchaseStore


def _client(tmp_path):
    app = build_app(state=LiveState(store=None))
    store = SqlitePurchaseStore(tmp_path / "p.db")
    app.dependency_overrides[get_purchase_store] = lambda: store
    return TestClient(app), store


def test_post_creates_purchase_and_returns_effective_rate(tmp_path):
    client, _ = _client(tmp_path)
    resp = client.post(
        "/api/purchases",
        json={"purchased_at": "2026-06-01", "rand": 1000.0, "units_kwh": 250.0},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] >= 1
    assert body["effective_rate"] == 4.0


def test_post_rejects_nonpositive_and_future(tmp_path):
    client, _ = _client(tmp_path)
    assert (
        client.post(
            "/api/purchases", json={"purchased_at": "2026-06-01", "rand": 0, "units_kwh": 250.0}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/purchases", json={"purchased_at": "2999-01-01", "rand": 100, "units_kwh": 10.0}
        ).status_code
        == 422
    )


def test_get_lists_newest_first(tmp_path):
    client, store = _client(tmp_path)
    from datetime import date

    store.add(Purchase(purchased_at=date(2026, 6, 1), rand=1000.0, units_kwh=250.0))
    store.add(Purchase(purchased_at=date(2026, 6, 15), rand=1000.0, units_kwh=280.0))
    body = client.get("/api/purchases").json()
    assert [p["purchased_at"] for p in body["purchases"]] == ["2026-06-15", "2026-06-01"]


def test_delete_existing_and_missing(tmp_path):
    client, store = _client(tmp_path)
    from datetime import date

    saved = store.add(Purchase(purchased_at=date(2026, 6, 1), rand=1000.0, units_kwh=250.0))
    assert client.delete(f"/api/purchases/{saved.id}").status_code == 204
    assert client.delete(f"/api/purchases/{saved.id}").status_code == 404


def test_dashboard_and_others_remain_get_only(tmp_path):
    client, _ = _client(tmp_path)
    # No POST/DELETE routes exist for these paths -> 405 Method Not Allowed.
    assert client.post("/api/dashboard").status_code == 405
    assert client.delete("/api/history").status_code == 405
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_purchases.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_purchase_store'`

- [ ] **Step 3: Edit `src/solar_advisor/api/app.py`**

Extend the fastapi import to add `Response`:

```python
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
```

Add schema + domain + store imports (extend the existing `from solar_advisor.api.schemas import (...)` block and add new lines):

```python
from solar_advisor.api.schemas import (
    DashboardView,
    ExplanationView,
    HistoryPoint,
    HistoryView,
    PurchaseCreate,
    PurchaseListView,
    PurchaseView,
    RecommendationView,
    SlotView,
)
from solar_advisor.domain.purchase import Purchase
from solar_advisor.storage.purchase_store import PurchaseStore, SqlitePurchaseStore
from solar_advisor.tariff.provider import TariffProvider
```

Add the dependency getter (next to `get_store`):

```python
def get_purchase_store(request: Request) -> PurchaseStore:
    store = getattr(request.app.state, "purchase_store", None)
    if not isinstance(store, PurchaseStore):
        raise HTTPException(status_code=500, detail="purchase store not initialised")
    return store
```

Add a view helper (next to `_to_view`):

```python
def _purchase_view(p: Purchase) -> PurchaseView:
    assert p.id is not None  # always set by the store on read/insert
    return PurchaseView(
        id=p.id,
        purchased_at=p.purchased_at.isoformat(),
        rand=p.rand,
        units_kwh=p.units_kwh,
        note=p.note,
        effective_rate=round(p.effective_rate, 4),
    )
```

In `_to_view`, add the two new `DashboardView` fields (after `tariff_rate=data.tariff_rate,`):

```python
        tariff_rate=data.tariff_rate,
        tariff_source=data.tariff_source,
        tariff_source_date=(
            data.tariff_source_date.isoformat() if data.tariff_source_date else None
        ),
```

Change the CORS middleware `allow_methods` (purchases are written to our own DB, never the inverter; other paths define no write routes so they stay effectively GET-only and return 405 to writes):

```python
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],  # Vite dev server (Plan E)
        allow_methods=["GET", "POST", "DELETE"],  # POST/DELETE used only by /api/purchases
        allow_headers=["*"],
    )
```

Add the three endpoints inside `build_app` (after the `history` endpoint, before `return app`):

```python
    @app.post("/api/purchases", response_model=PurchaseView, status_code=201)
    def create_purchase(
        body: PurchaseCreate,
        store: PurchaseStore = Depends(get_purchase_store),  # noqa: B008
    ) -> PurchaseView:
        saved = store.add(
            Purchase(
                purchased_at=body.purchased_at,
                rand=body.rand,
                units_kwh=body.units_kwh,
                note=body.note,
            )
        )
        return _purchase_view(saved)

    @app.get("/api/purchases", response_model=PurchaseListView)
    def list_purchases(
        store: PurchaseStore = Depends(get_purchase_store),  # noqa: B008
    ) -> PurchaseListView:
        return PurchaseListView(purchases=[_purchase_view(p) for p in store.list_all()])

    @app.delete("/api/purchases/{purchase_id}", status_code=204)
    def delete_purchase(
        purchase_id: int,
        store: PurchaseStore = Depends(get_purchase_store),  # noqa: B008
    ) -> Response:
        if not store.delete(purchase_id):
            raise HTTPException(status_code=404, detail="no such purchase")
        return Response(status_code=204)
```

In `create_production_app()`, wire the store + provider. Replace the `service = RecommendationService(...)` line and add wiring:

```python
    purchase_store = SqlitePurchaseStore(config.db_path)
    tariff_provider = TariffProvider(
        reader=purchase_store,
        fallback_rate=config.tariff_rate,
        window_days=config.tariff_window_days,
    )
    service = RecommendationService(
        config=config,
        estimator=estimator,
        forecast=forecast,
        tariff_provider=tariff_provider,
    )
```

And after `app.state.store = store` add:

```python
    app.state.purchase_store = purchase_store
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_purchases.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/solar_advisor/api/app.py tests/test_api_purchases.py
git commit -m "feat: add /api/purchases POST/GET/DELETE and wire derived tariff"
```

### Task 9: Full gate — tests, lint, types, import contract

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend suite**

Run: `python -m pytest -q`
Expected: PASS (all existing + new tests green)

- [ ] **Step 2: Lint, format, types, import contract**

Run: `ruff check . && ruff format --check . && mypy && lint-imports`
Expected: all clean. The `engine-is-pure` contract still holds — `tariff/` and `storage/purchase_store.py` are outside `solar_advisor.engine`, and nothing in `engine/` imports them.

- [ ] **Step 3: Fix any issues** surfaced by Step 1–2, then re-run until clean.

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "chore: satisfy lint/type/import gates for purchase tracker backend"
```

---

## Self-Review

**Spec coverage:**
- §2 read-only boundary → Task 3 (store docstring), Task 8 (CORS comment + 405 test). ✓
- §3 data model → Task 1. ✓
- §4 derivation (min-over-window, fallback, provenance, fixed charge stays config) → Task 2 (logic), Task 6 (fixed charge from `cfg.tariff_fixed_charge` unchanged). ✓
- §5 backend components (store, Protocol, derivation, provider, service, endpoints, schemas) → Tasks 1–8. ✓
- §7 testing (derivation hard cases incl. April step-up + boundary; store round-trip; endpoints; service integration) → Tasks 2, 3, 6, 8. ✓
- §8 Plan F scope = backend only → this plan; frontend deferred to Plan G. ✓

**Placeholder scan:** none — every step has complete code/commands.

**Type consistency:** `DerivedRate{rate, source, source_date}` consistent across derivation/provider/service; `DashboardData.tariff_source/tariff_source_date` ↔ `DashboardView.tariff_source/tariff_source_date` (date→isoformat str at the view boundary); `PurchaseStore` Protocol methods (`add/list_all/list_since/delete`) match `SqlitePurchaseStore`; `TariffProvider.current_rate(today)` called with `telemetry.ts.date()`. ✓
