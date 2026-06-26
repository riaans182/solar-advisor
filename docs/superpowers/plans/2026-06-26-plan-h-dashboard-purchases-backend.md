# Plan H — Dashboard & Purchases Polish (Backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose battery power + a derived inverter conversion/idle figure on the dashboard, serve bucketed history up to 30 days, and allow editing a logged purchase.

**Architecture:** Add `battery_power` + `conversion_power` (`pv + grid − battery − load`) to `DashboardView` (computed in `RecommendationService`). Add a SQL-aggregated `query_bucketed` to the telemetry store so any range returns ~400 points; raise the history cap to 720h and add `battery_power` to history. Add `PUT /api/purchases/{id}` backed by `PurchaseStore.update`.

**Tech Stack:** Python 3.12, FastAPI + Pydantic v2, stdlib sqlite3, pytest, ruff, mypy --strict, import-linter.

**Reference (read first):** spec `docs/superpowers/specs/2026-06-26-dashboard-purchases-polish-design.md`. Mirror existing patterns: `backend/src/solar_advisor/api/app.py` (`_to_view`, `history`, purchase endpoints), `backend/src/solar_advisor/services/recommendation.py` (`DashboardData`, `build`), `backend/src/solar_advisor/storage/sqlite_store.py`, `backend/src/solar_advisor/storage/purchase_store.py`, `backend/src/solar_advisor/storage/store.py` (Protocol). Tests: `backend/tests/test_recommendation_service.py`, `test_api.py`, `test_api_history.py`, `test_sqlite_store.py`, `test_api_purchases.py`. **All commands run from `backend/`; the worktree has no venv yet — first run `make install`, then use `.venv/bin/pytest`, `.venv/bin/ruff`, `.venv/bin/mypy`, `.venv/bin/lint-imports --config .importlinter`.**

---

## File Structure

| File | Change |
|------|--------|
| `src/solar_advisor/api/schemas.py` | `DashboardView` += `battery_power`, `conversion_power`; `HistoryPoint` += `battery_power`. |
| `src/solar_advisor/services/recommendation.py` | `DashboardData` += `conversion_power`; `build()` computes it. |
| `src/solar_advisor/api/app.py` | `_to_view` maps the two new fields; `history` uses bucketed query + 720h cap + `battery_power`; new `PUT /api/purchases/{id}`; CORS += `PUT`. |
| `src/solar_advisor/storage/store.py` | `TelemetryStore` Protocol += `query_bucketed`. |
| `src/solar_advisor/storage/sqlite_store.py` | implement `query_bucketed`. |
| `src/solar_advisor/storage/purchase_store.py` | `PurchaseStore` Protocol + `SqlitePurchaseStore` += `update`. |
| tests | `test_recommendation_service.py`, `test_api.py`, `test_sqlite_store.py`, `test_api_history.py`, `test_purchase_store.py`, `test_api_purchases.py`. |

---

## Group 1 — Battery power + conversion power on the dashboard

### Task 1: Service computes `conversion_power`; schema carries both fields

**Files:** Modify `services/recommendation.py`, `api/schemas.py`; Test `tests/test_recommendation_service.py`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_recommendation_service.py`; reuses the existing `_config()/_live_state()/_FakeEstimator/_FakeForecast`). The `make_telemetry` defaults are `pv_power=106, grid_power=1140, load_power=1086, battery_power=85` ⇒ `conversion = 106 + 1140 − 85 − 1086 = 75`:

```python
def test_dashboard_exposes_battery_and_conversion_power():
    svc = RecommendationService(
        config=_config(), estimator=_FakeEstimator(), forecast=_FakeForecast()
    )
    data = svc.build(_live_state(), objective=0.5)
    assert data.telemetry.battery_power == 85
    # conversion = pv + grid - battery_power - load = 106 + 1140 - 85 - 1086
    assert data.conversion_power == 75
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_recommendation_service.py -k conversion -v`
Expected: FAIL — `DashboardData` has no `conversion_power`.

- [ ] **Step 3: Implement.** In `services/recommendation.py`, add the field to `DashboardData` (after `tariff_source_date: date | None`):

```python
    tariff_source_date: date | None
    conversion_power: float
