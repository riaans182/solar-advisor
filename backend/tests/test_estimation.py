# tests/test_estimation.py
from datetime import datetime, timedelta

from solar_advisor.estimation.estimator import EstimatedParameters, ParameterEstimator
from solar_advisor.storage.sqlite_store import SqliteTelemetryStore
from tests.conftest import make_telemetry


def _store_with_discharge_cycle(tmp_path):
    """A clean discharge run: SOC 90 -> 40 while battery_energy_out rises 100 -> 107.5
    (=> usable capacity 7.5 / 0.5 = 15 kWh) and load_energy rises 200 -> 224 over 2 days
    (=> 12 kWh/day)."""
    store = SqliteTelemetryStore(tmp_path / "e.db", min_interval=timedelta(0))
    base = datetime(2026, 6, 20, 0, 0, 0)
    rows = [
        (0, 90.0, 100.0, 200.0),
        (24, 65.0, 103.75, 212.0),
        (48, 40.0, 107.5, 224.0),
    ]
    for hours, soc, eout, lenergy in rows:
        store.save(
            make_telemetry(
                base + timedelta(hours=hours),
                battery_soc=soc,
                battery_energy_out=eout,
                load_energy=lenergy,
            )
        )
    return store, base


def test_energy_since_deltas_from_cumulative_counters(tmp_path):
    store = SqliteTelemetryStore(tmp_path / "t.db", min_interval=timedelta(0))
    base = datetime(2026, 6, 20, 0, 0, 0)
    store.save(make_telemetry(base, pv_energy=100.0, load_energy=200.0))
    store.save(make_telemetry(base + timedelta(hours=6), pv_energy=106.2, load_energy=209.1))
    est = ParameterEstimator(store, nominal_kwh=15.0)
    pv, load = est.energy_since(base, base + timedelta(hours=6))
    assert round(pv, 1) == 6.2
    assert round(load, 1) == 9.1


def test_energy_since_empty_window_is_zero(tmp_path):
    store = SqliteTelemetryStore(tmp_path / "t2.db", min_interval=timedelta(0))
    est = ParameterEstimator(store, nominal_kwh=15.0)
    base = datetime(2026, 6, 20, 0, 0, 0)
    assert est.energy_since(base, base + timedelta(hours=1)) == (0.0, 0.0)


def test_estimates_usable_capacity_from_discharge_run(tmp_path):
    store, base = _store_with_discharge_cycle(tmp_path)
    est = ParameterEstimator(store, nominal_kwh=15.0)
    result = est.estimate(base, base + timedelta(hours=48))
    assert isinstance(result, EstimatedParameters)
    assert result.usable_kwh == 15.0  # 7.5 kWh out across a 50% SOC drop
    assert 0.0 < result.usable_kwh_confidence <= 1.0


def test_estimates_daily_consumption_from_load_energy(tmp_path):
    store, base = _store_with_discharge_cycle(tmp_path)
    est = ParameterEstimator(store, nominal_kwh=15.0)
    result = est.estimate(base, base + timedelta(hours=48))
    assert result.daily_consumption_kwh == 12.0  # 24 kWh over 2 days


def test_capacity_uses_single_discharge_run_not_global_soc_span(tmp_path):
    """Window with two discharge cycles separated by a recharge. The cumulative
    battery_energy_out delta across the whole window sums BOTH discharges (14.5 kWh),
    but any single SOC span is only ~60 points. The global-max/min approach divides
    the summed energy by one span and roughly doubles the estimate (~27.7 kWh).
    A per-run estimate stays in the real ~12-14 kWh range."""
    store = SqliteTelemetryStore(tmp_path / "m.db", min_interval=timedelta(0))
    base = datetime(2026, 6, 20, 0, 0, 0)
    rows = [
        (0, 90.0, 100.0),  # discharge run A: span 60, 7.0 kWh out
        (1, 30.0, 107.0),
        (2, 85.0, 107.0),  # recharge (SOC up; energy_out flat)
        (3, 80.0, 109.0),  # discharge run B: span 55, 7.5 kWh out
        (4, 25.0, 116.5),
    ]
    for hours, soc, eout in rows:
        store.save(
            make_telemetry(
                base + timedelta(hours=hours),
                battery_soc=soc,
                battery_energy_out=eout,
            )
        )
    est = ParameterEstimator(store, nominal_kwh=15.0)
    result = est.estimate(base, base + timedelta(hours=4))
    # Broken global-max/min yields ~27.7 kWh; a single-run estimate is ~11.7-13.6 kWh.
    assert result.usable_kwh < 20.0


def test_falls_back_to_nominal_without_discharge_data(tmp_path):
    store = SqliteTelemetryStore(tmp_path / "f.db", min_interval=timedelta(0))
    base = datetime(2026, 6, 20, 0, 0, 0)
    store.save(make_telemetry(base, battery_soc=50.0, battery_energy_out=10.0, load_energy=5.0))
    est = ParameterEstimator(store, nominal_kwh=15.0)
    result = est.estimate(base, base + timedelta(hours=1))
    assert result.usable_kwh == 15.0  # nominal fallback
    assert result.usable_kwh_confidence == 0.0  # no observed discharge span
