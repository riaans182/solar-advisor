# tests/test_topic_map.py
from solar_advisor.ingest.topic_map import TELEMETRY_TOPICS, parse_value


def test_known_telemetry_topic_maps_to_field_and_float():
    field, value = parse_value("solar_assistant/total/battery_state_of_charge/state", "64")
    assert field == "battery_soc"
    assert value == 64.0


def test_unknown_topic_returns_none():
    assert parse_value("solar_assistant/total/nonsense/state", "1") is None


def test_camera_noise_topic_returns_none():
    assert parse_value("frigate/driveway/snapshot", "<binary>") is None


def test_topic_map_covers_all_telemetry_fields():
    expected = {
        "battery_soc",
        "battery_power",
        "battery_voltage",
        "battery_current",
        "pv_power",
        "grid_power",
        "load_power",
        "load_power_essential",
        "grid_energy_in",
        "grid_energy_out",
        "pv_energy",
        "load_energy",
        "battery_energy_in",
        "battery_energy_out",
    }
    assert set(TELEMETRY_TOPICS.values()) == expected
