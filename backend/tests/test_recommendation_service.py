# tests/test_recommendation_service.py
from datetime import UTC, date, datetime, time

from solar_advisor.config import AppConfig
from solar_advisor.domain.purchase import Purchase
from solar_advisor.domain.schedule import build_schedule
from solar_advisor.engine.inputs import SolarForecast
from solar_advisor.estimation.estimator import EstimatedParameters
from solar_advisor.ingest.live import LiveState
from solar_advisor.services.recommendation import DashboardData, RecommendationService
from solar_advisor.tariff.provider import TariffProvider
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


def test_dashboard_surfaces_tariff_and_forecast():
    svc = RecommendationService(
        config=_config(),
        estimator=_FakeEstimator(),
        forecast=_FakeForecast(),
    )
    data = svc.build(_live_state(), objective=0.5)
    assert data.tariff_rate == 3.56
    assert data.expected_pv_kwh_today == 8.0
    assert data.expected_pv_kwh_tomorrow == 8.0


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


def test_dashboard_exposes_battery_and_conversion_power():
    svc = RecommendationService(
        config=_config(), estimator=_FakeEstimator(), forecast=_FakeForecast()
    )
    data = svc.build(_live_state(), objective=0.5)
    assert data.telemetry.battery_power == 85
    # conversion = pv + grid - battery_power - load = 106 + 1140 - 85 - 1086
    assert data.conversion_power == 75


def test_month_projection_energy_only():
    reader = _FakeReader(
        [
            Purchase(purchased_at=date(2026, 6, 3), rand=1000.0, units_kwh=280.0),
            Purchase(purchased_at=date(2026, 6, 18), rand=500.0, units_kwh=140.0),
            Purchase(purchased_at=date(2026, 5, 20), rand=900.0, units_kwh=260.0),
        ]
    )
    svc = RecommendationService(
        config=_config(),
        estimator=_FakeEstimator(),
        forecast=_FakeForecast(),
        purchases=reader,
    )
    data = svc.build(_live_state(), objective=0.5)
    assert data.month_spend == 1500.0  # May purchase excluded
    expected = (100.0 / 22.0) * 30.0 * 3.56  # energy only, no fixed charge
    assert round(data.month_projected_cost, 2) == round(expected, 2)
    assert round(data.month_balance, 2) == round(1500.0 - expected, 2)


def test_month_projection_zero_without_reader():
    svc = RecommendationService(
        config=_config(), estimator=_FakeEstimator(), forecast=_FakeForecast()
    )
    data = svc.build(_live_state(), objective=0.5)
    assert data.month_spend == 0.0
