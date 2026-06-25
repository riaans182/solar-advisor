# tests/test_api_history.py
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from solar_advisor.api.app import build_app, get_store
from solar_advisor.storage.sqlite_store import SqliteTelemetryStore
from tests.conftest import make_telemetry
from tests.test_api import _ready_state


def _client_with_store(tmp_path):
    store = SqliteTelemetryStore(tmp_path / "h.db", min_interval=timedelta(0))
    # Anchor sample timestamps near "now" so they fall inside the endpoint's
    # rolling now-Nh..now window regardless of the calendar date the test runs on.
    base = datetime.now(UTC) - timedelta(hours=3)
    for i in range(3):
        store.save(
            make_telemetry(base + timedelta(hours=i), battery_soc=60.0 + i, pv_power=100.0 * i)
        )
    app = build_app(state=_ready_state())
    app.dependency_overrides[get_store] = lambda: store
    return TestClient(app), base


def test_history_returns_points(tmp_path):
    client, _ = _client_with_store(tmp_path)
    resp = client.get("/api/history?hours=24")
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 3
    assert points[0]["battery_soc"] == 60.0
    assert {"ts", "battery_soc", "pv_power", "grid_power", "load_power"} <= set(points[0])


def test_history_hours_bounds(tmp_path):
    client, _ = _client_with_store(tmp_path)
    assert client.get("/api/history?hours=0").status_code == 422  # ge=1
    assert client.get("/api/history?hours=999").status_code == 422  # le=168
