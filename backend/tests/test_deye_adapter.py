# tests/test_deye_adapter.py
from datetime import datetime

from solar_advisor.ingest.deye_adapter import DeyeAdapter

ALL_FIELDS = {
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


def test_no_snapshot_until_all_fields_seen():
    adapter = DeyeAdapter()
    items = list(ALL_FIELDS.items())
    for topic, payload in items[:-1]:
        assert adapter.ingest(datetime(2026, 6, 22, 8, 0), topic, payload) is None
    # Last field completes the set → snapshot emitted.
    last_topic, last_payload = items[-1]
    snap = adapter.ingest(datetime(2026, 6, 22, 8, 0), last_topic, last_payload)
    assert snap is not None
    assert snap.battery_soc == 64.0
    assert snap.grid_power == 1140.0


def test_ignores_unknown_topics():
    adapter = DeyeAdapter()
    assert adapter.ingest(datetime(2026, 6, 22, 8, 0), "frigate/x/snapshot", "junk") is None


def test_month_to_date_derived_from_grid_energy_in():
    adapter = DeyeAdapter()
    for topic, payload in ALL_FIELDS.items():
        adapter.ingest(datetime(2026, 6, 22, 8, 0), topic, payload)
    snap = adapter.ingest(
        datetime(2026, 6, 23, 8, 0), "solar_assistant/total/grid_energy_in/state", "1012.5"
    )
    assert snap is not None
    assert snap.month_to_date_grid_import_kwh == 12.5
