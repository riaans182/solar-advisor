# Plan B — Deterministic Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the pure, deterministic optimisation engine — flat-rate tariff, battery model, a day-simulation schedule evaluator, an objective (cost↔resilience) policy, and a recommender — plus the I/O-bound parameter estimator that feeds it from stored telemetry.

**Architecture:** `engine/` is pure (no I/O, no network, no LLM, no storage) and is enforced by the existing `import-linter` contract. It consumes the vendor-neutral domain types from Plan A (`Telemetry`, `Slot`) plus plain value inputs (`SolarForecast`, `LoadProfile`, `DaylightWindow`). The `estimation/` service does the I/O (reads `TelemetryStore`) and hands the engine plain values. `forecast/` declares the provider interface only (the HA adapter is Plan C).

**Tech Stack:** Python 3.12+, stdlib `dataclasses`/`enum`, `pytest`, `ruff`, `mypy --strict`, `import-linter`. No new dependencies.

**Covers spec stages:** 3 (Engine core), 4 (Estimation), 5 (Optimizer + slider). See `docs/superpowers/specs/2026-06-22-solar-advisor-design.md` §§5, 5.2, 5.3, 5.4, 6, 9.

**Builds on Plan A (on `main`):** `solar_advisor.domain.telemetry.Telemetry`, `solar_advisor.domain.schedule.Slot`, `solar_advisor.storage.store.TelemetryStore`. The `engine`, `forecast`, `estimation` packages currently contain only empty `__init__.py`.

---

## Modelling decisions (deliberate MVP simplifications)

These are intentional and documented so reviewers don't flag them as gaps; they are refinable later without changing interfaces:

- **Flat tariff:** marginal cost of a grid kWh is constant (spec §6). `marginal_rate` ignores month-to-date; the monthly fixed charge appears only in `monthly_cost` (bill projection), never in marginal decisions.
- **Schedule evaluator** simulates the day slot-by-slot in chronological order from a starting SOC, allocating the day's forecast PV across slots by their overlap with a daylight window, and serving load solar-first → battery (down to the SOC floor) → grid. Grid charging only occurs in a slot whose `grid_charge` flag is set and only up to that slot's `target_soc`, capped by charge power × slot hours.
- **Recommender** is a *policy* (reserve-SOC target + whether overnight grid-charging is needed + expected cost/backup), not a re-simulated 6-slot schedule. It uses a daily energy balance. Re-simulating candidate schedules is a future refinement.
- **No charge/discharge efficiency losses, no temperature derating** in the MVP energy model.

---

## File structure (created by this plan)

```
backend/src/solar_advisor/
├─ engine/
│  ├─ inputs.py          # SolarForecast, LoadProfile, DaylightWindow (plain value inputs)
│  ├─ tariff.py          # TariffModel Protocol + FlatRateTariff
│  ├─ battery.py         # BatteryModel (soc<->kWh, floor, power limits)
│  ├─ objective.py       # reserve_target_soc(objective, floor, ceiling)
│  ├─ schedule_eval.py   # SlotBehavior, SlotAssessment, assess_schedule (day simulation)
│  └─ optimize.py        # Recommendation, recommend(...)
├─ forecast/
│  └─ provider.py        # ForecastProvider Protocol (interface only; adapter = Plan C)
└─ estimation/
   └─ estimator.py       # EstimatedParameters, ParameterEstimator (reads TelemetryStore)
backend/tests/
├─ test_engine_tariff.py
├─ test_engine_battery.py
├─ test_engine_objective.py
├─ test_engine_schedule_eval.py
├─ test_engine_optimize.py
├─ test_forecast_provider.py
└─ test_estimation.py
backend/.importlinter        # MODIFY: add solar_advisor.estimation to engine's forbidden list
```

All tooling runs via the project venv (Plan A made the Makefile self-contained):
`cd backend && make check` (ruff + mypy strict + import-linter + pytest). Run single tests with `.venv/bin/pytest tests/<file>.py -v`.

---

## Task 1: Engine value inputs

**Files:**
- Create: `backend/src/solar_advisor/engine/inputs.py`
- Test: `backend/tests/test_engine_optimize.py` (constructed here; reused by later tasks)

- [ ] **Step 1: Write `inputs.py`**

