# tests/test_live_ingest.py
from datetime import UTC, datetime, timedelta

from solar_advisor.ingest.live import LiveState
from solar_advisor.storage.sqlite_store import SqliteTelemetryStore

ALL_TELEMETRY = {
    "solar_assistant/total/battery_state_of_charge/state": "64",
    "solar_assistant/total/battery_power/state": "85",
    "solar_assistant/inverter_1/battery_voltage/state": "50.0",
    "solar_assistant/inverter_1/battery_current/state": "1.7",
    "solar_assistant/inverter_1/pv_power/state": "106",
    "solar_assistant/inverter_1/grid_power/state": "1140",
    "solar_assistant/inverter_1/load_power/state": "1086",
    "solar_assistant/inverter_1/load_power_essential/state": "1136",
    "solar_assistant/total/grid_energy_in/state": "1000",
    "solar_assistant/total/grid_energy_out/state": "0",
    "solar_assistant/total/pv_energy/state": "0",
    "solar_assistant/total/load_energy/state": "0",
    "solar_assistant/total/battery_energy_in/state": "0",
    "solar_assistant/total/battery_energy_out/state": "0",
}


def test_live_state_updates_telemetry_and_persists(tmp_path):
    store = SqliteTelemetryStore(tmp_path / "live.db", min_interval=timedelta(0))
    state = LiveState(store=store)
    ts = datetime(2026, 6, 22, 8, 0, tzinfo=UTC)
    for topic, payload in ALL_TELEMETRY.items():
        state.handle(ts, topic, payload)
    assert state.telemetry is not None
    assert state.telemetry.battery_soc == 64.0
    # Persisted to the store.
    rows = store.query_range(ts - timedelta(minutes=1), ts + timedelta(minutes=1))
    assert len(rows) == 1


def test_live_state_updates_schedule():
    state = LiveState(store=None)
    raw = {
        "time_point": {1: "00:00", 2: "05:00", 3: "08:00", 4: "16:30", 5: "18:00", 6: "21:30"},
        "capacity_point": {1: "65", 2: "65", 3: "90", 4: "95", 5: "75", 6: "65"},
        "grid_charge_point": {1: "true", 2: "true", 3: "true", 4: "false", 5: "true", 6: "true"},
        "gen_charge_point": {i: "false" for i in range(1, 7)},
    }
    ts = datetime(2026, 6, 22, 8, 0, tzinfo=UTC)
    for field, slots in raw.items():
        for i, val in slots.items():
            state.handle(ts, f"solar_assistant/inverter_1/{field}_{i}/state", val)
    assert state.schedule is not None
    assert len(state.schedule) == 6


def test_live_state_ignores_write_topics():
    import pytest

    from solar_advisor.ingest.safety import WriteAttemptError

    state = LiveState(store=None)
    with pytest.raises(WriteAttemptError):
        state.handle(datetime.now(UTC), "solar_assistant/inverter_1/max_charge_current/set", "150")
