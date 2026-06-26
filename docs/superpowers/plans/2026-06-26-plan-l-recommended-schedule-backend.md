# Plan L — Recommended Schedule & Forward Month Figure (backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute a recommended 6-slot schedule (what the inverter *should* be set to), expose it + the current-vs-recommended daily cost on the dashboard, and replace the broken prepaid projection with a forward "more to finish the month" figure.

**Architecture:** A pure `recommend_schedule` projects the existing reserve/grid-charge policy onto the inverter's slot grid (daytime → fill from solar, no grid-charge; night → hold reserve, grid-charge only if backup needs it). The service assesses both the current and recommended schedules, exposing both costs + the saving. The month figure becomes `expected_daily_grid_import_kwh × days_remaining × rate` (no dependency on the restart-resettable month-to-date counter).

**Tech Stack:** Python 3.12, FastAPI + Pydantic v2, pytest, ruff, mypy --strict, import-linter.

**Reference (read first):** spec `docs/superpowers/specs/2026-06-26-actionable-recommendation-design.md`. Files: `engine/schedule_eval.py` (`assess_schedule`, `SlotAssessment`, `_overlap_hours`), `engine/objective.py` (`reserve_target_soc`), `engine/optimize.py` (`recommend`, `Recommendation`), `domain/schedule.py` (`Slot(start,end,target_soc:int,grid_charge,gen_charge)`), `services/recommendation.py` (`DashboardData`, `build`), `api/schemas.py` (`DashboardView`, `SlotView`), `api/app.py` (`_to_view`). **From `backend/`: `make install`, then `.venv/bin/pytest`, `.venv/bin/ruff`, `.venv/bin/mypy`, `.venv/bin/lint-imports --config .importlinter`.**

---

## File Structure

| File | Change |
|------|--------|
| `src/solar_advisor/engine/recommend_schedule.py` (create) | pure `recommend_schedule(...)`. |
| `src/solar_advisor/services/recommendation.py` | build recommended schedule, assess both, costs; replace month projection with `month_remaining_cost`. |
| `src/solar_advisor/api/schemas.py` | `DashboardView` += `recommended_slots`, `current_daily_cost`, `recommended_daily_cost`, `daily_saving`, `month_remaining_cost`; drop `month_projected_cost`, `month_balance`. |
| `src/solar_advisor/api/app.py` | `_to_view` maps the new fields. |
| tests | `test_recommend_schedule.py` (new), `test_recommendation_service.py`, `test_api.py`, `test_explain_context.py` (fixture). |

---

## Group 1 — Engine: `recommend_schedule`

### Task 1: pure recommended-schedule policy

**Files:** Create `src/solar_advisor/engine/recommend_schedule.py`; Test `tests/test_recommend_schedule.py`.

- [ ] **Step 1: Write the failing test** `tests/test_recommend_schedule.py`:
```python
# tests/test_recommend_schedule.py
from datetime import time

from solar_advisor.domain.schedule import Slot
from solar_advisor.engine.inputs import DaylightWindow
from solar_advisor.engine.recommend_schedule import recommend_schedule

DAYLIGHT = DaylightWindow(dawn=time(7, 0), dusk=time(17, 30))


def _slot(start, end, target, grid):
    return Slot(start=time(start, 0), end=time(end, 0), target_soc=target, grid_charge=grid, gen_charge=False)


def test_daytime_slots_fill_from_solar_no_grid_charge():
    # A midday slot (10:00-16:00) overlaps daylight -> target 100, grid_charge off.
    rec = recommend_schedule(
        [_slot(10, 16, 65, True)], reserve_soc=60, grid_charge_needed=False, daylight=DAYLIGHT
    )
    assert rec[0].target_soc == 100
    assert rec[0].grid_charge is False


def test_night_slots_hold_reserve_no_charge_when_not_needed():
    # A night slot (21:00-05:00 wraps midnight) -> target = reserve, grid off when not needed.
    rec = recommend_schedule(
        [_slot(21, 5, 95, True)], reserve_soc=60, grid_charge_needed=False, daylight=DAYLIGHT
    )
    assert rec[0].target_soc == 60
    assert rec[0].grid_charge is False


def test_night_slots_grid_charge_only_when_needed():
    rec = recommend_schedule(
        [_slot(21, 5, 95, False)], reserve_soc=60, grid_charge_needed=True, daylight=DAYLIGHT
    )
    assert rec[0].grid_charge is True
    assert rec[0].target_soc == 60


def test_preserves_time_points_and_gen_charge():
    src = [Slot(start=time(0, 0), end=time(5, 0), target_soc=65, grid_charge=True, gen_charge=True)]
    rec = recommend_schedule(src, reserve_soc=60, grid_charge_needed=False, daylight=DAYLIGHT)
    assert rec[0].start == time(0, 0)
    assert rec[0].end == time(5, 0)
    assert rec[0].gen_charge is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_recommend_schedule.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement** `src/solar_advisor/engine/recommend_schedule.py`:
```python
# src/solar_advisor/engine/recommend_schedule.py
from __future__ import annotations

