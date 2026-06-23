# tests/test_sqlite_store.py
from datetime import datetime, timedelta

import pytest

from solar_advisor.domain.telemetry import Telemetry
from solar_advisor.storage.sqlite_store import SqliteTelemetryStore


def _snap(ts: datetime, soc: float = 64.0) -> Telemetry:
    return Telemetry(
        ts=ts,
        battery_soc=soc,
        battery_power=85,
        battery_voltage=50,
        battery_current=1.7,
        pv_power=106,
        grid_power=1140,
        load_power=1086,
        load_power_essential=1136,
        grid_energy_in=1000,
        grid_energy_out=0,
        pv_energy=0,
        load_energy=0,
        battery_energy_in=0,
        battery_energy_out=0,
        month_to_date_grid_import_kwh=12.5,
    )


@pytest.fixture
def store(tmp_path):
    return SqliteTelemetryStore(tmp_path / "t.db", min_interval=timedelta(seconds=10))


def test_save_then_query_roundtrip(store):
    t = datetime(2026, 6, 22, 8, 0, 0)
    assert store.save(_snap(t, soc=64)) is True
    rows = store.query_range(t - timedelta(minutes=1), t + timedelta(minutes=1))
    assert len(rows) == 1
    assert rows[0].battery_soc == 64
    assert rows[0].month_to_date_grid_import_kwh == 12.5


def test_downsampling_skips_writes_inside_min_interval(store):
    t = datetime(2026, 6, 22, 8, 0, 0)
    assert store.save(_snap(t)) is True
    assert store.save(_snap(t + timedelta(seconds=5))) is False  # within 10s window
    assert store.save(_snap(t + timedelta(seconds=11))) is True  # past window


def test_prune_before_removes_old_rows(store):
    old = datetime(2026, 6, 1, 8, 0, 0)
    new = datetime(2026, 6, 22, 8, 0, 0)
    store.save(_snap(old))
    store.save(_snap(new))
    removed = store.prune_before(datetime(2026, 6, 10))
    assert removed == 1
    rows = store.query_range(datetime(2026, 5, 1), datetime(2026, 7, 1))
    assert len(rows) == 1
    assert rows[0].ts == new
