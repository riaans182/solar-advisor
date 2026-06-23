# tests/test_accumulator.py
from datetime import datetime

from solar_advisor.ingest.accumulator import MonthToDateAccumulator


def test_non_finite_first_reading_does_not_poison_state():
    acc = MonthToDateAccumulator()
    assert acc.update(datetime(2026, 6, 22, 8, 0), float("nan")) == 0.0
    # A subsequent finite reading establishes the baseline normally.
    assert acc.update(datetime(2026, 6, 22, 8, 0), 1000.0) == 0.0
    assert acc.update(datetime(2026, 6, 23, 8, 0), 1012.5) == 12.5


def test_non_finite_reading_mid_stream_is_ignored():
    acc = MonthToDateAccumulator()
    acc.update(datetime(2026, 6, 22, 8, 0), 1000.0)
    # Non-finite reading is ignored: returns last good month-to-date.
    assert acc.update(datetime(2026, 6, 22, 9, 0), float("nan")) == 0.0
    assert acc.update(datetime(2026, 6, 22, 10, 0), 1005.0) == 5.0


def test_first_reading_is_zero_month_to_date():
    acc = MonthToDateAccumulator()
    assert acc.update(datetime(2026, 6, 22, 8, 0), 1000.0) == 0.0


def test_accumulates_within_month():
    acc = MonthToDateAccumulator()
    acc.update(datetime(2026, 6, 22, 8, 0), 1000.0)
    assert acc.update(datetime(2026, 6, 23, 8, 0), 1012.5) == 12.5


def test_resets_at_month_rollover():
    acc = MonthToDateAccumulator()
    acc.update(datetime(2026, 6, 22, 8, 0), 1000.0)
    acc.update(datetime(2026, 6, 30, 8, 0), 1030.0)
    # New month: baseline rebases to the first reading of July.
    assert acc.update(datetime(2026, 7, 1, 8, 0), 1031.0) == 0.0
    assert acc.update(datetime(2026, 7, 2, 8, 0), 1036.0) == 5.0


def test_tolerates_counter_reset():
    acc = MonthToDateAccumulator()
    acc.update(datetime(2026, 6, 22, 8, 0), 1000.0)
    # Counter reset (e.g. inverter reboot): value drops below last seen.
    assert acc.update(datetime(2026, 6, 22, 9, 0), 5.0) == 0.0
    assert acc.update(datetime(2026, 6, 22, 10, 0), 8.0) == 3.0
