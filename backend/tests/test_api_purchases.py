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