```

In `build()`, compute it just before constructing `DashboardData` (telemetry is already bound as `telemetry`):

```python
        conversion_power = (
            telemetry.pv_power + telemetry.grid_power - telemetry.battery_power - telemetry.load_power
        )
```

And pass it in the returned `DashboardData(...)` (add after `tariff_source_date=derived.source_date,`):

```python
            tariff_source_date=derived.source_date,
            conversion_power=conversion_power,
```

In `api/schemas.py`, add to `DashboardView` (after `load_power: float`):

```python
    load_power: float
    battery_power: float
    conversion_power: float
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_recommendation_service.py -k conversion -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/solar_advisor/services/recommendation.py src/solar_advisor/api/schemas.py tests/test_recommendation_service.py
git commit -m "feat: compute conversion_power and carry battery/conversion on dashboard data"
```

### Task 2: `_to_view` surfaces battery_power + conversion_power

**Files:** Modify `api/app.py`; Test `tests/test_api.py`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_api.py`; `_ready_state()` uses `make_telemetry` defaults, so `battery_power=85`, `conversion=75`):

```python
def test_dashboard_view_includes_battery_and_conversion_power():
    body = _client(_ready_state()).get("/api/dashboard?objective=0.5").json()
    assert body["battery_power"] == 85
    assert body["conversion_power"] == 75
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_api.py -k battery_and_conversion -v`
Expected: FAIL — keys missing / validation error.

- [ ] **Step 3: Implement.** In `api/app.py` `_to_view`, add the two fields (after `load_power=data.telemetry.load_power,`):

```python
        load_power=data.telemetry.load_power,
        battery_power=round(data.telemetry.battery_power),
        conversion_power=round(data.conversion_power),
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_api.py -k battery_and_conversion -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/solar_advisor/api/app.py tests/test_api.py
git commit -m "feat: surface battery_power and conversion_power on /api/dashboard"
```

---

## Group 2 — History bucketing + 30-day range + battery power

### Task 3: `query_bucketed` on the telemetry store

**Files:** Modify `storage/store.py`, `storage/sqlite_store.py`; Test `tests/test_sqlite_store.py`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_sqlite_store.py`; the `store` fixture and `make_telemetry` are already imported there):

```python
def test_query_bucketed_averages_within_buckets(tmp_path):
    store = SqliteTelemetryStore(tmp_path / "t.db", min_interval=timedelta(0))
    base = datetime(2026, 6, 1, 0, 0, 0)
    # Two samples in bucket 0 (avg pv 100), one in a later bucket (pv 300).
    store.save(make_telemetry(base, pv_power=50))
    store.save(make_telemetry(base + timedelta(seconds=30), pv_power=150))
    store.save(make_telemetry(base + timedelta(seconds=3600), pv_power=300))
    out = store.query_bucketed(base - timedelta(minutes=1), base + timedelta(hours=2), 3600)
    assert len(out) == 2
    assert round(out[0].pv_power) == 100  # (50 + 150) / 2
    assert round(out[1].pv_power) == 300
    assert out[0].ts <= out[1].ts  # ordered


def test_query_bucketed_empty_range_returns_empty(store):
    out = store.query_bucketed(
        datetime(2026, 1, 1), datetime(2026, 1, 2), 3600
    )
    assert out == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_sqlite_store.py -k bucketed -v`
Expected: FAIL — `SqliteTelemetryStore` has no `query_bucketed`.

- [ ] **Step 3: Implement.** In `storage/store.py`, add to the `TelemetryStore` Protocol (after `query_range`):

```python
    def query_range(self, start: datetime, end: datetime) -> list[Telemetry]: ...
    # query_bucketed aggregates the range into time buckets (SQL AVG per metric),
    # returning one Telemetry per bucket ordered by ascending ts.
    def query_bucketed(
        self, start: datetime, end: datetime, bucket_seconds: int
    ) -> list[Telemetry]: ...
