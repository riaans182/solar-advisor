# Plan P — Accurate Grid-Charge Power (backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cap grid-charging estimates at the inverter's real grid-charge power (~71 A ≈ 3.6 kW) rather than the full battery charge power (~8 kW), so per-slot grid import / cost / `daily_saving` are accurate. Solar charging still uses the full charge power.

**Architecture:** `BatteryModel` gains an optional `max_grid_charge_power_w` (0 → fall back to `max_charge_power_w`). `assess_schedule` uses it for the per-slot **grid**-charge cap only. A config value (`SA_MAX_GRID_CHARGE_POWER_W`, default 3640 W) feeds it through the service.

**Tech Stack:** Python 3.12, pytest, ruff, mypy --strict, import-linter.

**Reference (read first):** the design note in spec `docs/superpowers/specs/2026-06-26-inverter-settings-and-forecast-design.md` §5. Files: `engine/battery.py` (`BatteryModel`), `engine/schedule_eval.py` (`assess_schedule` — the grid-charge cap block), `config.py` (`AppConfig`, `load_config`), `services/recommendation.py` (builds `BatteryModel` in `build()`), `docker-compose.yml`. **From `backend/`: `make install`, then `.venv/bin/pytest`, `.venv/bin/ruff`, `.venv/bin/mypy`, `.venv/bin/lint-imports --config .importlinter`.**

---

## File Structure

| File | Change |
|------|--------|
| `src/solar_advisor/engine/battery.py` | `BatteryModel` += `max_grid_charge_power_w: float = 0.0`. |
| `src/solar_advisor/engine/schedule_eval.py` | grid-charge cap uses the grid-charge power (fallback to max charge). |
| `src/solar_advisor/config.py` | `AppConfig` += `max_grid_charge_power_w` (default 0.0); `load_config` env `SA_MAX_GRID_CHARGE_POWER_W` (default 3640). |
| `src/solar_advisor/services/recommendation.py` | pass `max_grid_charge_power_w` into `BatteryModel`. |
| `docker-compose.yml` | pass `SA_MAX_GRID_CHARGE_POWER_W` to `api`. |
| tests | `test_engine_schedule_eval.py`, `test_config.py`. |

---

## Group 1 — Engine + config + wiring

### Task 1: Grid-charge power in the model + evaluator

**Files:** Modify `engine/battery.py`, `engine/schedule_eval.py`; Test `tests/test_engine_schedule_eval.py`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_engine_schedule_eval.py`; mirror how that file builds `BatteryModel`/`Slot`/`SolarForecast`/`LoadProfile`/`DaylightWindow`/`FlatRateTariff` — read it first). The test: a night slot flagged grid-charge, battery below target, where the **grid-charge power** limits how much is imported in the slot. With a low grid-charge power the slot imports less than it would at the full charge power:
```python
def test_grid_charge_is_capped_by_grid_charge_power_not_max_charge():
    from datetime import time

    from solar_advisor.domain.schedule import Slot
    from solar_advisor.engine.battery import BatteryModel
    from solar_advisor.engine.inputs import DaylightWindow, LoadProfile, SolarForecast
    from solar_advisor.engine.schedule_eval import assess_schedule
    from solar_advisor.engine.tariff import FlatRateTariff

    # One 2-hour night slot (no daylight overlap), grid-charge on, target 100%.
    slot = Slot(start=time(1, 0), end=time(3, 0), target_soc=100, grid_charge=True, gen_charge=False)
    forecast = SolarForecast(expected_pv_kwh_today=0.0, expected_pv_kwh_tomorrow=0.0)
    load = LoadProfile(daily_kwh=0.0, essential_power_w=1000.0)  # no load deficit, isolate grid charge
    daylight = DaylightWindow(dawn=time(7, 0), dusk=time(17, 30))

    def grid_import(grid_power_w: float) -> float:
        battery = BatteryModel(
            usable_kwh=15.0,
            soc_floor_pct=20.0,
            max_charge_power_w=8000.0,
            max_discharge_power_w=8000.0,
            max_grid_charge_power_w=grid_power_w,
        )
        # start at 50% -> needs 7.5 kWh to reach 100%, but the slot is only 2h.
        out = assess_schedule(
            [slot], battery, FlatRateTariff(3.5, 600.0), forecast, load, daylight,
            start_soc=50.0, month_to_date_import_kwh=0.0,
        )
        return out[0].grid_import_kwh

    # At 3.6 kW over 2h the slot can import at most ~7.2 kWh; at 8 kW it could do the full 7.5.
    capped = grid_import(3600.0)
    full = grid_import(8000.0)
    assert round(capped, 2) == round(3600.0 / 1000.0 * 2.0, 2)  # 7.2 kWh, power-limited
    assert full > capped  # full charge power imports more in the same slot


