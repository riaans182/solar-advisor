# tests/test_sqlite_store.py
from datetime import datetime, timedelta

import pytest

from solar_advisor.storage.sqlite_store import SqliteTelemetryStore
from tests.conftest import make_telemetry


@pytest.fixture
def store(tmp_path):
    return SqliteTelemetryStore(tmp_path / "t.db", min_interval=timedelta(seconds=10))


def test_save_then_query_roundtrip(store):
    t = datetime(2026, 6, 22, 8, 0, 0)
    assert store.save(make_telemetry(t, battery_soc=64)) is True
    rows = store.query_range(t - timedelta(minutes=1), t + timedelta(minutes=1))
    assert len(rows) == 1
    assert rows[0].battery_soc == 64
    assert rows[0].month_to_date_grid_import_kwh == 12.5


def test_downsampling_skips_writes_inside_min_interval(store):
    t = datetime(2026, 6, 22, 8, 0, 0)
    assert store.save(make_telemetry(t)) is True
    assert store.save(make_telemetry(t + timedelta(seconds=5))) is False  # within 10s window
    assert store.save(make_telemetry(t + timedelta(seconds=11))) is True  # past window


def test_prune_before_removes_old_rows(store):
    old = datetime(2026, 6, 1, 8, 0, 0)
    new = datetime(2026, 6, 22, 8, 0, 0)
    store.save(make_telemetry(old))
    store.save(make_telemetry(new))
    removed = store.prune_before(datetime(2026, 6, 10))
    assert removed == 1
    rows = store.query_range(datetime(2026, 5, 1), datetime(2026, 7, 1))
    assert len(rows) == 1
    assert rows[0].ts == new


def test_upsert_on_duplicate_ts_keeps_last_write(tmp_path):
    # min_interval=0 so the downsample guard never suppresses the second write.
    store = SqliteTelemetryStore(tmp_path / "t.db", min_interval=timedelta(0))
    t = datetime(2026, 6, 22, 8, 0, 0)
    assert store.save(make_telemetry(t, battery_soc=10)) is True
    assert store.save(make_telemetry(t, battery_soc=90)) is True
    rows = store.query_range(t - timedelta(minutes=1), t + timedelta(minutes=1))
    # INSERT OR REPLACE on the ts PRIMARY KEY => last write wins, single row.
    assert len(rows) == 1
    assert rows[0].battery_soc == 90


def test_query_range_returns_rows_sorted_by_ts(tmp_path):
    db = tmp_path / "t.db"
    t0 = datetime(2026, 6, 22, 8, 0, 0)
    t1 = datetime(2026, 6, 22, 8, 5, 0)
    t2 = datetime(2026, 6, 22, 8, 10, 0)
    # Insert out of chronological order. A fresh store per write resets the
    # per-instance downsample guard (which would otherwise drop an older ts),
    # so all three rows land regardless of insertion order.
    for ts in (t1, t0, t2):
        store = SqliteTelemetryStore(db, min_interval=timedelta(0))
        assert store.save(make_telemetry(ts)) is True
        store.close()
    store = SqliteTelemetryStore(db, min_interval=timedelta(0))
    rows = store.query_range(t0 - timedelta(minutes=1), t2 + timedelta(minutes=1))
    # query_range applies ORDER BY ts, so results come back ascending by ts.
    assert [r.ts for r in rows] == [t0, t1, t2]


def test_data_persists_across_reopen(tmp_path):
    db = tmp_path / "t.db"
    t = datetime(2026, 6, 22, 8, 0, 0)
    store = SqliteTelemetryStore(db, min_interval=timedelta(0))
    assert store.save(make_telemetry(t, battery_soc=42)) is True
    store.close()

    reopened = SqliteTelemetryStore(db, min_interval=timedelta(0))
    rows = reopened.query_range(t - timedelta(minutes=1), t + timedelta(minutes=1))
    assert len(rows) == 1
    assert rows[0].ts == t
    assert rows[0].battery_soc == 42


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
    out = store.query_bucketed(datetime(2026, 1, 1), datetime(2026, 1, 2), 3600)
    assert out == []