```

In `storage/sqlite_store.py`, add the method (after `query_range`):

```python
    def query_bucketed(
        self, start: datetime, end: datetime, bucket_seconds: int
    ) -> list[Telemetry]:
        # Aggregate in SQL so a 30-day range never loads ~260k rows into Python.
        # Bucket key = unix-epoch(ts) // bucket_seconds. ts is stored as an ISO8601
        # string; replacing 'T' with a space keeps strftime('%s', ...) robust across
        # SQLite builds, and the stored '+00:00' offset yields a correct UTC epoch.
        cur = self._conn.execute(
            "SELECT MIN(ts) AS ts, "
            "AVG(battery_soc), AVG(battery_power), AVG(pv_power), "
            "AVG(grid_power), AVG(load_power) "
            "FROM telemetry WHERE ts >= ? AND ts <= ? "
            "GROUP BY CAST(strftime('%s', replace(ts, 'T', ' ')) AS INTEGER) / ? "
            "ORDER BY ts",
            (start.isoformat(), end.isoformat(), bucket_seconds),
        )
        out: list[Telemetry] = []
        for ts, soc, bpow, pv, grid, load in cur.fetchall():
            out.append(
                Telemetry(
                    ts=datetime.fromisoformat(ts),
                    battery_soc=soc,
                    battery_power=bpow,
                    battery_voltage=0.0,
                    battery_current=0.0,
                    pv_power=pv,
                    grid_power=grid,
                    load_power=load,
                    load_power_essential=0.0,
                    grid_energy_in=0.0,
                    grid_energy_out=0.0,
                    pv_energy=0.0,
                    load_energy=0.0,
                    battery_energy_in=0.0,
                    battery_energy_out=0.0,
                    month_to_date_grid_import_kwh=0.0,
                )
            )
        return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_sqlite_store.py -k bucketed -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/solar_advisor/storage/store.py src/solar_advisor/storage/sqlite_store.py tests/test_sqlite_store.py
git commit -m "feat: add SQL-bucketed telemetry query for history aggregation"
```

### Task 4: History endpoint — 30-day cap, bucketing, battery_power

**Files:** Modify `api/schemas.py`, `api/app.py`; Test `tests/test_api_history.py`.

- [ ] **Step 1: Write the failing test.** First read `tests/test_api_history.py` to match how it builds a store/app. Then append a test asserting the 720h cap and that `battery_power` is present. Use the same app/store construction the existing tests in that file use (a real `SqliteTelemetryStore` wired into `app.state.store` with `get_store` overridden, or the file's existing helper). Concretely:

```python
def test_history_accepts_30_day_range_and_returns_battery_power(tmp_path):
    from datetime import UTC, datetime, timedelta
    from fastapi.testclient import TestClient
    from solar_advisor.api.app import build_app, get_store
    from solar_advisor.ingest.live import LiveState
    from solar_advisor.storage.sqlite_store import SqliteTelemetryStore
    from tests.conftest import make_telemetry

    store = SqliteTelemetryStore(tmp_path / "h.db", min_interval=timedelta(0))
    now = datetime.now(UTC)
    store.save(make_telemetry(now - timedelta(days=10), pv_power=120, battery_power=40))
    app = build_app(state=LiveState(store=None))
    app.dependency_overrides[get_store] = lambda: store
    client = TestClient(app)

    assert client.get("/api/history?hours=720").status_code == 200
    assert client.get("/api/history?hours=721").status_code == 422  # over cap
    pts = client.get("/api/history?hours=720").json()["points"]
    assert len(pts) >= 1
    assert "battery_power" in pts[0]
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_api_history.py -k 30_day -v`
Expected: FAIL — `hours=721` currently allowed (cap 168) and/or `battery_power` missing.

- [ ] **Step 3: Implement.** In `api/schemas.py`, add to `HistoryPoint` (after `load_power: float`):

```python
    load_power: float
    battery_power: float