```python
# src/solar_advisor/engine/inputs.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True, slots=True)
class SolarForecast:
    """Expected PV generation. Maps to HA Forecast.Solar today/tomorrow totals."""

    expected_pv_kwh_today: float
    expected_pv_kwh_tomorrow: float


@dataclass(frozen=True, slots=True)
class LoadProfile:
    """Consumption inputs. essential_power_w is the continuous backup-critical load
    (from load_power_essential history)."""

    daily_kwh: float
    essential_power_w: float


@dataclass(frozen=True, slots=True)
class DaylightWindow:
    """Window over which PV is assumed to generate, used to allocate forecast PV
    across schedule slots."""

    dawn: time
    dusk: time
```

- [ ] **Step 2: Verify it imports**

Run: `cd backend && .venv/bin/python -c "from solar_advisor.engine.inputs import SolarForecast, LoadProfile, DaylightWindow; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/src/solar_advisor/engine/inputs.py
git commit -m "feat(engine): value inputs (forecast, load, daylight)"
```

---

## Task 2: Flat-rate tariff

**Files:**
- Create: `backend/src/solar_advisor/engine/tariff.py`
- Test: `backend/tests/test_engine_tariff.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_tariff.py
from solar_advisor.engine.tariff import FlatRateTariff, TariffModel


def test_marginal_rate_is_flat_regardless_of_month_to_date():
    t = FlatRateTariff(energy_rate=3.56, monthly_fixed_charge=600.0)
    assert t.marginal_rate(0.0) == 3.56
    assert t.marginal_rate(1000.0) == 3.56  # no inclining block


def test_monthly_cost_is_fixed_plus_import_times_rate():
    t = FlatRateTariff(energy_rate=3.56, monthly_fixed_charge=600.0)
    assert t.monthly_cost(100.0, days_in_month=30) == 600.0 + 100.0 * 3.56


def test_flat_rate_satisfies_tariff_model_protocol():
    t: TariffModel = FlatRateTariff(energy_rate=3.56, monthly_fixed_charge=600.0)
    assert isinstance(t, TariffModel)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_engine_tariff.py -v`
Expected: FAIL with `ModuleNotFoundError: solar_advisor.engine.tariff`.

- [ ] **Step 3: Write the implementation**

```python
# src/solar_advisor/engine/tariff.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class TariffModel(Protocol):
    """A tariff. The protocol is kept (not collapsed to a constant) so a future
    inclining-block adapter can return without touching the engine (spec §6)."""

    def marginal_rate(self, month_to_date_kwh: float) -> float: ...
    def monthly_cost(self, import_kwh: float, days_in_month: int) -> float: ...


@dataclass(frozen=True, slots=True)
class FlatRateTariff:
    """Eskom Direct prepaid flat rate: constant per-kWh marginal rate; the monthly
    fixed charge is a sunk cost that affects only bill projection (spec §6)."""

    energy_rate: float  # R/kWh
    monthly_fixed_charge: float  # R/month

    def marginal_rate(self, month_to_date_kwh: float) -> float:
        return self.energy_rate

    def monthly_cost(self, import_kwh: float, days_in_month: int) -> float:
        return self.monthly_fixed_charge + import_kwh * self.energy_rate
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_engine_tariff.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/solar_advisor/engine/tariff.py backend/tests/test_engine_tariff.py
git commit -m "feat(engine): flat-rate tariff with fixed monthly charge"
```

---

## Task 3: Battery model

