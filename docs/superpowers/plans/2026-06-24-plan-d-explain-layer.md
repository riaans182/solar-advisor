# Plan D — LLM Explain Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the explanation/interface layer — Claude renders the deterministic engine's output as plain-English "what each slot is doing, what it costs, what to change and why," constrained by a numeric-provenance guard so it can never present a number the engine didn't compute.

**Architecture:** `explain/` consumes a `DashboardData` (from Plan C's `RecommendationService`) and builds an `ExplanationContext` of pre-computed facts. The guard whitelists exactly the numbers in those facts; after Claude replies, every number in the reply must trace to a whitelisted value (within tolerance) or the reply is **withheld** and replaced with a safe message. The LLM has no engine handle, no solver, and computes nothing — it only writes prose over provided facts. The API key is server-side only, behind a kill-switch and a rate limit.

**Tech Stack:** Python 3.12+, the Anthropic SDK (`anthropic`), FastAPI (from Plan C), `pytest`, `ruff`, `mypy --strict`, `import-linter`. Default model `claude-haiku-4-5` (config-overridable). The `engine` package stays pure — the import-linter contract already forbids it from importing `explain`/`anthropic`.

**Covers spec stages:** the LLM explanation layer (spec §§3 goal-3, 8). See `docs/superpowers/specs/2026-06-22-solar-advisor-design.md` §8 (enforced boundary, provenance guard, model, server-side key, kill-switch).

**Builds on `main`:** `services/recommendation.py` (`DashboardData`, `SlotAssessment`-backed views), `engine.schedule_eval.SlotBehavior`, `engine.optimize.Recommendation`, `config.AppConfig`, `api/app.py` (`build_app`, `app.state`, `get_state`/`get_service`).

---

## Design decisions

- **Provenance = number-set containment.** The whitelist is `extract_numbers(<the exact fact text sent to Claude>)`. Claude's reply passes iff every number it contains is within tolerance of some whitelisted number. This makes times, percentages, costs, counts — every number in the facts — automatically allowed, and anything else flagged. It is the literal encoding of "the LLM never presents a number the engine didn't produce."
- **Withhold on failure.** A reply that fails the guard is never shown; the user gets a safe fallback that points at the engine figures directly. This is the demoable, tested invariant.
- **Model:** `claude-haiku-4-5` by default (spec §8 — cost-appropriate; you chose it). Config-overridable via `SA_EXPLAIN_MODEL`. No `thinking`/`effort` params (Haiku doesn't take `effort`); a plain `messages.create` with a system prompt + a user facts block, `max_tokens=1024`.
- **Testability:** `Explainer` takes an injectable `complete: Callable[[str, str], str]` (system, user → reply text) and an injectable `now: Callable[[], float]`. Tests inject a fake completion (no network, no key); production injects an Anthropic-backed one.
- **Safety:** the LLM call is read-only and outbound to Anthropic only; it touches nothing on the inverter. Kill-switch (`SA_EXPLAIN_ENABLED=false`) returns a canned message without calling the API.

---

## File structure (created/modified by this plan)

```
backend/
├─ pyproject.toml                              # MODIFY: add anthropic
├─ Dockerfile.api / docker-compose.yml         # MODIFY: pass ANTHROPIC_API_KEY + SA_EXPLAIN_* env
├─ src/solar_advisor/
│  ├─ config.py                                 # MODIFY: explain settings
│  ├─ services/recommendation.py                # MODIFY: surface tariff_rate + forecast on DashboardData
│  ├─ explain/
│  │  ├─ context.py                             # NEW: ExplanationContext + build_context
│  │  ├─ guard.py                               # NEW: extract_numbers + check_provenance
│  │  ├─ prompt.py                              # NEW: build_messages
│  │  └─ client.py                              # NEW: Explainer + ExplanationResult + anthropic_complete
│  └─ api/
│     ├─ schemas.py                             # MODIFY: ExplanationView (+ forecast fields on DashboardView)
│     └─ app.py                                 # MODIFY: /api/explain endpoint + Explainer wiring
└─ tests/
   ├─ test_explain_context.py
   ├─ test_explain_guard.py
   ├─ test_explain_client.py
   └─ test_api_explain.py
```

`explain/__init__.py` already exists (empty, from the Plan A scaffold). Tooling: `cd backend && make check`.

---

## Task 1: Anthropic dependency + explain config

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/src/solar_advisor/config.py`
- Test: `backend/tests/test_config.py` (extend)

- [ ] **Step 1: Add the dependency**

In `pyproject.toml` `[project].dependencies`, add `"anthropic>=0.40"`. Install:
Run: `cd backend && .venv/bin/python -m pip install -e ".[dev]" && echo OK`
Expected: installs `anthropic`; prints `OK`.

- [ ] **Step 2: Write the failing config test**

Add to `backend/tests/test_config.py`:

```python
def test_explain_settings_from_env(monkeypatch):
    monkeypatch.setenv("SA_EXPLAIN_MODEL", "claude-opus-4-8")
    monkeypatch.setenv("SA_EXPLAIN_ENABLED", "false")
    monkeypatch.setenv("SA_EXPLAIN_MIN_INTERVAL_S", "30")
    cfg = load_config()
    assert cfg.explain_model == "claude-opus-4-8"
    assert cfg.explain_enabled is False
    assert cfg.explain_min_interval_s == 30.0


def test_explain_settings_defaults(monkeypatch):
    for var in ("SA_EXPLAIN_MODEL", "SA_EXPLAIN_ENABLED", "SA_EXPLAIN_MIN_INTERVAL_S"):
        monkeypatch.delenv(var, raising=False)
    cfg = load_config()
    assert cfg.explain_model == "claude-haiku-4-5"
    assert cfg.explain_enabled is True
    assert cfg.explain_min_interval_s == 10.0
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_config.py -k explain -v`
Expected: FAIL with `AttributeError: 'AppConfig' object has no attribute 'explain_model'`.

- [ ] **Step 4: Add the fields**

In `config.py`, append three fields to `AppConfig` (after `daily_consumption_kwh`, all with defaults):

```python
    explain_model: str = "claude-haiku-4-5"
    explain_enabled: bool = True
    explain_min_interval_s: float = 10.0
```

In `load_config()`, pass them:

```python
        explain_model=os.environ.get("SA_EXPLAIN_MODEL", "claude-haiku-4-5"),
        explain_enabled=os.environ.get("SA_EXPLAIN_ENABLED", "true").strip().lower() != "false",
        explain_min_interval_s=float(os.environ.get("SA_EXPLAIN_MIN_INTERVAL_S", "10")),
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_config.py -k explain -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/src/solar_advisor/config.py backend/tests/test_config.py
git commit -m "build: add anthropic dependency and explain-layer config"
```

---

## Task 2: Surface tariff rate + forecast on DashboardData

The explanation needs the tariff rate (to say "at R3.56/kWh") and the forecast (to say "based on X kWh of expected sun") — and the guard can only allow numbers that are present in the facts. Add them to `DashboardData` (and the API view, closing a Plan C deferred minor).

**Files:**
- Modify: `backend/src/solar_advisor/services/recommendation.py`
- Modify: `backend/src/solar_advisor/api/schemas.py`
- Test: `backend/tests/test_recommendation_service.py` (extend)

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_recommendation_service.py`:

```python
def test_dashboard_surfaces_tariff_and_forecast():
    svc = RecommendationService(
        config=_config(), estimator=_FakeEstimator(), forecast=_FakeForecast(),
    )
    data = svc.build(_live_state(), objective=0.5)
    assert data.tariff_rate == 3.56
    assert data.expected_pv_kwh_today == 8.0
    assert data.expected_pv_kwh_tomorrow == 8.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_recommendation_service.py -k tariff_and_forecast -v`
Expected: FAIL with `AttributeError` (no `tariff_rate` on `DashboardData`).

- [ ] **Step 3: Add the fields**

In `recommendation.py`, add three fields to the `DashboardData` dataclass (place them after `daily_consumption_confidence`, before `disclaimer`):

```python
    tariff_rate: float
    expected_pv_kwh_today: float
    expected_pv_kwh_tomorrow: float
```

In `RecommendationService.build`, populate them in the returned `DashboardData(...)` (the `forecast` and `cfg` locals are already in scope):

```python
            tariff_rate=cfg.tariff_rate,
            expected_pv_kwh_today=forecast.expected_pv_kwh_today,
            expected_pv_kwh_tomorrow=forecast.expected_pv_kwh_tomorrow,
```

- [ ] **Step 4: Add them to the API view**

In `api/schemas.py`, add to `DashboardView`:

```python
    tariff_rate: float
    expected_pv_kwh_today: float
    expected_pv_kwh_tomorrow: float
```

In `api/app.py::_to_view`, set them on the `DashboardView(...)`:

```python
        tariff_rate=data.tariff_rate,
        expected_pv_kwh_today=round(data.expected_pv_kwh_today, 2),
        expected_pv_kwh_tomorrow=round(data.expected_pv_kwh_tomorrow, 2),
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_recommendation_service.py tests/test_api.py -v`
Expected: PASS (the new test + existing service/API tests still pass).

- [ ] **Step 6: Commit**

```bash
git add backend/src/solar_advisor/services/recommendation.py backend/src/solar_advisor/api/schemas.py backend/src/solar_advisor/api/app.py backend/tests/test_recommendation_service.py
git commit -m "feat: surface tariff rate and forecast on dashboard data"
```

---

## Task 3: Explanation context

**Files:**
- Create: `backend/src/solar_advisor/explain/context.py`
- Test: `backend/tests/test_explain_context.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_explain_context.py
from datetime import UTC, datetime, time

from solar_advisor.domain.schedule import Slot
from solar_advisor.engine.optimize import Recommendation
from solar_advisor.engine.schedule_eval import SlotAssessment, SlotBehavior
from solar_advisor.explain.context import ExplanationContext, build_context
from solar_advisor.services.recommendation import ADVISORY_DISCLAIMER, DashboardData
from tests.conftest import make_telemetry


def _dashboard_data():
    slot = Slot(start=time(0, 0), end=time(5, 0), target_soc=90, grid_charge=True, gen_charge=False)
    assessment = SlotAssessment(
        slot=slot, behavior=SlotBehavior.GRID_CHARGING, end_soc=90.0,
        grid_import_kwh=13.0, cost=46.28,
    )
    rec = Recommendation(
        reserve_target_soc=100.0, enable_overnight_grid_charge=True, grid_charge_kwh=10.5,
        expected_daily_grid_import_kwh=22.5, expected_daily_cost=80.1, backup_hours=30.0,
        monthly_cost_so_far=956.0,
    )
    return DashboardData(
        telemetry=make_telemetry(datetime(2026, 6, 22, 8, 0, tzinfo=UTC), battery_soc=30.0),
        objective=0.5, slot_assessments=[assessment], recommendation=rec,
        usable_kwh=15.0, usable_kwh_confidence=0.6,
        daily_consumption_kwh=20.0, daily_consumption_confidence=0.5,
        tariff_rate=3.56, expected_pv_kwh_today=8.0, expected_pv_kwh_tomorrow=8.0,
        disclaimer=ADVISORY_DISCLAIMER,
    )


def test_build_context_carries_facts():
    ctx = build_context(_dashboard_data())
    assert isinstance(ctx, ExplanationContext)
    assert ctx.tariff_rate == 3.56
    assert ctx.objective == 0.5
    assert len(ctx.slots) == 1
    assert ctx.slots[0].behavior == "grid_charging"
    assert ctx.slots[0].cost == 46.28
    assert ctx.recommendation.expected_daily_cost == 80.1


def test_to_facts_is_text_and_includes_key_numbers():
    facts = build_context(_dashboard_data()).to_facts()
    assert isinstance(facts, str)
    # Engine numbers must appear verbatim so the guard can whitelist them.
    assert "3.56" in facts
    assert "46.28" in facts
    assert "80.1" in facts
    assert "grid_charging" in facts
    # The disclaimer travels with the facts.
    assert "read-only" in facts.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_explain_context.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
# src/solar_advisor/explain/context.py
from __future__ import annotations

from dataclasses import dataclass

from solar_advisor.services.recommendation import DashboardData


@dataclass(frozen=True, slots=True)
class SlotFact:
    start: str
    end: str
    target_soc: int
    grid_charge: bool
    behavior: str
    end_soc: float
    grid_import_kwh: float
    cost: float


@dataclass(frozen=True, slots=True)
class RecommendationFact:
    reserve_target_soc: float
    enable_overnight_grid_charge: bool
    grid_charge_kwh: float
    expected_daily_grid_import_kwh: float
    expected_daily_cost: float
    backup_hours: float
    monthly_cost_so_far: float


@dataclass(frozen=True, slots=True)
class ExplanationContext:
    """Pre-computed facts handed to the LLM. Every number here came from the
    deterministic engine or live telemetry; the LLM computes nothing (spec §8)."""

    objective: float
    battery_soc: float
    pv_power: float
    grid_power: float
    load_power: float
    month_to_date_grid_import_kwh: float
    usable_kwh: float
    usable_kwh_confidence: float
    daily_consumption_kwh: float
    daily_consumption_confidence: float
    tariff_rate: float
    expected_pv_kwh_today: float
    slots: list[SlotFact]
    recommendation: RecommendationFact
    disclaimer: str

    def to_facts(self) -> str:
        """Serialize the facts as the text block sent to the model. The guard's
        whitelist is derived from exactly this string."""
        lines = [
            "LIVE STATE:",
            f"- battery SOC: {self.battery_soc}%",
            f"- PV power: {self.pv_power} W",
            f"- grid power: {self.grid_power} W",
            f"- load power: {self.load_power} W",
            f"- month-to-date grid import: {self.month_to_date_grid_import_kwh} kWh",
            "ESTIMATES:",
            f"- usable battery capacity: {self.usable_kwh} kWh "
            f"(confidence {self.usable_kwh_confidence})",
            f"- typical daily consumption: {self.daily_consumption_kwh} kWh "
            f"(confidence {self.daily_consumption_confidence})",
            f"- expected solar today: {self.expected_pv_kwh_today} kWh",
            f"TARIFF: flat {self.tariff_rate} R/kWh (no cheap window).",
            f"OBJECTIVE (0=cost, 1=resilience): {self.objective}",
            "CURRENT SCHEDULE (per slot):",
        ]
        for i, s in enumerate(self.slots, start=1):
            lines.append(
                f"- slot {i} {s.start}-{s.end}: target SOC {s.target_soc}%, "
                f"grid-charge {'on' if s.grid_charge else 'off'}, behavior {s.behavior}, "
                f"projected end SOC {s.end_soc}%, grid import {s.grid_import_kwh} kWh, "
                f"cost R{s.cost}"
            )
        r = self.recommendation
        lines += [
            "RECOMMENDATION (engine output):",
            f"- reserve target SOC: {r.reserve_target_soc}%",
            f"- overnight grid-charge needed: {r.enable_overnight_grid_charge}",
            f"- grid-charge energy: {r.grid_charge_kwh} kWh",
            f"- expected daily grid import: {r.expected_daily_grid_import_kwh} kWh",
            f"- expected daily cost: R{r.expected_daily_cost}",
            f"- backup runtime at reserve: {r.backup_hours} hours",
            f"- month-to-date bill: R{r.monthly_cost_so_far}",
            f"DISCLAIMER: {self.disclaimer}",
        ]
        return "\n".join(lines)


def build_context(data: DashboardData) -> ExplanationContext:
    return ExplanationContext(
        objective=data.objective,
        battery_soc=data.telemetry.battery_soc,
        pv_power=data.telemetry.pv_power,
        grid_power=data.telemetry.grid_power,
        load_power=data.telemetry.load_power,
        month_to_date_grid_import_kwh=data.telemetry.month_to_date_grid_import_kwh,
        usable_kwh=round(data.usable_kwh, 2),
        usable_kwh_confidence=round(data.usable_kwh_confidence, 2),
        daily_consumption_kwh=round(data.daily_consumption_kwh, 2),
        daily_consumption_confidence=round(data.daily_consumption_confidence, 2),
        tariff_rate=data.tariff_rate,
        expected_pv_kwh_today=round(data.expected_pv_kwh_today, 2),
        slots=[
            SlotFact(
                start=a.slot.start.isoformat(timespec="minutes"),
                end=a.slot.end.isoformat(timespec="minutes"),
                target_soc=a.slot.target_soc,
                grid_charge=a.slot.grid_charge,
                behavior=a.behavior.value,
                end_soc=round(a.end_soc, 1),
                grid_import_kwh=round(a.grid_import_kwh, 2),
                cost=round(a.cost, 2),
            )
            for a in data.slot_assessments
        ],
        recommendation=RecommendationFact(
            reserve_target_soc=round(data.recommendation.reserve_target_soc, 1),
            enable_overnight_grid_charge=data.recommendation.enable_overnight_grid_charge,
            grid_charge_kwh=round(data.recommendation.grid_charge_kwh, 2),
            expected_daily_grid_import_kwh=round(
                data.recommendation.expected_daily_grid_import_kwh, 2
            ),
            expected_daily_cost=round(data.recommendation.expected_daily_cost, 2),
            backup_hours=round(data.recommendation.backup_hours, 1),
            monthly_cost_so_far=round(data.recommendation.monthly_cost_so_far, 2),
        ),
        disclaimer=data.disclaimer,
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_explain_context.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/solar_advisor/explain/context.py backend/tests/test_explain_context.py
git commit -m "feat(explain): explanation context of pre-computed engine facts"
```

---

## Task 4: Numeric-provenance guard

**Files:**
- Create: `backend/src/solar_advisor/explain/guard.py`
- Test: `backend/tests/test_explain_guard.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_explain_guard.py
from solar_advisor.explain.guard import check_provenance, extract_numbers


def test_extract_numbers_handles_currency_percent_commas():
    nums = extract_numbers("Slot 1 costs R46.28, draws 1,140 W, holds 90% over 7 hours.")
    assert 46.28 in nums
    assert 1140.0 in nums
    assert 90.0 in nums
    assert 7.0 in nums


def test_provenance_passes_when_all_numbers_traced():
    facts = "cost R46.28, reserve 100%, 13.0 kWh"
    reply = "It grid-charges to 100%, importing 13.0 kWh at a cost of R46.28."
    result = check_provenance(reply, allowed=extract_numbers(facts))
    assert result.ok is True
    assert result.unverified == []


def test_provenance_flags_a_fabricated_number():
    facts = "cost R46.28, reserve 100%"
    reply = "This will save you R512 per month."  # 512 is nowhere in the facts
    result = check_provenance(reply, allowed=extract_numbers(facts))
    assert result.ok is False
    assert 512.0 in result.unverified


def test_provenance_tolerates_rounding():
    facts = "expected daily cost R42.72"
    reply = "Roughly R42.70 a day."  # within tolerance of 42.72
    assert check_provenance(reply, allowed=extract_numbers(facts)).ok is True


def test_provenance_ignores_when_no_numbers():
    assert check_provenance("Grid-charging at night is pure cost here.", allowed=[]).ok is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_explain_guard.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
# src/solar_advisor/explain/guard.py
from __future__ import annotations

import re
from dataclasses import dataclass

# Matches integers/decimals, optionally with thousands separators. Currency/%
# symbols and units are outside the match and ignored.
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def extract_numbers(text: str) -> list[float]:
    """All numeric literals in the text, commas stripped, as floats."""
    out: list[float] = []
    for token in _NUMBER.findall(text):
        try:
            out.append(float(token.replace(",", "")))
        except ValueError:  # pragma: no cover - regex guarantees parseable
            continue
    return out


@dataclass(frozen=True, slots=True)
class ProvenanceResult:
    ok: bool
    unverified: list[float]


def _is_traced(value: float, allowed: list[float], abs_floor: float, rel: float) -> bool:
    return any(
        abs(value - w) <= max(abs_floor, rel * max(abs(value), abs(w))) for w in allowed
    )


def check_provenance(
    reply: str, allowed: list[float], *, abs_floor: float = 0.5, rel: float = 0.02
) -> ProvenanceResult:
    """Every number in the reply must trace to an allowed (engine-provided) number
    within tolerance, else it is flagged. This is the runtime form of "the LLM
    never presents a number the engine didn't compute" (spec §8)."""
    unverified = [n for n in extract_numbers(reply) if not _is_traced(n, allowed, abs_floor, rel)]
    return ProvenanceResult(ok=not unverified, unverified=unverified)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_explain_guard.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/solar_advisor/explain/guard.py backend/tests/test_explain_guard.py
git commit -m "feat(explain): numeric-provenance guard"
```

---

## Task 5: Prompt builder

**Files:**
- Create: `backend/src/solar_advisor/explain/prompt.py`
- Test: `backend/tests/test_explain_context.py` (extend — same module owns context+prompt fixtures)

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_explain_context.py`:

```python
from solar_advisor.explain.prompt import build_messages


def test_build_messages_returns_system_and_facts():
    ctx = build_context(_dashboard_data())
    system, user = build_messages(ctx)
    assert "only use numbers" in system.lower() or "do not invent" in system.lower()
    assert "advisory" in system.lower()
    # The user message is the fact block — the guard whitelists exactly this.
    assert user == ctx.to_facts()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_explain_context.py -k build_messages -v`
Expected: FAIL with `ModuleNotFoundError: solar_advisor.explain.prompt`.

- [ ] **Step 3: Write the implementation**

```python
# src/solar_advisor/explain/prompt.py
from __future__ import annotations

from solar_advisor.explain.context import ExplanationContext

_SYSTEM = (
    "You are the explanation layer of a self-hosted solar advisor. A deterministic "
    "engine has already computed every number below. Your job is ONLY to explain, in "
    "plain, friendly English, what the current battery schedule is doing, what it is "
    "likely costing, and what to change and why — for a homeowner.\n"
    "\n"
    "Hard rules:\n"
    "- Do NOT invent, compute, or estimate any number. Only use numbers that appear in "
    "the facts provided. If you want to state a figure, it must be one of the given "
    "values. Do not add, multiply, or derive new numbers.\n"
    "- This is advisory only: the app is read-only and never changes the inverter. Frame "
    "suggestions as things the user can choose to apply themselves.\n"
    "- The tariff is flat with no cheap overnight window, so grid-charging the battery is "
    "pure cost and only worth it for backup/resilience. Make that trade-off legible.\n"
    "- Be concise: a short overview, then a per-slot note where it matters, then the "
    "recommendation. Use Rand (R) for money."
)


def build_messages(ctx: ExplanationContext) -> tuple[str, str]:
    """Return (system_prompt, user_facts). The user message is exactly
    ctx.to_facts() so the guard can whitelist precisely the numbers shown to Claude."""
    return _SYSTEM, ctx.to_facts()
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_explain_context.py -v`
Expected: PASS (all context + prompt tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/solar_advisor/explain/prompt.py backend/tests/test_explain_context.py
git commit -m "feat(explain): prompt builder constraining the model to provided numbers"
```

---

## Task 6: Explainer client (kill-switch, rate limit, guard, withhold)

**Files:**
- Create: `backend/src/solar_advisor/explain/client.py`
- Test: `backend/tests/test_explain_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_explain_client.py
from solar_advisor.explain.client import Explainer, ExplanationResult
from tests.test_explain_context import _dashboard_data

WITHHELD_MARKER = "could not be verified"


def _ctx():
    from solar_advisor.explain.context import build_context

    return build_context(_dashboard_data())


def test_kill_switch_returns_canned_without_calling_model():
    calls = []

    def fake_complete(system, user):
        calls.append((system, user))
        return "should not be called"

    explainer = Explainer(complete=fake_complete, enabled=False, min_interval_s=0.0)
    result = explainer.explain(_ctx())
    assert isinstance(result, ExplanationResult)
    assert result.generated is False
    assert calls == []  # model never invoked


def test_clean_reply_passes_guard_and_is_returned():
    def fake_complete(system, user):
        # Uses only numbers present in the facts.
        return "Your battery grid-charges to 100% overnight, importing 13.0 kWh at R46.28."

    explainer = Explainer(complete=fake_complete, enabled=True, min_interval_s=0.0)
    result = explainer.explain(_ctx())
    assert result.generated is True
    assert result.guard_ok is True
    assert "46.28" in result.text


def test_fabricated_number_is_withheld():
    def fake_complete(system, user):
        return "You will save R512 every month by switching this off."  # 512 not in facts

    explainer = Explainer(complete=fake_complete, enabled=True, min_interval_s=0.0)
    result = explainer.explain(_ctx())
    assert result.generated is True
    assert result.guard_ok is False
    assert 512.0 in result.unverified
    assert WITHHELD_MARKER in result.text.lower()
    assert "512" not in result.text  # the hallucinating reply is not shown


def test_rate_limit_blocks_second_call_within_interval():
    clock = [100.0]

    def fake_complete(system, user):
        return "Grid-charging at night is pure cost here."  # no numbers

    explainer = Explainer(
        complete=fake_complete, enabled=True, min_interval_s=10.0, now=lambda: clock[0]
    )
    first = explainer.explain(_ctx())
    assert first.generated is True
    clock[0] = 105.0  # 5s later, inside the 10s window
    second = explainer.explain(_ctx())
    assert second.generated is False
    assert "too frequently" in second.text.lower() or "rate" in second.text.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_explain_client.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
# src/solar_advisor/explain/client.py
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from solar_advisor.explain.context import ExplanationContext
from solar_advisor.explain.guard import check_provenance, extract_numbers
from solar_advisor.explain.prompt import build_messages

CompleteFn = Callable[[str, str], str]

_DISABLED_MESSAGE = (
    "AI explanations are turned off. The figures above come straight from the "
    "deterministic engine."
)
_RATE_LIMITED_MESSAGE = (
    "Explanations are being requested too frequently — please wait a moment. The "
    "engine figures above are current."
)
_WITHHELD_MESSAGE = (
    "An explanation was generated but could not be verified against the engine's "
    "numbers, so it was withheld. Read the engine figures above directly."
)


@dataclass(frozen=True, slots=True)
class ExplanationResult:
    text: str
    generated: bool  # True iff the model was actually called
    guard_ok: bool
    unverified: list[float] = field(default_factory=list)


class Explainer:
    """Calls the LLM to render the engine's facts as prose, behind a kill-switch
    and a rate limit, and enforces numeric provenance: a reply that cites a number
    not in the facts is withheld (spec §8)."""

    def __init__(
        self,
        complete: CompleteFn,
        *,
        enabled: bool = True,
        min_interval_s: float = 10.0,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._complete = complete
        self._enabled = enabled
        self._min_interval_s = min_interval_s
        self._now = now
        self._last_call: float | None = None

    def explain(self, ctx: ExplanationContext) -> ExplanationResult:
        if not self._enabled:
            return ExplanationResult(text=_DISABLED_MESSAGE, generated=False, guard_ok=True)

        now = self._now()
        if self._last_call is not None and (now - self._last_call) < self._min_interval_s:
            return ExplanationResult(text=_RATE_LIMITED_MESSAGE, generated=False, guard_ok=True)
        self._last_call = now

        system, user = build_messages(ctx)
        reply = self._complete(system, user)
        result = check_provenance(reply, allowed=extract_numbers(user))
        if not result.ok:
            return ExplanationResult(
                text=_WITHHELD_MESSAGE, generated=True, guard_ok=False,
                unverified=result.unverified,
            )
        return ExplanationResult(text=reply, generated=True, guard_ok=True)


def anthropic_complete(model: str, max_tokens: int = 1024) -> CompleteFn:
    """Production completion: the Anthropic SDK with a server-side key
    (ANTHROPIC_API_KEY). Imported lazily so tests never need the SDK or a key."""
    import anthropic

    client = anthropic.Anthropic()

    def _complete(system: str, user: str) -> str:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            block.text
            for block in response.content
            if isinstance(block, anthropic.types.TextBlock)
        )

    return _complete
```

> **mypy-strict note:** narrow the content-block union with `isinstance(block, anthropic.types.TextBlock)` (shown above) rather than `block.type == "text"` — the latter may not narrow the SDK's union under `--strict`, producing a `"...Block" has no attribute "text"` error. If the exact `TextBlock` import path differs in the installed SDK version, find it (`python -c "import anthropic.types as t; print(t.TextBlock)"`) and use that path.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_explain_client.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/solar_advisor/explain/client.py backend/tests/test_explain_client.py
git commit -m "feat(explain): Explainer with kill-switch, rate limit, and provenance withholding"
```

---

## Task 7: `/api/explain` endpoint + wiring

**Files:**
- Modify: `backend/src/solar_advisor/api/schemas.py`
- Modify: `backend/src/solar_advisor/api/app.py`
- Modify: `backend/Dockerfile.api`, `backend/docker-compose.yml`
- Test: `backend/tests/test_api_explain.py`

- [ ] **Step 1: Add the response schema**

In `api/schemas.py`:

```python
class ExplanationView(BaseModel):
    explanation: str
    generated: bool
    guard_ok: bool
    unverified_numbers: list[float]
    disclaimer: str
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_api_explain.py
from fastapi.testclient import TestClient

from solar_advisor.api.app import build_app, get_explainer, get_service
from solar_advisor.explain.client import Explainer
from solar_advisor.services.recommendation import RecommendationService
from tests.test_api import _FakeEstimator, _FakeForecast, _config, _ready_state


def _client(state, complete, *, enabled=True):
    app = build_app(state=state)
    svc = RecommendationService(config=_config(), estimator=_FakeEstimator(), forecast=_FakeForecast())
    explainer = Explainer(complete=complete, enabled=enabled, min_interval_s=0.0)
    app.dependency_overrides[get_service] = lambda: svc
    app.dependency_overrides[get_explainer] = lambda: explainer
    return TestClient(app)


def test_explain_returns_generated_text_with_disclaimer():
    def complete(system, user):
        return "Your schedule grid-charges to 100% overnight, importing 13.0 kWh."

    resp = _client(_ready_state(), complete).get("/api/explain?objective=1.0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["generated"] is True
    assert body["guard_ok"] is True
    assert "100%" in body["explanation"]
    assert "read-only" in body["disclaimer"].lower()


def test_explain_withholds_fabricated_numbers():
    def complete(system, user):
        return "You'll save R777 a month."  # not in facts

    body = _client(_ready_state(), complete).get("/api/explain").json()
    assert body["guard_ok"] is False
    assert 777.0 in body["unverified_numbers"]
    assert "777" not in body["explanation"]


def test_explain_503_when_state_not_ready():
    from solar_advisor.ingest.live import LiveState

    resp = _client(LiveState(store=None), lambda s, u: "x").get("/api/explain")
    assert resp.status_code == 503
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_api_explain.py -v`
Expected: FAIL with `ImportError: cannot import name 'get_explainer'`.

- [ ] **Step 4: Wire the endpoint**

In `api/app.py`:

Add the import near the others:

```python
from solar_advisor.api.schemas import DashboardView, ExplanationView, RecommendationView, SlotView
from solar_advisor.explain.client import Explainer, anthropic_complete
from solar_advisor.explain.context import build_context
```

Add the dependency (next to `get_service`):

```python
def get_explainer(request: Request) -> Explainer:
    explainer = getattr(request.app.state, "explainer", None)
    if explainer is None:
        raise HTTPException(status_code=500, detail="explainer not initialised")
    return explainer
```

Add the endpoint (inside `build_app`, after `dashboard`):

```python
    @app.get("/api/explain", response_model=ExplanationView)
    def explain(
        objective: float | None = Query(default=None, ge=0.0, le=1.0),
        service: RecommendationService = Depends(get_service),  # noqa: B008
        state: LiveState = Depends(get_state),  # noqa: B008
        explainer: Explainer = Depends(get_explainer),  # noqa: B008
    ) -> ExplanationView:
        try:
            data = service.build(state, objective=objective)
        except LookupError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        result = explainer.explain(build_context(data))
        return ExplanationView(
            explanation=result.text,
            generated=result.generated,
            guard_ok=result.guard_ok,
            unverified_numbers=result.unverified,
            disclaimer=data.disclaimer,
        )
```

In `create_production_app`, build and attach the explainer (after `_SERVICE`/service creation, before/after `build_app` — set on `app.state`):

```python
    explainer = Explainer(
        complete=anthropic_complete(config.explain_model),
        enabled=config.explain_enabled,
        min_interval_s=config.explain_min_interval_s,
    )
    app = build_app(state=state, config=config)
    app.state.service = service
    app.state.explainer = explainer
    return app
```

(Adjust the existing `create_production_app` so `build_app` is called once and both `service` and `explainer` are attached to `app.state`; remove any duplicate `build_app`/return.)

Also update CORS to allow the new GET (already GET-only, so no change) and leave the disclaimer flowing.

- [ ] **Step 5: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_api_explain.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Pass the API key + explain env into the container**

In `docker-compose.yml` `api` service `environment:`, add:

```yaml
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:?set in .env}
      SA_EXPLAIN_MODEL: ${SA_EXPLAIN_MODEL:-claude-haiku-4-5}
      SA_EXPLAIN_ENABLED: ${SA_EXPLAIN_ENABLED:-true}
```

(`Dockerfile.api` needs no change — env is passed at run time, and the key never bakes into the image.)

- [ ] **Step 7: Run the full suite**

Run: `cd backend && make check`
Expected: ruff, mypy strict, import-linter (1 kept — engine still forbidden from importing `explain`/`anthropic`), all tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/src/solar_advisor/api/ backend/tests/test_api_explain.py backend/docker-compose.yml
git commit -m "feat(api): /api/explain endpoint with provenance-guarded LLM explanation"
```

---

## Definition of done (Plan D)

- `make check` green: ruff, `mypy --strict`, import-linter (engine still pure — never imports `explain` or `anthropic`), all tests pass.
- `GET /api/explain?objective=<0..1>` returns a plain-English explanation of the engine's output with the advisory disclaimer; 503 until live state is ready.
- The kill-switch (`SA_EXPLAIN_ENABLED=false`) returns a canned message without calling the API; the rate limit blocks bursts.
- The provenance guard is a tested runtime invariant: a reply citing a number absent from the engine facts is **withheld** and the fabricated figure never reaches the user (`test_fabricated_number_is_withheld`, `test_explain_withholds_fabricated_numbers`).
- The API key is server-side only (env), never in the image or any response.

**Next:** Plan E — the Vue 3 dashboard consuming `/api/dashboard` and `/api/explain`, with the cost↔resilience slider, history charts, and the visible advisory disclaimer.

---

## Self-review notes

- **Spec coverage:** §8 enforced boundary — `explain/` consumes only `DashboardData`/`ExplanationContext` (pre-computed values), never the engine; the import-linter contract keeps the engine free of `explain`/`anthropic` (verified each `make check`). §8 provenance guard — `guard.check_provenance` + the withhold path in `Explainer`, the centerpiece tested invariant. §8 model/key/kill-switch/rate-limit — `anthropic_complete` (server-side `ANTHROPIC_API_KEY`), `explain_enabled`, `explain_min_interval_s`. §3 goal-3 — the explanation renders per-slot behavior + cost + recommendation. Also closes the Plan C deferred minor (forecast/tariff surfaced for the explanation and the UI).
- **Type consistency:** `build_context(DashboardData)` reads the exact `DashboardData` fields defined in Plan C + the three added in Task 2; `SlotFact`/`RecommendationFact` mirror `SlotAssessment`/`Recommendation`. `Explainer.explain(ExplanationContext) -> ExplanationResult` is used identically by `test_explain_client` and the `/api/explain` endpoint. `build_messages` returns `(system, user)` where `user == ctx.to_facts()`, and the guard's whitelist is `extract_numbers(user)` — the same string — so provenance is exact. `get_explainer`/`app.state.explainer` follow the Plan C `app.state` + `Depends` pattern.
- **No placeholders:** every code step is complete and runnable; commands carry expected output.
- **Safety:** the LLM call is outbound to Anthropic only; nothing in `explain/` can touch the inverter. The key is read from the environment by the SDK, never logged or returned.
```