```

In `api/app.py`, replace the whole `history` endpoint body with the bucketed version (note the new `math` import — add `import math` at the top with the other stdlib imports):

```python
    @app.get("/api/history", response_model=HistoryView)
    def history(
        hours: int = Query(default=24, ge=1, le=720),
        store: TelemetryStore = Depends(get_store),  # noqa: B008
    ) -> HistoryView:
        end = datetime.now(UTC)
        start = end - timedelta(hours=hours)
        # Target ~400 points regardless of range; never bucket finer than the 10s sample.
        bucket_seconds = max(10, math.ceil(hours * 3600 / 400))
        rows = store.query_bucketed(start, end, bucket_seconds)
        return HistoryView(
            points=[
                HistoryPoint(
                    ts=r.ts.isoformat(),
                    battery_soc=r.battery_soc,
                    pv_power=r.pv_power,
                    grid_power=r.grid_power,
                    load_power=r.load_power,
                    battery_power=r.battery_power,
                )
                for r in rows
            ]
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_api_history.py -v`
Expected: PASS (existing history tests + the new one). If an existing test asserted `hours=169` is rejected, update it to the new cap.

- [ ] **Step 5: Commit**

```bash
git add src/solar_advisor/api/schemas.py src/solar_advisor/api/app.py tests/test_api_history.py
git commit -m "feat: history up to 30 days with server-side bucketing and battery_power"
```

---

## Group 3 — Edit a purchase (PUT)

### Task 5: `PurchaseStore.update`

**Files:** Modify `storage/purchase_store.py`; Test `tests/test_purchase_store.py`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_purchase_store.py`; `store` fixture + `_p` helper + `date` already imported there):

```python
def test_update_existing_returns_updated_row(store):
    saved = store.add(_p(date(2026, 6, 1), rand=1000.0, units=250.0))
    updated = store.update(
        saved.id, Purchase(purchased_at=date(2026, 6, 2), rand=900.0, units_kwh=260.0, note="fixed")
    )
    assert updated is not None
    assert updated.id == saved.id
    assert updated.rand == 900.0
    assert updated.units_kwh == 260.0
    assert updated.purchased_at == date(2026, 6, 2)
    assert updated.note == "fixed"
    # persisted
    assert store.list_all()[0].rand == 900.0


def test_update_missing_returns_none(store):
    assert store.update(999, _p(date(2026, 6, 1))) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_purchase_store.py -k update -v`
Expected: FAIL — no `update`.

- [ ] **Step 3: Implement.** In `storage/purchase_store.py`, add to the `PurchaseStore` Protocol (after `delete`):

```python
    def delete(self, purchase_id: int) -> bool: ...
    def update(self, purchase_id: int, purchase: Purchase) -> Purchase | None: ...
```

And on `SqlitePurchaseStore` (after `delete`):

```python
    def update(self, purchase_id: int, purchase: Purchase) -> Purchase | None:
        cur = self._conn.execute(
            "UPDATE purchases SET purchased_at = ?, rand = ?, units_kwh = ?, note = ? "
            "WHERE id = ?",
            (
                purchase.purchased_at.isoformat(),
                purchase.rand,
                purchase.units_kwh,
                purchase.note,
                purchase_id,
            ),
        )
        self._conn.commit()
        if cur.rowcount == 0:
            return None
        return Purchase(
            id=purchase_id,
            purchased_at=purchase.purchased_at,
            rand=purchase.rand,
            units_kwh=purchase.units_kwh,
            note=purchase.note,
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_purchase_store.py -k update -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/solar_advisor/storage/purchase_store.py tests/test_purchase_store.py
git commit -m "feat: add SqlitePurchaseStore.update"
```

### Task 6: `PUT /api/purchases/{id}` + CORS PUT

