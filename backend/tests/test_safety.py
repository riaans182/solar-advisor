# tests/test_safety.py
import pytest

from solar_advisor.ingest.safety import WriteAttemptError, assert_read_only, is_write_topic


@pytest.mark.parametrize(
    "topic",
    [
        "solar_assistant/inverter_1/max_charge_current/set",
        "solar_assistant/inverter_1/grid_charge_point_1/set",
        "solar_assistant/set/response_message/state",
    ],
)
def test_write_topics_detected(topic):
    assert is_write_topic(topic) is True


@pytest.mark.parametrize(
    "topic",
    [
        "solar_assistant/total/battery_state_of_charge/state",
        "solar_assistant/inverter_1/pv_power/state",
    ],
)
def test_read_topics_allowed(topic):
    assert is_write_topic(topic) is False


def test_assert_read_only_raises_on_write_topic():
    with pytest.raises(WriteAttemptError):
        assert_read_only("solar_assistant/inverter_1/max_charge_current/set")


def test_assert_read_only_silent_on_read_topic():
    assert_read_only("solar_assistant/inverter_1/pv_power/state")  # no raise