**Files:**
- Create: `backend/src/solar_advisor/engine/battery.py`
- Test: `backend/tests/test_engine_battery.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_battery.py
from solar_advisor.engine.battery import BatteryModel


def _batt():
    # 15 kWh nominal (3x Dyness 5 kWh), 20% floor, ~7.6 kW charge/discharge
    return BatteryModel(
        usable_kwh=15.0, soc_floor_pct=20.0,
        max_charge_power_w=7600.0, max_discharge_power_w=7600.0,
    )


def test_soc_to_kwh():
    assert _batt().soc_to_kwh(50.0) == 7.5


def test_floor_kwh():
    assert _batt().floor_kwh == 3.0  # 15 * 20%


def test_energy_between_soc_levels():
    assert _batt().energy_between(40.0, 90.0) == 7.5  # 15 * 50%
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_engine_battery.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
# src/solar_advisor/engine/battery.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BatteryModel:
    """Energy model of the battery. SOC is a percentage; energy in kWh.
    No charge/discharge efficiency or temperature derating in the MVP model."""

    usable_kwh: float
    soc_floor_pct: float
    max_charge_power_w: float
    max_discharge_power_w: float

    def soc_to_kwh(self, soc_pct: float) -> float:
        return self.usable_kwh * soc_pct / 100.0

    def energy_between(self, soc_lo_pct: float, soc_hi_pct: float) -> float:
        return self.usable_kwh * (soc_hi_pct - soc_lo_pct) / 100.0

    @property
    def floor_kwh(self) -> float:
        return self.soc_to_kwh(self.soc_floor_pct)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_engine_battery.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/solar_advisor/engine/battery.py backend/tests/test_engine_battery.py
git commit -m "feat(engine): battery energy model"
```

---

## Task 4: Objective (cost↔resilience) policy

**Files:**
- Create: `backend/src/solar_advisor/engine/objective.py`
- Test: `backend/tests/test_engine_objective.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_engine_objective.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
# src/solar_advisor/engine/objective.py
from __future__ import annotations


def reserve_target_soc(
    objective: float, floor_pct: float, ceiling_pct: float = 100.0
) -> float:
    """Map the cost<->resilience scalar to a target backup reserve SOC.

    objective 0.0 = pure cost (reserve at the battery floor);
    objective 1.0 = pure resilience (reserve at the ceiling). Linear, clamped.
    """
    o = min(1.0, max(0.0, objective))
    return floor_pct + o * (ceiling_pct - floor_pct)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_engine_objective.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/solar_advisor/engine/objective.py backend/tests/test_engine_objective.py
git commit -m "feat(engine): cost-resilience objective to reserve-SOC policy"
```

---

## Task 5: Schedule evaluator (day simulation)

Simulates the current 6-slot schedule chronologically from a starting SOC and classifies each slot, with the grid energy it draws and its cost.

