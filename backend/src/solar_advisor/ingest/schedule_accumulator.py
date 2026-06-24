# src/solar_advisor/ingest/schedule_accumulator.py
from __future__ import annotations

from typing import Any

from solar_advisor.domain.schedule import Slot, build_schedule
from solar_advisor.ingest.schedule_topics import SCHEDULE_FIELDS, parse_schedule_value

_BOOL_FIELDS = {"grid_charge_point", "gen_charge_point"}


class ScheduleAccumulator:
    """Collects the 24 schedule topic values and emits a Schedule once every
    field/slot is present. Returns None until then."""

    def __init__(self) -> None:
        self._raw: dict[str, dict[int, Any]] = {field: {} for field in SCHEDULE_FIELDS}

    def ingest(self, topic: str, payload: str) -> list[Slot] | None:
        parsed = parse_schedule_value(topic, payload)
        if parsed is None:
            return None
        field, slot, raw = parsed
        if field in _BOOL_FIELDS:
            self._raw[field][slot] = raw.strip().lower() == "true"
        else:
            self._raw[field][slot] = raw
        if not self._is_complete():
            return None
        return build_schedule(self._raw)

    def _is_complete(self) -> bool:
        return all(len(self._raw[field]) == 6 for field in SCHEDULE_FIELDS)