**Files:** Modify `api/app.py`; Test `tests/test_api_purchases.py`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_api_purchases.py`; reuses its `_client(tmp_path)` helper + `Purchase`/`date` imports):

```python
def test_put_updates_existing_purchase(tmp_path):
    client, store = _client(tmp_path)
    from datetime import date

    saved = store.add(Purchase(purchased_at=date(2026, 6, 1), rand=1000.0, units_kwh=250.0))
    resp = client.put(
        f"/api/purchases/{saved.id}",
        json={"purchased_at": "2026-06-02", "rand": 900.0, "units_kwh": 300.0},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == saved.id
    assert body["rand"] == 900.0
    assert body["effective_rate"] == 3.0  # 900 / 300


def test_put_missing_is_404(tmp_path):
    client, _ = _client(tmp_path)
    resp = client.put(
        "/api/purchases/999",
        json={"purchased_at": "2026-06-02", "rand": 900.0, "units_kwh": 300.0},
    )
    assert resp.status_code == 404


def test_put_rejects_invalid_body(tmp_path):
    client, store = _client(tmp_path)
    from datetime import date

    saved = store.add(Purchase(purchased_at=date(2026, 6, 1), rand=1000.0, units_kwh=250.0))
    resp = client.put(
        f"/api/purchases/{saved.id}",
        json={"purchased_at": "2026-06-02", "rand": 0, "units_kwh": 300.0},
    )
    assert resp.status_code == 422
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_api_purchases.py -k put -v`
Expected: FAIL — no PUT route (405/404 mismatch).

- [ ] **Step 3: Implement.** In `api/app.py`:

Add `PUT` to the CORS `allow_methods` list:

```python
        allow_methods=["GET", "POST", "PUT", "DELETE"],  # POST/PUT/DELETE: /api/purchases only
```

Add the endpoint after `create_purchase` (and before `list_purchases` or near the other purchase routes):

```python
    @app.put("/api/purchases/{purchase_id}", response_model=PurchaseView)
    def update_purchase(
        purchase_id: int,
        body: PurchaseCreate,
        store: PurchaseStore = Depends(get_purchase_store),  # noqa: B008
    ) -> PurchaseView:
        updated = store.update(
            purchase_id,
            Purchase(
                purchased_at=body.purchased_at,
                rand=body.rand,
                units_kwh=body.units_kwh,
                note=body.note,
            ),
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="no such purchase")
        return _purchase_view(updated)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_api_purchases.py -k put -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/solar_advisor/api/app.py tests/test_api_purchases.py
git commit -m "feat: add PUT /api/purchases/{id} for editing a purchase"
```

---

## Group 4 — Full gate

### Task 7: Gate — tests, lint, types, import contract

- [ ] **Step 1:** `.venv/bin/pytest -q` — all green (existing + new).
- [ ] **Step 2:** `.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy && .venv/bin/lint-imports --config .importlinter` — all clean. The `engine-is-pure` contract must still hold (no `engine/` imports of storage/api).
- [ ] **Step 3:** Fix anything that fails; re-run until clean.
- [ ] **Step 4:** Commit any fixes: `git add -A && git commit -m "chore: satisfy gates for dashboard/purchases backend"`.

---

## Self-Review

**Spec coverage:** H1 → Tasks 1–2 (battery_power + conversion_power on DashboardView); H2 → Tasks 3–4 (query_bucketed, 720h cap, battery_power on HistoryPoint); H3 → Tasks 5–6 (store.update + PUT + CORS PUT). ✓

**Placeholder scan:** none — every step has complete code/commands.

**Type consistency:** `conversion_power` flows telemetry→`DashboardData.conversion_power`→`DashboardView.conversion_power`; `battery_power` added to both `DashboardView` and `HistoryPoint`; `query_bucketed(start, end, bucket_seconds)` signature matches Protocol, store, and endpoint call; `PurchaseStore.update(id, purchase) -> Purchase | None` matches store + PUT handler (404 on `None`). The history endpoint uses `math.ceil` (import added). ✓