**Files:**
- Create: `backend/src/solar_advisor/engine/schedule_eval.py`
- Test: `backend/tests/test_engine_schedule_eval.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_schedule_eval.py
from datetime import time

from solar_advisor.domain.schedule import Slot
from solar_advisor.engine.battery import BatteryModel
from solar_advisor.engine.inputs import DaylightWindow, LoadProfile, SolarForecast
from solar_advisor.engine.schedule_eval import SlotBehavior, assess_schedule
from solar_advisor.engine.tariff import FlatRateTariff


def _battery():
    return BatteryModel(
        usable_kwh=15.0, soc_floor_pct=20.0,
        max_charge_power_w=7600.0, max_discharge_power_w=7600.0,
    )


def _tariff():
    return FlatRateTariff(energy_rate=3.56, monthly_fixed_charge=600.0)


def _daylight():
    return DaylightWindow(dawn=time(7, 0), dusk=time(17, 30))


def _two_slots():
    # Night slot then a daytime slot.
    return [
        Slot(start=time(0, 0), end=time(7, 0), target_soc=90, grid_charge=True, gen_charge=False),
        Slot(start=time(7, 0), end=time(17, 30), target_soc=95, grid_charge=False, gen_charge=False),
    ]


def test_returns_one_assessment_per_slot():
    out = assess_schedule(
        _two_slots(), _battery(), _tariff(),
        SolarForecast(expected_pv_kwh_today=20.0, expected_pv_kwh_tomorrow=20.0),
        LoadProfile(daily_kwh=24.0, essential_power_w=500.0),
        _daylight(), start_soc=50.0, month_to_date_import_kwh=0.0,
    )
    assert len(out) == 2


def test_night_grid_charge_slot_classified_grid_charging_with_cost():
    out = assess_schedule(
        _two_slots(), _battery(), _tariff(),
        SolarForecast(expected_pv_kwh_today=20.0, expected_pv_kwh_tomorrow=20.0),
        LoadProfile(daily_kwh=24.0, essential_power_w=500.0),
        _daylight(), start_soc=50.0, month_to_date_import_kwh=0.0,
    )
    night = out[0]
    assert night.behavior is SlotBehavior.GRID_CHARGING  # no solar, grid-charging to 90%
    assert night.grid_import_kwh > 0
    assert night.cost == night.grid_import_kwh * 3.56


def test_daytime_slot_with_strong_sun_charges_from_solar():
    out = assess_schedule(
        _two_slots(), _battery(), _tariff(),
        SolarForecast(expected_pv_kwh_today=40.0, expected_pv_kwh_tomorrow=40.0),
        LoadProfile(daily_kwh=12.0, essential_power_w=500.0),
        _daylight(), start_soc=50.0, month_to_date_import_kwh=0.0,
    )
    day = out[1]
    assert day.behavior is SlotBehavior.SOLAR_CHARGING
    assert day.grid_import_kwh == 0.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_engine_schedule_eval.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
# src/solar_advisor/engine/schedule_eval.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from enum import Enum

from solar_advisor.domain.schedule import Slot
from solar_advisor.engine.battery import BatteryModel
from solar_advisor.engine.inputs import DaylightWindow, LoadProfile, SolarForecast
from solar_advisor.engine.tariff import TariffModel


class SlotBehavior(Enum):
    SOLAR_CHARGING = "solar_charging"
    GRID_CHARGING = "grid_charging"
    DISCHARGING = "discharging"
    HOLDING = "holding"


@dataclass(frozen=True, slots=True)
class SlotAssessment:
    slot: Slot
    behavior: SlotBehavior
    end_soc: float  # projected SOC % at slot end
    grid_import_kwh: float  # grid energy drawn during the slot (load deficit + grid charge)
    cost: float  # grid_import_kwh * marginal rate


def _to_hours(t: time) -> float:
    return t.hour + t.minute / 60.0


def _slot_hours(slot: Slot) -> float:
    start, end = _to_hours(slot.start), _to_hours(slot.end)
    span = end - start
    return span + 24.0 if span <= 0 else span  # wrap past midnight


def _overlap_hours(slot: Slot, daylight: DaylightWindow) -> float:
    """Hours of the slot that fall within the daylight window. Slots that wrap
    midnight are treated as not overlapping daylight (night slots)."""
    start, end = _to_hours(slot.start), _to_hours(slot.end)
    if end <= start:  # wraps midnight -> night slot
        return 0.0
    lo = max(start, _to_hours(daylight.dawn))
    hi = min(end, _to_hours(daylight.dusk))
    return max(0.0, hi - lo)


def assess_schedule(
    schedule: list[Slot],
    battery: BatteryModel,
    tariff: TariffModel,
    forecast: SolarForecast,
    load: LoadProfile,
    daylight: DaylightWindow,
    start_soc: float,
    month_to_date_import_kwh: float,
) -> list[SlotAssessment]:
    """Simulate the schedule chronologically and classify each slot. PV is
    allocated across slots in proportion to their daylight overlap; load is served
    solar-first, then battery down to the floor, then grid. Grid charging happens
    only in a slot whose grid_charge flag is set, up to target_soc, capped by power.
    """
    rate = tariff.marginal_rate(month_to_date_import_kwh)
    total_overlap = sum(_overlap_hours(s, daylight) for s in schedule)
    soc_kwh = battery.soc_to_kwh(start_soc)
    floor_kwh = battery.floor_kwh

    out: list[SlotAssessment] = []
    for slot in schedule:
        hours = _slot_hours(slot)
        load_kwh = load.daily_kwh * hours / 24.0
        solar_kwh = (
            forecast.expected_pv_kwh_today * _overlap_hours(slot, daylight) / total_overlap
            if total_overlap > 0
            else 0.0
        )
        net = solar_kwh - load_kwh
        grid_import = 0.0

        if net >= 0:
            soc_kwh = min(battery.usable_kwh, soc_kwh + net)
        else:
            deficit = -net
            from_batt = min(max(0.0, soc_kwh - floor_kwh), deficit)
            soc_kwh -= from_batt
            grid_import += deficit - from_batt

        grid_charge = 0.0
        target_kwh = battery.soc_to_kwh(slot.target_soc)
        if slot.grid_charge and soc_kwh < target_kwh:
            max_charge_kwh = battery.max_charge_power_w / 1000.0 * hours
            grid_charge = min(target_kwh - soc_kwh, max_charge_kwh)
            soc_kwh += grid_charge
            grid_import += grid_charge

        if grid_charge > 0:
            behavior = SlotBehavior.GRID_CHARGING
        elif net > 0:
            behavior = SlotBehavior.SOLAR_CHARGING
        elif net < 0:
            behavior = SlotBehavior.DISCHARGING
        else:
            behavior = SlotBehavior.HOLDING

        out.append(
            SlotAssessment(
                slot=slot,
                behavior=behavior,
                end_soc=soc_kwh / battery.usable_kwh * 100.0,
                grid_import_kwh=grid_import,
                cost=grid_import * rate,
            )
        )
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_engine_schedule_eval.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/solar_advisor/engine/schedule_eval.py backend/tests/test_engine_schedule_eval.py
git commit -m "feat(engine): schedule evaluator via day simulation"
```

