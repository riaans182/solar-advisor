# tests/test_api.py
from datetime import UTC, datetime, time

from fastapi.testclient import TestClient

from solar_advisor.api.app import build_app, get_service
from solar_advisor.config import AppConfig
from solar_advisor.domain.schedule import build_schedule
from solar_advisor.engine.inputs import SolarForecast
from solar_advisor.estimation.estimator import EstimatedParameters
from solar_advisor.ingest.live import LiveState
from solar_advisor.services.recommendation import RecommendationService
from tests.conftest import make_telemetry


class _FakeEstimator:
    def estimate(self, start, end):
        return EstimatedParameters(15.0, 0.6, 20.0, 0.5)

    def energy_since(self, start, end):
        return (6.2, 9.1)


class _FakeForecast:
    def fetch(self):
        return SolarForecast(8.0, 8.0)


def _config():
    return AppConfig(
        tariff_rate=3.56,
        tariff_fixed_charge=600.0,
        battery_nominal_kwh=15.0,
        battery_soc_floor_pct=20.0,
        max_charge_power_w=7950.0,
        max_discharge_power_w=7950.0,
        essential_power_w=1136.0,
        daylight_dawn=time(7, 0),
        daylight_dusk=time(17, 30),
        objective_default=0.5,
        mqtt_host="x",
        mqtt_port=1883,
        mqtt_user=None,
        mqtt_pass=None,
        db_path=":memory:",
        forecast_today_kwh=8.0,
        forecast_tomorrow_kwh=8.0,
    )


def _ready_state():
    state = LiveState(store=None)
    state.telemetry = make_telemetry(
        datetime(2026, 6, 22, 8, 0, tzinfo=UTC),
        battery_soc=30.0,
        month_to_date_grid_import_kwh=100.0,
    )
    state.schedule = build_schedule(
        {
            "time_point": {1: "00:00", 2: "05:00", 3: "08:00", 4: "16:30", 5: "18:00", 6: "21:30"},
            "capacity_point": {1: 65, 2: 65, 3: 90, 4: 95, 5: 75, 6: 65},
            "grid_charge_point": {1: True, 2: True, 3: True, 4: False, 5: True, 6: True},
            "gen_charge_point": {i: False for i in range(1, 7)},
        }
    )
    return state


def _client(state):
    app = build_app(state=state)
    svc = RecommendationService(
        config=_config(), estimator=_FakeEstimator(), forecast=_FakeForecast()
    )
    app.dependency_overrides[get_service] = lambda: svc
    return TestClient(app)


def test_health_ok():
    assert _client(_ready_state()).get("/api/health").status_code == 200


def test_dashboard_returns_engine_output_with_disclaimer():
    resp = _client(_ready_state()).get("/api/dashboard?objective=1.0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["objective"] == 1.0
    assert len(body["slots"]) == 6
    assert body["recommendation"]["reserve_target_soc"] == 100.0
    assert "read-only" in body["disclaimer"].lower()


def test_dashboard_503_when_state_not_ready():
    resp = _client(LiveState(store=None)).get("/api/dashboard")
    assert resp.status_code == 503


def test_two_apps_keep_independent_state():
    """Two apps built in the same process must not clobber each other's state.
    With the old module-global _STATE, building app B overwrote app A's state
    and A's dashboard would 503. Per-app state via app.state fixes this."""
    svc = RecommendationService(
        config=_config(), estimator=_FakeEstimator(), forecast=_FakeForecast()
    )

    app_a = build_app(state=_ready_state())
    app_a.dependency_overrides[get_service] = lambda: svc

    app_b = build_app(state=LiveState(store=None))
    app_b.dependency_overrides[get_service] = lambda: svc

    client_a = TestClient(app_a)
    client_b = TestClient(app_b)

    assert client_a.get("/api/dashboard").status_code == 200
    assert client_b.get("/api/dashboard").status_code == 503


def test_dashboard_view_includes_battery_and_conversion_power():
    body = _client(_ready_state()).get("/api/dashboard?objective=0.5").json()
    assert body["battery_power"] == 85
    assert body["conversion_power"] == 75


def test_dashboard_view_includes_schedule_diff_and_month_remaining():
    body = _client(_ready_state()).get("/api/dashboard?objective=0.5").json()
    assert "recommended_slots" in body
    assert len(body["recommended_slots"]) == len(body["slots"])
    assert "current_daily_cost" in body
    assert "recommended_daily_cost" in body
    assert "daily_saving" in body
    assert "month_remaining_cost" in body
    assert "month_projected_cost" not in body
    assert "month_balance" not in body