from solar_advisor.domain.schedule import Slot
from solar_advisor.engine.inputs import DaylightWindow
from solar_advisor.engine.schedule_eval import _overlap_hours


def recommend_schedule(
    current: list[Slot],
    *,
    reserve_soc: int,
    grid_charge_needed: bool,
    daylight: DaylightWindow,
) -> list[Slot]:
    """Project the flat-tariff reserve policy onto the inverter's slot grid.

    Grid-charging is pure cost on a flat tariff with no cheap window, so it is off
    everywhere unless the day's energy balance can't hold the resilience reserve
    (``grid_charge_needed``), in which case the night slots top up to the reserve.
    Daytime slots target 100% so solar fills the battery without curtailment; night
    slots target the reserve so the battery may discharge to it serving load. Time
    points and the (unmodelled) gen-charge flag are preserved from the current
    schedule — only target SOC and grid-charge are advised."""

    out: list[Slot] = []
    for s in current:
        if _overlap_hours(s, daylight) > 0:
            out.append(
                Slot(
                    start=s.start,
                    end=s.end,
                    target_soc=100,
                    grid_charge=False,
                    gen_charge=s.gen_charge,
                )
            )
        else:
            out.append(
                Slot(
                    start=s.start,
                    end=s.end,
                    target_soc=reserve_soc,
                    grid_charge=grid_charge_needed,
                    gen_charge=s.gen_charge,
                )
            )
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_recommend_schedule.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/solar_advisor/engine/recommend_schedule.py tests/test_recommend_schedule.py
git commit -m "feat: add recommend_schedule (flat-tariff reserve policy on the slot grid)"
```

---

## Group 2 — Service + schema + view

### Task 2: Service — assess both schedules, costs, forward month figure

**Files:** Modify `src/solar_advisor/services/recommendation.py`; Test `tests/test_recommendation_service.py`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_recommendation_service.py`; reuses helpers). Replace the existing `test_month_projection_*` tests (they assert the now-removed `month_projected_cost`/`month_balance`) with the forward-figure version, and add the schedule-diff test:
```python
def test_recommended_schedule_and_costs_present():
    svc = RecommendationService(
        config=_config(), estimator=_FakeEstimator(), forecast=_FakeForecast()
    )
    data = svc.build(_live_state(), objective=0.5)
    assert len(data.recommended_assessments) == len(data.slot_assessments)
    assert isinstance(data.current_daily_cost, float)
    assert isinstance(data.recommended_daily_cost, float)
    assert round(data.daily_saving, 2) == round(
        data.current_daily_cost - data.recommended_daily_cost, 2
    )


def test_forward_month_figure_uses_daily_import_not_mtd():
    # _live_state(): ts day 22, June (30 days) -> days_remaining = 30-22+1 = 9.
    svc = RecommendationService(
        config=_config(), estimator=_FakeEstimator(), forecast=_FakeForecast()
    )
    data = svc.build(_live_state(), objective=0.5)
    days_remaining = 30 - 22 + 1
    expected = data.recommendation.expected_daily_grid_import_kwh * days_remaining * data.tariff_rate
    assert round(data.month_remaining_cost, 2) == round(expected, 2)
```
Delete the old `test_month_projection_energy_only` and `test_month_projection_zero_without_reader` tests (the fields they assert are gone). Keep `test_month_projection`-style spend coverage only if it asserts `month_spend` (which remains) — adapt: if those tests assert `month_spend`, keep that assertion and drop the projected/balance lines.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_recommendation_service.py -k "recommended_schedule or forward_month" -v`
Expected: FAIL.

- [ ] **Step 3: Edit `services/recommendation.py`.**

Add the import (with the other engine imports):
```python
from solar_advisor.engine.recommend_schedule import recommend_schedule
```

In `DashboardData`, replace the `month_projected_cost`/`month_balance` fields with the new set. The block currently reads:
```python
    month_spend: float
    month_projected_cost: float
    month_balance: float
    disclaimer: str