---

## Task 6: Recommender (objective → policy + scores)

**Files:**
- Create: `backend/src/solar_advisor/engine/optimize.py`
- Test: `backend/tests/test_engine_optimize.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_optimize.py
from solar_advisor.engine.battery import BatteryModel
from solar_advisor.engine.inputs import LoadProfile, SolarForecast
from solar_advisor.engine.optimize import Recommendation, recommend
from solar_advisor.engine.tariff import FlatRateTariff


def _common():
    return dict(
        battery=BatteryModel(
            usable_kwh=15.0, soc_floor_pct=20.0,
            max_charge_power_w=7600.0, max_discharge_power_w=7600.0,
        ),
        tariff=FlatRateTariff(energy_rate=3.56, monthly_fixed_charge=600.0),
        # Solar short of load so a deficit exists; low SOC so reserve needs grid.
        forecast=SolarForecast(expected_pv_kwh_today=8.0, expected_pv_kwh_tomorrow=8.0),
        load=LoadProfile(daily_kwh=20.0, essential_power_w=500.0),
        current_soc=30.0,
        month_to_date_import_kwh=100.0,
        days_in_month=30,
    )


def test_cost_end_no_grid_charge_reserve_at_floor():
    r = recommend(objective=0.0, **_common())
    assert isinstance(r, Recommendation)
    assert r.reserve_target_soc == 20.0
    assert r.enable_overnight_grid_charge is False
    assert r.grid_charge_kwh == 0.0
    # Only the load deficit (20 - 8 = 12 kWh) is imported.
    assert r.expected_daily_grid_import_kwh == 12.0
    assert r.expected_daily_cost == 12.0 * 3.56


def test_resilience_end_grid_charges_and_costs_more():
    cost = recommend(objective=0.0, **_common())
    resil = recommend(objective=1.0, **_common())
    assert resil.reserve_target_soc == 100.0
    assert resil.enable_overnight_grid_charge is True
    assert resil.grid_charge_kwh > 0
    assert resil.expected_daily_cost > cost.expected_daily_cost
    assert resil.backup_hours > cost.backup_hours


def test_slider_sweep_is_monotonic():
    rs = [recommend(objective=o / 10, **_common()) for o in range(11)]
    reserves = [r.reserve_target_soc for r in rs]
    costs = [r.expected_daily_cost for r in rs]
    assert reserves == sorted(reserves)
    assert costs == sorted(costs)


def test_monthly_cost_uses_fixed_charge_plus_month_to_date():
    r = recommend(objective=0.0, **_common())
    assert r.monthly_cost_so_far == 600.0 + 100.0 * 3.56
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_engine_optimize.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
# src/solar_advisor/engine/optimize.py
from __future__ import annotations

from dataclasses import dataclass

from solar_advisor.engine.battery import BatteryModel
from solar_advisor.engine.inputs import LoadProfile, SolarForecast
from solar_advisor.engine.objective import reserve_target_soc
from solar_advisor.engine.tariff import TariffModel


@dataclass(frozen=True, slots=True)
class Recommendation:
    reserve_target_soc: float  # % backup reserve the policy targets
    enable_overnight_grid_charge: bool
    grid_charge_kwh: float  # grid energy needed to reach the reserve (0 if solar suffices)
    expected_daily_grid_import_kwh: float  # load deficit + grid charge
    expected_daily_cost: float  # marginal cost of the day's grid import
    backup_hours: float  # how long the reserve powers the essential load
    monthly_cost_so_far: float  # fixed charge + month-to-date import (bill projection)


def recommend(
    *,
    battery: BatteryModel,
    tariff: TariffModel,
    forecast: SolarForecast,
    load: LoadProfile,
    objective: float,
    current_soc: float,
    month_to_date_import_kwh: float,
    days_in_month: int,
) -> Recommendation:
    """Daily energy-balance policy. With a flat tariff and no cheap window,
    self-consumption minimises the bill; grid-charging is pure cost justified only
    by the resilience reserve the objective scalar asks for (spec §5.4)."""
    reserve_soc = reserve_target_soc(objective, battery.soc_floor_pct)
    reserve_kwh = battery.soc_to_kwh(reserve_soc)

    expected_pv = forecast.expected_pv_kwh_today
    load_deficit = max(0.0, load.daily_kwh - expected_pv)

    current_kwh = battery.soc_to_kwh(current_soc)
    solar_surplus = max(0.0, expected_pv - load.daily_kwh)
    projected_kwh = min(battery.usable_kwh, current_kwh + solar_surplus)
    grid_charge_kwh = max(0.0, reserve_kwh - projected_kwh)

    daily_import = load_deficit + grid_charge_kwh
    rate = tariff.marginal_rate(month_to_date_import_kwh)
    backup_hours = (
        reserve_kwh * 1000.0 / load.essential_power_w
        if load.essential_power_w > 0
        else 0.0
    )

    return Recommendation(
        reserve_target_soc=reserve_soc,
        enable_overnight_grid_charge=grid_charge_kwh > 0,
        grid_charge_kwh=grid_charge_kwh,
        expected_daily_grid_import_kwh=daily_import,
        expected_daily_cost=daily_import * rate,
        backup_hours=backup_hours,
        monthly_cost_so_far=tariff.monthly_cost(month_to_date_import_kwh, days_in_month),
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_engine_optimize.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/solar_advisor/engine/optimize.py backend/tests/test_engine_optimize.py
git commit -m "feat(engine): cost-resilience recommender with scores"
```

