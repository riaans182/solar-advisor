# src/solar_advisor/ingest/schedule_topics.py
from __future__ import annotations

import re

# The four per-slot schedule fields (i = 1..6). All vendor-specific knowledge
# for the TOU schedule lives here (spec §3.1).
SCHEDULE_FIELDS = ("time_point", "capacity_point", "grid_charge_point", "gen_charge_point")

_PATTERN = re.compile(
    r"^solar_assistant/inverter_1/(time_point|capacity_point|grid_charge_point|gen_charge_point)_([1-6])/state$"
)


def parse_schedule_value(topic: str, payload: str) -> tuple[str, int, str] | None:
    """Map a schedule topic to (field, slot_index, raw_payload). None if not a
    schedule topic. The payload stays raw; build_schedule does the typing."""
    match = _PATTERN.match(topic)
    if match is None:
        return None
    return match.group(1), int(match.group(2)), payload