def test_grid_charge_power_zero_falls_back_to_max_charge():
    from datetime import time

    from solar_advisor.domain.schedule import Slot
    from solar_advisor.engine.battery import BatteryModel
    from solar_advisor.engine.inputs import DaylightWindow, LoadProfile, SolarForecast
    from solar_advisor.engine.schedule_eval import assess_schedule
    from solar_advisor.engine.tariff import FlatRateTariff

    slot = Slot(start=time(1, 0), end=time(3, 0), target_soc=100, grid_charge=True, gen_charge=False)
    forecast = SolarForecast(0.0, 0.0)
    load = LoadProfile(daily_kwh=0.0, essential_power_w=1000.0)
    daylight = DaylightWindow(dawn=time(7, 0), dusk=time(17, 30))

    def grid_import(model: BatteryModel) -> float:
        return assess_schedule(
            [slot], model, FlatRateTariff(3.5, 600.0), forecast, load, daylight,
            start_soc=50.0, month_to_date_import_kwh=0.0,
        )[0].grid_import_kwh

    base = dict(usable_kwh=15.0, soc_floor_pct=20.0, max_charge_power_w=2000.0, max_discharge_power_w=8000.0)
    # 0.0 grid power must behave exactly like using max_charge_power_w (2 kW).
    assert grid_import(BatteryModel(**base, max_grid_charge_power_w=0.0)) == grid_import(
        BatteryModel(**base, max_grid_charge_power_w=2000.0)
    )
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_engine_schedule_eval.py -k grid_charge_power -v`
Expected: FAIL — `BatteryModel` has no `max_grid_charge_power_w`.

- [ ] **Step 3: Implement.**

In `engine/battery.py`, add a field (after `max_discharge_power_w`):
```python
    max_discharge_power_w: float
    max_grid_charge_power_w: float = 0.0  # 0 => use max_charge_power_w (grid charge ≤ solar charge)
```

In `engine/schedule_eval.py`, in the grid-charge block, replace:
```python
            max_charge_kwh = battery.max_charge_power_w / 1000.0 * hours
```
with:
```python
            grid_charge_power_w = battery.max_grid_charge_power_w or battery.max_charge_power_w
            max_charge_kwh = grid_charge_power_w / 1000.0 * hours
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_engine_schedule_eval.py -k grid_charge_power -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/solar_advisor/engine/battery.py src/solar_advisor/engine/schedule_eval.py tests/test_engine_schedule_eval.py
git commit -m "feat: cap grid-charging at a dedicated grid-charge power (fallback to max charge)"
```

### Task 2: Config + service wiring + compose

**Files:** Modify `config.py`, `services/recommendation.py`, `docker-compose.yml`; Test `tests/test_config.py`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_config.py`):
```python
def test_max_grid_charge_power_default(monkeypatch):
    monkeypatch.delenv("SA_MAX_GRID_CHARGE_POWER_W", raising=False)
    from solar_advisor.config import load_config

    assert load_config().max_grid_charge_power_w == 3640.0


def test_max_grid_charge_power_from_env(monkeypatch):
    monkeypatch.setenv("SA_MAX_GRID_CHARGE_POWER_W", "3000")
    from solar_advisor.config import load_config

    assert load_config().max_grid_charge_power_w == 3000.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py -k max_grid_charge -v`
Expected: FAIL — field missing.

- [ ] **Step 3: Implement.**

In `config.py` `AppConfig`, add a defaulted field (in the defaulted block, e.g. after `forecast_ttl_s`/`pv_arrays` or wherever defaulted power-ish fields sit — anywhere in the `= default` block is fine):
```python
    max_grid_charge_power_w: float = 0.0  # W cap for grid->battery charging; 0 => engine uses max_charge
```
In `load_config()`'s returned `AppConfig(...)`, add:
```python
        max_grid_charge_power_w=float(os.environ.get("SA_MAX_GRID_CHARGE_POWER_W", "3640")),
```

In `services/recommendation.py` `build()`, pass it into the `BatteryModel(...)` construction:
```python
        battery = BatteryModel(
            usable_kwh=usable_kwh,
            soc_floor_pct=cfg.battery_soc_floor_pct,
            max_charge_power_w=cfg.max_charge_power_w,
            max_discharge_power_w=cfg.max_discharge_power_w,
            max_grid_charge_power_w=cfg.max_grid_charge_power_w,
        )
```

In `docker-compose.yml`, under the `api` service `environment:` block, add:
```yaml
      SA_MAX_GRID_CHARGE_POWER_W: ${SA_MAX_GRID_CHARGE_POWER_W:-3640}
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py -k max_grid_charge -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/solar_advisor/config.py src/solar_advisor/services/recommendation.py docker-compose.yml tests/test_config.py
git commit -m "feat: configure grid-charge power (SA_MAX_GRID_CHARGE_POWER_W, default 3640) and wire it"
```

---

## Group 2 — Full gate

### Task 3: Gate + final review

- [ ] **Step 1:** `.venv/bin/pytest -q` — all green. (Existing `BatteryModel(...)` constructions omit the new field → default 0.0 → engine falls back to `max_charge_power_w`, so prior behavior/tests are unchanged.)
- [ ] **Step 2:** `.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy && .venv/bin/lint-imports --config .importlinter` — all clean. Engine purity holds (only `engine/`+`domain` touched in the engine).
- [ ] **Step 3:** Fix anything; re-run until clean.
- [ ] **Step 4:** Commit fixes: `git add -A && git commit -m "chore: satisfy gates for grid-charge power"`.

---

## Self-Review

**Spec coverage:** dedicated grid-charge power capping the per-slot grid charge (engine) → Task 1; config + wiring + compose → Task 2. Solar charging still uses `max_charge_power_w` (only the grid-charge branch changed). The `daily_saving`/costs now reflect the real grid-charge rate. ✓

**Placeholder scan:** the engine test mirrors the file's existing construction idioms; all production code is complete.

**Type consistency:** `BatteryModel.max_grid_charge_power_w: float = 0.0` ← `cfg.max_grid_charge_power_w` (service) ← `SA_MAX_GRID_CHARGE_POWER_W` (config, default 3640); `assess_schedule` reads `battery.max_grid_charge_power_w or battery.max_charge_power_w`; default 0.0 preserves existing behavior for all current `BatteryModel(...)` call sites. ✓
