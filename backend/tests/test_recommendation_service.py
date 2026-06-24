# tests/test_recommendation_service.py
from datetime import UTC, datetime, time

from solar_advisor.config import AppConfig
from solar_advisor.domain.schedule import build_schedule
from solar_advisor.engine.inputs import SolarForecast
from solar_advisor.estimation.estimator import EstimatedParameters
from solar_advisor.ingest.live import LiveState
from solar_advisor.services.recommendation import DashboardData, RecommendationService
from tests.conftest import make_telemetry


class _FakeEstimator:
    def estimate(self, start, end):
        return EstimatedParameters(
            usable_kwh=15.0,
            usable_kwh_confidence=0.6,
            daily_consumption_kwh=20.0,
            daily_consumption_confidence=0.5,
        )


class _ZeroConfidenceEstimator:
    """Mirrors the estimator's thin-history contract: daily consumption is 0.0
    and confidence is 0, so the service must NOT use the 0.0 value."""

    def estimate(self, start, end):
        return EstimatedParameters(
            usable_kwh=15.0,
            usable_kwh_confidence=0.6,
            daily_consumption_kwh=0.0,
            daily_consumption_confidence=0.0,
        )


class _FakeForecast:
    def fetch(self):
        return SolarForecast(expected_pv_kwh_today=8.0, expected_pv_kwh_tomorrow=8.0)


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


def _live_state():
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


def test_build_dashboard_runs_engine():
    svc = RecommendationService(
        config=_config(),
        estimator=_FakeEstimator(),
        forecast=_FakeForecast(),
    )
    data = svc.build(_live_state(), objective=1.0)
    assert isinstance(data, DashboardData)
    assert len(data.slot_assessments) == 6
    assert data.recommendation.reserve_target_soc == 100.0
    assert data.recommendation.enable_overnight_grid_charge is True
    assert data.usable_kwh_confidence == 0.6


def test_objective_defaults_to_config_when_none():
    svc = RecommendationService(
        config=_config(),
        estimator=_FakeEstimator(),
        forecast=_FakeForecast(),
    )
    data = svc.build(_live_state(), objective=None)
    assert data.objective == 0.5  # config default


def test_daily_load_falls_back_to_config_when_confidence_zero():
    """When the estimator reports daily_consumption_confidence == 0 (thin history),
    the service must use the config default rather than the physically-wrong 0.0."""
    svc = RecommendationService(
        config=_config(),  # daily_consumption_kwh defaults to 24.0
        estimator=_ZeroConfidenceEstimator(),
        forecast=_FakeForecast(),
    )
    data = svc.build(_live_state(), objective=0.0)
    assert data.daily_consumption_kwh == 24.0  # config fallback, NOT 0.0
