# src/solar_advisor/ingest/safety.py
from __future__ import annotations


class WriteAttemptError(RuntimeError):
    """Raised if anything attempts to write to the inverter. Advisory-only invariant."""


def is_write_topic(topic: str) -> bool:
    """True for any inverter command/write topic."""
    return topic.endswith("/set") or topic.startswith("solar_assistant/set/")


def assert_read_only(topic: str) -> None:
    if is_write_topic(topic):
        raise WriteAttemptError(f"refusing to write to inverter topic: {topic}")
