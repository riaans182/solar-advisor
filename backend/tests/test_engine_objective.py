# tests/test_engine_objective.py
from solar_advisor.engine.objective import reserve_target_soc


def test_cost_end_returns_floor():
    assert reserve_target_soc(0.0, floor_pct=20.0) == 20.0


def test_resilience_end_returns_ceiling():
    assert reserve_target_soc(1.0, floor_pct=20.0, ceiling_pct=100.0) == 100.0


def test_balanced_is_midpoint():
    assert reserve_target_soc(0.5, floor_pct=20.0, ceiling_pct=100.0) == 60.0


def test_objective_is_clamped_to_unit_interval():
    assert reserve_target_soc(-1.0, floor_pct=20.0) == 20.0
    assert reserve_target_soc(2.0, floor_pct=20.0, ceiling_pct=100.0) == 100.0


def test_reserve_is_monotonic_non_decreasing_in_objective():
    vals = [reserve_target_soc(o / 10, floor_pct=20.0) for o in range(11)]
    assert vals == sorted(vals)
