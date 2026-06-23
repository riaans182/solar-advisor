# tests/test_mqtt_client.py
from solar_advisor.ingest.mqtt_client import ReadOnlyMqttClient


def test_client_exposes_no_publish_capability():
    # The advisory-only invariant, made testable: the class surfaces no method
    # whose name implies writing/publishing to the broker.
    names = [n for n in dir(ReadOnlyMqttClient) if not n.startswith("_")]
    assert not [n for n in names if "publish" in n.lower() or n.lower() == "set"]


def test_subscribe_filter_is_solar_assistant_only():
    client = ReadOnlyMqttClient(host="localhost", port=1883)
    assert client.topic_filter == "solar_assistant/#"