```
Change it to:
```python
    month_spend: float
    month_remaining_cost: float
    recommended_assessments: list[SlotAssessment]
    current_daily_cost: float
    recommended_daily_cost: float
    daily_saving: float
    disclaimer: str
```

In `build()`, after the existing `assessments = assess_schedule(...)` and `rec = recommend(...)`, add the recommended-schedule assessment + costs:
```python
        recommended = recommend_schedule(
            state.schedule,
            reserve_soc=round(rec.reserve_target_soc),
            grid_charge_needed=rec.enable_overnight_grid_charge,
            daylight=daylight,
        )
        recommended_assessments = assess_schedule(
            recommended,
            battery,
            tariff,
            forecast,
            load,
            daylight,
            start_soc=telemetry.battery_soc,
            month_to_date_import_kwh=telemetry.month_to_date_grid_import_kwh,
        )
        current_daily_cost = sum(a.cost for a in assessments)
        recommended_daily_cost = sum(a.cost for a in recommended_assessments)
        daily_saving = current_daily_cost - recommended_daily_cost
```

Replace the month projection block. It currently reads:
```python
        today = telemetry.ts.date()
        first_of_month = today.replace(day=1)
        month_spend = (
            sum(
                p.rand
                for p in self._purchases.list_since(first_of_month)
                if p.purchased_at.year == today.year and p.purchased_at.month == today.month
            )
            if self._purchases is not None
            else 0.0
        )
        month_projected_cost = (
            telemetry.month_to_date_grid_import_kwh / today.day * days_in_month * derived.rate
        )
        month_balance = month_spend - month_projected_cost
```
Change the last two statements to the forward figure (keep `month_spend` as-is):
```python
        days_remaining = days_in_month - today.day + 1
        month_remaining_cost = (
            rec.expected_daily_grid_import_kwh * days_remaining * derived.rate
        )
```

Update the returned `DashboardData(...)`: replace `month_projected_cost=...,` and `month_balance=...,` with:
```python
            month_spend=month_spend,
            month_remaining_cost=month_remaining_cost,
            recommended_assessments=recommended_assessments,
            current_daily_cost=current_daily_cost,
            recommended_daily_cost=recommended_daily_cost,
            daily_saving=daily_saving,
```

- [ ] **Step 4: Run the full service test file**

Run: `.venv/bin/pytest tests/test_recommendation_service.py -v`
Expected: PASS (after deleting/adapting the old month-projection tests per Step 1).

- [ ] **Step 5: Commit**

```bash
git add src/solar_advisor/services/recommendation.py tests/test_recommendation_service.py
git commit -m "feat: assess recommended schedule + costs; forward month-remaining figure"
```

### Task 3: Schema + `_to_view`

**Files:** Modify `src/solar_advisor/api/schemas.py`, `src/solar_advisor/api/app.py`; Test `tests/test_api.py`.

- [ ] **Step 1: Write the failing test** (replace the existing `test_dashboard_view_includes_month_projection_fields` in `tests/test_api.py` with):
```python
def test_dashboard_view_includes_schedule_diff_and_month_remaining():
    body = _client(_ready_state()).get("/api/dashboard?objective=0.5").json()
    assert "recommended_slots" in body
    assert len(body["recommended_slots"]) == len(body["slots"])
    assert "current_daily_cost" in body
    assert "recommended_daily_cost" in body
    assert "daily_saving" in body
    assert "month_remaining_cost" in body
    assert "month_projected_cost" not in body  # removed
    assert "month_balance" not in body  # removed
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_api.py -k schedule_diff -v`
Expected: FAIL.

- [ ] **Step 3: Edit `api/schemas.py`.** In `DashboardView`, replace the `month_spend`/`month_projected_cost`/`month_balance` lines with:
```python
    month_spend: float
    month_remaining_cost: float
    recommended_slots: list[SlotView]
    current_daily_cost: float
    recommended_daily_cost: float
    daily_saving: float
