# tests/test_api_explain.py
from fastapi.testclient import TestClient

from solar_advisor.api.app import build_app, get_explainer, get_service
from solar_advisor.explain.client import Explainer
from solar_advisor.services.recommendation import RecommendationService
from tests.test_api import _config, _FakeEstimator, _FakeForecast, _ready_state


def _client(state, complete, *, enabled=True):
    app = build_app(state=state)
    svc = RecommendationService(
        config=_config(), estimator=_FakeEstimator(), forecast=_FakeForecast()
    )
    explainer = Explainer(complete=complete, enabled=enabled, min_interval_s=0.0)
    app.dependency_overrides[get_service] = lambda: svc
    app.dependency_overrides[get_explainer] = lambda: explainer
    return TestClient(app)


def test_explain_returns_generated_text_with_disclaimer():
    def complete(system, user):
        # Numbers (100%, 13.2 kWh) trace to the engine facts the service built.
        return "Your schedule grid-charges to 100% overnight, importing 13.2 kWh."

    resp = _client(_ready_state(), complete).get("/api/explain?objective=1.0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["generated"] is True
    assert body["guard_ok"] is True
    assert "100%" in body["explanation"]
    assert "read-only" in body["disclaimer"].lower()


def test_explain_withholds_fabricated_numbers():
    def complete(system, user):
        return "You'll save R777 a month."  # not in facts

    body = _client(_ready_state(), complete).get("/api/explain").json()
    assert body["guard_ok"] is False
    assert 777.0 in body["unverified_numbers"]
    assert "777" not in body["explanation"]


def test_explain_503_when_state_not_ready():
    from solar_advisor.ingest.live import LiveState

    resp = _client(LiveState(store=None), lambda s, u: "x").get("/api/explain")
    assert resp.status_code == 503