---

## Task 7: Forecast provider interface

**Files:**
- Create: `backend/src/solar_advisor/forecast/provider.py`
- Test: `backend/tests/test_forecast_provider.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_forecast_provider.py
from solar_advisor.engine.inputs import SolarForecast
from solar_advisor.forecast.provider import ForecastProvider


class _StubProvider:
    def fetch(self) -> SolarForecast:
        return SolarForecast(expected_pv_kwh_today=10.0, expected_pv_kwh_tomorrow=12.0)


def test_stub_satisfies_forecast_provider_protocol():
    p: ForecastProvider = _StubProvider()
    assert isinstance(p, ForecastProvider)
    assert p.fetch().expected_pv_kwh_today == 10.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_forecast_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: solar_advisor.forecast.provider`.

- [ ] **Step 3: Write the implementation**

```python
# src/solar_advisor/forecast/provider.py
from __future__ import annotations

from typing import Protocol, runtime_checkable

from solar_advisor.engine.inputs import SolarForecast


@runtime_checkable
class ForecastProvider(Protocol):
    """Fetches a solar forecast. The concrete HA Forecast.Solar adapter lands in
    Plan C; the engine consumes the returned SolarForecast value (spec §9)."""

    def fetch(self) -> SolarForecast: ...
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_forecast_provider.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add backend/src/solar_advisor/forecast/provider.py backend/tests/test_forecast_provider.py
git commit -m "feat(forecast): provider interface returning SolarForecast"
```

---

## Task 8: Parameter estimator + boundary contract update

The estimator reads stored telemetry (I/O, outside the pure engine) and produces the values the engine needs but the inverter doesn't report: usable battery kWh and typical daily consumption, each with a confidence figure (spec §5.2).

