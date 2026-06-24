# src/solar_advisor/ingest/schedule_accumulator.py
from __future__ import annotations

from solar_advisor.domain.schedule import Slot, build_schedule
from solar_advisor.ingest.schedule_topics import (
    SCHEDULE_FIELDS,
    SLOT_COUNT,
    parse_schedule_value,
)


class ScheduleAccumulator:
    """Collects the 24 schedule topic values and emits a Schedule once every
    field/slot is present. Returns None until then. build_schedule owns all
    typing, so we store raw payload strings here."""

    def __init__(self) -> None:
        self._raw: dict[str, dict[int, str]] = {field: {} for field in SCHEDULE_FIELDS}

    def ingest(self, topic: str, payload: str) -> list[Slot] | None:
        parsed = parse_schedule_value(topic, payload)
        if parsed is None:
            return None
        field, slot, raw = parsed
        self._raw[field][slot] = raw
        if not self._is_complete():
            return None
        try:
            return build_schedule(self._raw)
        except ValueError:
            # A malformed payload (e.g. capacity "abc", time "9") must not kill
            # the async ingest loop. Degrade to "no schedule yet"; a later valid
            # payload overwrites the bad value and the schedule then builds.
            return None

    def _is_complete(self) -> bool:
        return all(len(self._raw[field]) == SLOT_COUNT for field in SCHEDULE_FIELDS)
