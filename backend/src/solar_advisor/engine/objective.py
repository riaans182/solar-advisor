# src/solar_advisor/engine/objective.py
from __future__ import annotations


def reserve_target_soc(objective: float, floor_pct: float, ceiling_pct: float = 100.0) -> float:
    """Map the cost<->resilience scalar to a target backup reserve SOC.

    objective 0.0 = pure cost (reserve at the battery floor);
    objective 1.0 = pure resilience (reserve at the ceiling). Linear, clamped.

    Precondition: callers must pass floor_pct <= ceiling_pct (values come from
    validated config).
    """
    o = min(1.0, max(0.0, objective))
    return floor_pct + o * (ceiling_pct - floor_pct)