**Files:**
- Create: `backend/src/solar_advisor/estimation/estimator.py`
- Modify: `backend/.importlinter` (add `solar_advisor.estimation` to engine's forbidden list)
- Test: `backend/tests/test_estimation.py`

- [ ] **Step 1: Add `solar_advisor.estimation` to the engine-purity contract**

In `backend/.importlinter`, under `[importlinter:contract:engine-is-pure]`, add `solar_advisor.estimation` to `forbidden_modules` so it reads:

```ini
forbidden_modules =
    solar_advisor.ingest
    solar_advisor.storage
    solar_advisor.estimation
    solar_advisor.explain
    solar_advisor.forecast
    solar_advisor.api
    aiomqtt
    sqlite3
    anthropic
```

Run: `cd backend && .venv/bin/lint-imports --config .importlinter`
Expected: `Contracts: 1 kept, 0 broken.`

- [ ] **Step 2: Write the failing test**

```python
# tests/test_estimation.py
from datetime import datetime, timedelta

from solar_advisor.estimation.estimator import EstimatedParameters, ParameterEstimator
from solar_advisor.storage.sqlite_store import SqliteTelemetryStore
from tests.conftest import make_telemetry


def _store_with_discharge_cycle(tmp_path):
    """A clean discharge run: SOC 90 -> 40 while battery_energy_out rises 100 -> 107.5
    (=> usable capacity 7.5 / 0.5 = 15 kWh) and load_energy rises 200 -> 224 over 2 days
    (=> 12 kWh/day)."""
    store = SqliteTelemetryStore(tmp_path / "e.db", min_interval=timedelta(0))
    base = datetime(2026, 6, 20, 0, 0, 0)
    rows = [
        (0, 90.0, 100.0, 200.0),
        (24, 65.0, 103.75, 212.0),
        (48, 40.0, 107.5, 224.0),
    ]
    for hours, soc, eout, lenergy in rows:
        store.save(make_telemetry(
            base + timedelta(hours=hours),
            battery_soc=soc, battery_energy_out=eout, load_energy=lenergy,
        ))
    return store, base


def test_estimates_usable_capacity_from_discharge_run(tmp_path):
    store, base = _store_with_discharge_cycle(tmp_path)
    est = ParameterEstimator(store, nominal_kwh=15.0)
    result = est.estimate(base, base + timedelta(hours=48))
    assert isinstance(result, EstimatedParameters)
    assert result.usable_kwh == 15.0  # 7.5 kWh out across a 50% SOC drop
    assert 0.0 < result.usable_kwh_confidence <= 1.0


def test_estimates_daily_consumption_from_load_energy(tmp_path):
    store, base = _store_with_discharge_cycle(tmp_path)
    est = ParameterEstimator(store, nominal_kwh=15.0)
    result = est.estimate(base, base + timedelta(hours=48))
    assert result.daily_consumption_kwh == 12.0  # 24 kWh over 2 days


def test_falls_back_to_nominal_without_discharge_data(tmp_path):
    store = SqliteTelemetryStore(tmp_path / "f.db", min_interval=timedelta(0))
    base = datetime(2026, 6, 20, 0, 0, 0)
    store.save(make_telemetry(base, battery_soc=50.0, battery_energy_out=10.0, load_energy=5.0))
    est = ParameterEstimator(store, nominal_kwh=15.0)
    result = est.estimate(base, base + timedelta(hours=1))
    assert result.usable_kwh == 15.0  # nominal fallback
    assert result.usable_kwh_confidence == 0.0  # no observed discharge span
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_estimation.py -v`
Expected: FAIL with `ModuleNotFoundError: solar_advisor.estimation.estimator`.

- [ ] **Step 4: Write the implementation**

```python
# src/solar_advisor/estimation/estimator.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from solar_advisor.storage.store import TelemetryStore


@dataclass(frozen=True, slots=True)
class EstimatedParameters:
    usable_kwh: float
    usable_kwh_confidence: float  # 0..1
    daily_consumption_kwh: float
    daily_consumption_confidence: float  # 0..1


class ParameterEstimator:
    """Derives values the inverter doesn't report from stored telemetry history.
    I/O lives here, outside the pure engine; results are passed to the engine as
    plain inputs (spec §5.2)."""

    def __init__(self, store: TelemetryStore, nominal_kwh: float) -> None:
        self._store = store
        self._nominal_kwh = nominal_kwh

    def estimate(self, start: datetime, end: datetime) -> EstimatedParameters:
        rows = self._store.query_range(start, end)
        usable_kwh, usable_conf = self._estimate_capacity(rows)
        daily_kwh, daily_conf = self._estimate_daily_consumption(rows)
        return EstimatedParameters(
            usable_kwh=usable_kwh,
            usable_kwh_confidence=usable_conf,
            daily_consumption_kwh=daily_kwh,
            daily_consumption_confidence=daily_conf,
        )

    def _estimate_capacity(self, rows: list) -> tuple[float, float]:
        """Capacity = battery_energy_out over a falling-SOC run / fractional SOC drop.
        Scans for the largest SOC span and uses the energy_out delta across it."""
        if len(rows) < 2:
            return self._nominal_kwh, 0.0
        soc_hi = max(rows, key=lambda r: r.battery_soc)
        soc_lo = min(rows, key=lambda r: r.battery_soc)
        soc_span = soc_hi.battery_soc - soc_lo.battery_soc
        energy_out = soc_lo.battery_energy_out - soc_hi.battery_energy_out
        if soc_span <= 0 or energy_out <= 0:
            return self._nominal_kwh, 0.0
        usable_kwh = energy_out / (soc_span / 100.0)
        confidence = min(1.0, soc_span / 80.0)  # an ~80% swing => full confidence
        return usable_kwh, confidence

    def _estimate_daily_consumption(self, rows: list) -> tuple[float, float]:
        """Daily kWh = load_energy delta normalised to a per-day rate."""
        if len(rows) < 2:
            return 0.0, 0.0
        first, last = rows[0], rows[-1]
        days = (last.ts - first.ts).total_seconds() / 86400.0
        if days <= 0:
            return 0.0, 0.0
        daily_kwh = (last.load_energy - first.load_energy) / days
        confidence = min(1.0, days / 7.0)  # a week of data => full confidence
        return daily_kwh, confidence
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_estimation.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Run the full suite and commit**

Run: `cd backend && make check`
Expected: ruff clean, mypy strict clean, `Contracts: 1 kept, 0 broken.`, all tests PASS.

```bash
git add backend/.importlinter backend/src/solar_advisor/estimation/estimator.py backend/tests/test_estimation.py
git commit -m "feat(estimation): usable-kWh and daily-consumption estimator from stored telemetry"
```

---

## Definition of done (Plan B)

- `make check` green: ruff, `mypy --strict`, import-linter (`engine` forbidden from importing storage/estimation/forecast/ingest/explain/api/aiomqtt/sqlite3/anthropic), all tests pass.
- The engine is pure and fully unit-tested: flat tariff, battery model, objective policy, schedule evaluator (day simulation), recommender.
- The slider behaves monotonically: sweeping the objective scalar produces non-decreasing reserve SOC and non-decreasing expected cost.
- The estimator reads `TelemetryStore` and produces usable-kWh and daily-consumption with confidence, falling back to nominal when data is insufficient.

**Next:** Plan C — Interface (LLM explain layer + provenance guard, FastAPI, Vue dashboard with the slider and history charts). Written when Plan B is complete.

---

## Self-review notes

- **Spec coverage:** §6 flat tariff (Task 2), §5 battery (Task 3) + schedule evaluator (Task 5) + recommender (Task 6), §5.3 objective scalar (Task 4) wired through Task 6, §5.4 grid-charge-is-pure-cost trade-off (encoded in recommender + evaluator), §5.2 estimation (Task 8), §9 forecast interface (Task 7). §8 engine-purity boundary extended to forbid `estimation` (Task 8 Step 1).
- **Type consistency:** `BatteryModel`, `FlatRateTariff`, `SolarForecast`, `LoadProfile`, `DaylightWindow` are defined once (Tasks 1–3) and imported unchanged by Tasks 5–6. `recommend(...)` is keyword-only and its arg names match the Task 6 tests. `assess_schedule(...)` positional order matches its tests. `SlotBehavior` enum values are referenced identically across evaluator and tests. Estimator consumes the Plan A `Telemetry` fields (`battery_soc`, `battery_energy_out`, `load_energy`, `ts`) and the `tests/conftest.py::make_telemetry` factory from Plan A.
- **No placeholders:** every code step is complete and runnable; every command has expected output.
- **Purity:** engine modules import only `dataclasses`/`enum`/`typing` and sibling engine modules + `solar_advisor.domain` (allowed). `estimation` imports `storage` (allowed; it is not the engine). `forecast` imports `engine.inputs` (allowed). The contract is updated so a future engine→estimation import fails CI.
```