```

- [ ] **Step 4: Edit `api/app.py` `_to_view`.** There is an existing local that builds the current `slots=[SlotView(...) for a in data.slot_assessments]`. Factor the SlotView mapping into a small helper above `_to_view` so both current and recommended use it:
```python
def _slot_view(a: SlotAssessment) -> SlotView:
    return SlotView(
        start=a.slot.start.isoformat(timespec="minutes"),
        end=a.slot.end.isoformat(timespec="minutes"),
        target_soc=a.slot.target_soc,
        grid_charge=a.slot.grid_charge,
        behavior=a.behavior.value,
        end_soc=round(a.end_soc, 1),
        grid_import_kwh=round(a.grid_import_kwh, 2),
        cost=round(a.cost, 2),
    )
```
(Add `from solar_advisor.engine.schedule_eval import SlotAssessment` to the imports.) Change the `slots=[...]` builder in `_to_view` to `slots=[_slot_view(a) for a in data.slot_assessments]`, and replace the `month_spend`/`month_projected_cost`/`month_balance` mapping lines with:
```python
        month_spend=round(data.month_spend),
        month_remaining_cost=round(data.month_remaining_cost),
        recommended_slots=[_slot_view(a) for a in data.recommended_assessments],
        current_daily_cost=round(data.current_daily_cost, 2),
        recommended_daily_cost=round(data.recommended_daily_cost, 2),
        daily_saving=round(data.daily_saving, 2),
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_api.py -k schedule_diff -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/solar_advisor/api/schemas.py src/solar_advisor/api/app.py tests/test_api.py
git commit -m "feat: expose recommended schedule, costs and month-remaining on /api/dashboard"
```

---

## Group 3 — Full gate

### Task 4: Gate

- [ ] **Step 1:** `.venv/bin/pytest -q` — all green. The removed `DashboardData` fields break the `tests/test_explain_context.py` fixture — update its `DashboardData(...)` construction: drop `month_projected_cost=...`/`month_balance=...`, add `month_remaining_cost=0.0, recommended_assessments=[], current_daily_cost=0.0, recommended_daily_cost=0.0, daily_saving=0.0` (keep `month_spend=0.0`). Fix and re-run.
- [ ] **Step 2:** `.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy && .venv/bin/lint-imports --config .importlinter` — all clean. Engine purity holds (`recommend_schedule` is in `engine/`, imports only engine + domain).
- [ ] **Step 3:** Fix anything; re-run until clean.
- [ ] **Step 4:** Commit fixes: `git add -A && git commit -m "chore: satisfy gates for recommended-schedule backend"`.

---

## Self-Review

**Spec coverage:** L1 `recommend_schedule` → Task 1; L2 dual assessment + costs + diff fields → Tasks 2–3; L3 forward month figure (no MTD dependency) → Task 2. ✓

**Placeholder scan:** none — complete code/commands.

**Type consistency:** `recommend_schedule(current, *, reserve_soc:int, grid_charge_needed:bool, daylight)` called with `round(rec.reserve_target_soc)` + `rec.enable_overnight_grid_charge`; `recommended_assessments: list[SlotAssessment]` → `recommended_slots: list[SlotView]` via `_slot_view`; `current_daily_cost`/`recommended_daily_cost`/`daily_saving`/`month_remaining_cost` flow `DashboardData` → `DashboardView` → `_to_view`; old `month_projected_cost`/`month_balance` removed everywhere (service, schema, view, explain fixture). The explain layer's `allowed_numbers` is unchanged here — broadening it to cover the new numbers is Plan M (so an LLM citing `daily_saving` would currently be withheld → the deterministic fallback in M covers UX until then). ✓
