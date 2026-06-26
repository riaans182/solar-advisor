# Plan M — Robust Explain (backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the explain feature from dead-ending on "withheld": broaden the legitimately-citeable numbers, steer the prompt, and — the real fix — fall back to a **deterministic engine-only summary** whenever the LLM text isn't shown, so the user always gets a useful, verified explanation.

**Architecture:** Extend `ExplanationContext` with the recommended-schedule costs + month figures (so the LLM and the deterministic summary can both reference them), add them + a couple of structural constants to the provenance whitelist, add a `deterministic_summary(ctx)` built only from engine facts, and have `Explainer` return that summary (not a bland message) in every non-LLM-text branch.

**Tech Stack:** Python 3.12, pytest, ruff, mypy --strict, import-linter.

**Reference (read first):** spec `docs/superpowers/specs/2026-06-26-actionable-recommendation-design.md` (§M). Files: `explain/context.py` (`ExplanationContext`, `build_context`, `to_facts`, `allowed_numbers`), `explain/prompt.py` (`_SYSTEM`), `explain/client.py` (`Explainer.explain`, the `_*_MESSAGE` constants), `explain/guard.py` (`check_provenance`). `DashboardData` now has `current_daily_cost`, `recommended_daily_cost`, `daily_saving`, `month_spend`, `month_remaining_cost` (Plan L). **From `backend/`: `make install`, then `.venv/bin/pytest`, `.venv/bin/ruff`, `.venv/bin/mypy`, `.venv/bin/lint-imports --config .importlinter`.**

---

## File Structure

| File | Change |
|------|--------|
| `src/solar_advisor/explain/context.py` | extend `ExplanationContext` (+ `build_context`, `to_facts`, `allowed_numbers`); add `deterministic_summary`. |
| `src/solar_advisor/explain/prompt.py` | steer against counting-words / derived numbers. |
| `src/solar_advisor/explain/client.py` | fall back to `deterministic_summary` in non-LLM-text branches. |
| tests | `test_explain_context.py`, `test_explain_client.py`. |

---

## Group 1 — Context facts + deterministic summary + prompt

### Task 1: Extend `ExplanationContext` with the action/cost/month facts

**Files:** Modify `src/solar_advisor/explain/context.py`; Test `tests/test_explain_context.py`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_explain_context.py`; it already builds an `ExplanationContext`/`DashboardData` fixture — reuse it):
```python
def test_allowed_numbers_includes_action_and_month_figures():
    ctx = _context()  # the file's existing helper that builds an ExplanationContext
    allowed = ctx.allowed_numbers()
    for v in [
        ctx.daily_saving,
        ctx.current_daily_cost,
        ctx.recommended_daily_cost,
        ctx.month_spend,
        ctx.month_remaining_cost,
        100.0,
        24.0,
    ]:
        assert any(abs(v - a) < 1e-9 for a in allowed)


def test_to_facts_mentions_saving_and_month():
    ctx = _context()
    facts = ctx.to_facts()
    assert "saving" in facts.lower()
    assert "this month" in facts.lower() or "month" in facts.lower()
```
If the file has no `_context()` helper, derive the context from the existing `DashboardData` fixture via `build_context(...)`; match whatever the file already does.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_explain_context.py -k "action_and_month or saving_and_month" -v`
Expected: FAIL — fields/whitelist entries missing.

- [ ] **Step 3: Implement** in `explain/context.py`:

Add `import calendar` at the top.

Add fields to `ExplanationContext` (after `expected_pv_kwh_today: float`):
```python
    expected_pv_kwh_today: float
    current_daily_cost: float
    recommended_daily_cost: float
    daily_saving: float
    month_spend: float
    month_remaining_cost: float
    days_in_month: int
```

In `allowed_numbers()`, add to the `nums` list (after `self.expected_pv_kwh_today,`):
```python
            self.expected_pv_kwh_today,
            self.current_daily_cost,
            self.recommended_daily_cost,
            self.daily_saving,
            self.month_spend,
            self.month_remaining_cost,
```
and after the confidences-as-percent appends, add the structural constants:
```python
        # Structural constants the model legitimately names: percent ceiling, hours
        # in a day, and the number of days in the current month.
        nums.extend([100.0, 24.0, float(self.days_in_month)])
```

In `to_facts()`, add a section before `f"DISCLAIMER: {self.disclaimer}"` (i.e. extend the `lines += [...]` recommendation block):
```python
            f"- month-to-date bill: R{r.monthly_cost_so_far}",
            "RECOMMENDED ACTION (engine output):",
            f"- following the recommended schedule costs R{self.recommended_daily_cost}/day "
            f"vs R{self.current_daily_cost}/day now (saving R{self.daily_saving}/day)",
            f"- prepaid this month: spent R{self.month_spend}; about "
            f"R{self.month_remaining_cost} more to finish the month at today's usage",
            f"DISCLAIMER: {self.disclaimer}",
        ]
```

In `build_context(data)`, populate the new fields (before/with `disclaimer=`):
```python
        expected_pv_kwh_today=round(data.expected_pv_kwh_today, 2),
        current_daily_cost=round(data.current_daily_cost, 2),
        recommended_daily_cost=round(data.recommended_daily_cost, 2),
        daily_saving=round(data.daily_saving, 2),
        month_spend=round(data.month_spend),
        month_remaining_cost=round(data.month_remaining_cost),
        days_in_month=calendar.monthrange(data.telemetry.ts.year, data.telemetry.ts.month)[1],
```
(Place `expected_pv_kwh_today=...` where it already is; add the six new lines after it. Keep the existing `slots=`, `recommendation=`, `disclaimer=`.)

Also update the file's test fixture/helper that constructs `ExplanationContext` or `DashboardData` directly so it provides the new fields (the `DashboardData` fixture already has the L fields from Plan L; if the test builds `ExplanationContext` directly it needs the six new values — set sensible numbers, e.g. `current_daily_cost=49.86, recommended_daily_cost=0.0, daily_saving=49.86, month_spend=2350.0, month_remaining_cost=300.0, days_in_month=30`).

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_explain_context.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/solar_advisor/explain/context.py tests/test_explain_context.py
git commit -m "feat: add action/cost/month facts + constants to explain context & whitelist"
```

### Task 2: `deterministic_summary` + prompt steering

**Files:** Modify `src/solar_advisor/explain/context.py`, `src/solar_advisor/explain/prompt.py`; Test `tests/test_explain_context.py`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_explain_context.py`):
```python
from solar_advisor.explain.context import deterministic_summary
from solar_advisor.explain.guard import check_provenance


def test_deterministic_summary_is_provenance_clean():
    ctx = _context()
    summary = deterministic_summary(ctx)
    assert check_provenance(summary, allowed=ctx.allowed_numbers()).ok


def test_deterministic_summary_calls_out_saving_when_present():
    ctx = _context()  # fixture has daily_saving ~ 49.86
    summary = deterministic_summary(ctx).lower()
    assert "save" in summary or "saving" in summary
    assert "this month" in summary
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_explain_context.py -k deterministic_summary -v`
Expected: FAIL — function missing.

- [ ] **Step 3: Implement** `deterministic_summary` at the end of `explain/context.py`:
```python
def deterministic_summary(ctx: ExplanationContext) -> str:
    """A plain-English summary built ONLY from engine facts — every number is an
    allowed value, so it passes the provenance guard by construction. Used as the
    fallback whenever the LLM text isn't shown, so the user never hits a dead end."""
    r = ctx.recommendation
    lines = [
        "## Your system right now",
        f"Battery at {ctx.battery_soc}%, solar {ctx.pv_power} W, load {ctx.load_power} W, "
        f"grid {ctx.grid_power} W, on a flat R{ctx.tariff_rate}/kWh tariff.",
        "",
        "## What to change",
    ]
    if ctx.daily_saving >= 1:
        lines.append(
            f"Your schedule grid-charges more than you need. Following the recommended schedule "
            f"would cut today's grid cost from R{ctx.current_daily_cost} to "
            f"R{ctx.recommended_daily_cost} — about R{ctx.daily_saving} a day. With no cheap "
            f"window, grid-charging only pays off for backup, and your solar plus battery already "
            f"hold the {r.reserve_target_soc}% reserve (~{r.backup_hours} h of backup)."
        )
    else:
        lines.append(
            f"Your schedule already matches the advice — no needless grid-charging to cut. "
            f"You're holding a {r.reserve_target_soc}% reserve (~{r.backup_hours} h of backup)."
        )
    lines += [
        "",
        "## This month",
        f"Spent R{ctx.month_spend} so far; at today's usage you'll need about "
        f"R{ctx.month_remaining_cost} more to finish the month.",
        "",
        ctx.disclaimer,
    ]
    return "\n".join(lines)
```

- [ ] **Step 4: Steer the prompt.** In `explain/prompt.py` `_SYSTEM`, add two bullets to the Hard rules (so the LLM trips the guard less often):
```python
    "- Do NOT write counting words either (e.g. 'six slots', 'two slots'); say 'all slots' "
    "or name them by digit ('slot 3'). Never state a total or difference you worked out "
    "yourself — only quote figures that appear verbatim in the facts.\n"
```
(Insert it after the existing "Write every number as plain digits…" bullet.)

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_explain_context.py -k deterministic_summary -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/solar_advisor/explain/context.py src/solar_advisor/explain/prompt.py tests/test_explain_context.py
git commit -m "feat: add deterministic_summary fallback and tighten the explain prompt"
```

---

## Group 2 — Wire the fallback + gate

### Task 3: `Explainer` returns the deterministic summary instead of dead-end messages

**Files:** Modify `src/solar_advisor/explain/client.py`; Test `tests/test_explain_client.py`.

- [ ] **Step 1: Write/adjust the failing tests** in `tests/test_explain_client.py`. The existing tests assert the bland `_*_MESSAGE` strings on disabled/withheld/unavailable — those messages change to the deterministic summary. Read the file, then for the disabled, withheld, and unavailable cases assert the result is the deterministic summary with `generated == False`. Add/replace:
```python
def test_withheld_falls_back_to_deterministic_summary():
    # A completion that cites an impossible number trips the guard.
    explainer = Explainer(complete=lambda s, u: "Your bill will be R999999.99 next year.", enabled=True)
    ctx = _context()  # the file's context fixture/helper
    res = explainer.explain(ctx)
    assert res.guard_ok is False
    assert res.generated is False
    assert res.text == deterministic_summary(ctx)


def test_disabled_returns_deterministic_summary():
    explainer = Explainer(complete=lambda s, u: "unused", enabled=False)
    ctx = _context()
    res = explainer.explain(ctx)
    assert res.generated is False
    assert res.text == deterministic_summary(ctx)


def test_successful_reply_is_returned_verbatim():
    # A reply citing only allowed numbers passes and is shown as-is.
    ctx = _context()
    soc = ctx.battery_soc
    explainer = Explainer(complete=lambda s, u: f"Battery is at {soc}%.", enabled=True)
    res = explainer.explain(ctx)
    assert res.generated is True
    assert res.guard_ok is True
    assert "Battery is at" in res.text
```
Import `deterministic_summary` at the top of the test file. Match the file's existing context-building helper (`_context()` / a fixture). If existing tests asserted `_WITHHELD_MESSAGE`/`_DISABLED_MESSAGE`, update them to the new behavior (the bland constants may be removed if now unused).

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_explain_client.py -v`
Expected: FAIL (old message assertions / new ones).

- [ ] **Step 3: Implement** in `explain/client.py`:

Import the summary: `from solar_advisor.explain.context import ExplanationContext, deterministic_summary`.

Rewrite `explain()` so every branch that doesn't show guarded LLM text returns the deterministic summary (build it once up front):
```python
    def explain(self, ctx: ExplanationContext) -> ExplanationResult:
        summary = deterministic_summary(ctx)
        if not self._enabled:
            return ExplanationResult(text=summary, generated=False, guard_ok=True)

        now = self._now()
        if self._last_call is not None and (now - self._last_call) < self._min_interval_s:
            return ExplanationResult(text=summary, generated=False, guard_ok=True)
        self._last_call = now

        system, user = build_messages(ctx)
        try:
            reply = self._complete(system, user)
        except Exception:  # noqa: BLE001 - any provider failure degrades, never 500s
            return ExplanationResult(text=summary, generated=False, guard_ok=True)
        if not reply.strip():
            return ExplanationResult(text=summary, generated=False, guard_ok=True)
        result = check_provenance(reply, allowed=ctx.allowed_numbers())
        if not result.ok:
            return ExplanationResult(
                text=summary, generated=False, guard_ok=False, unverified=result.unverified
            )
        return ExplanationResult(text=reply, generated=True, guard_ok=True)
```
Remove the now-unused `_DISABLED_MESSAGE`/`_RATE_LIMITED_MESSAGE`/`_WITHHELD_MESSAGE`/`_UNAVAILABLE_MESSAGE` constants (or keep only those still referenced — none are, so delete them to satisfy ruff F401/unused).

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_explain_client.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/solar_advisor/explain/client.py tests/test_explain_client.py
git commit -m "feat: explain falls back to the deterministic summary, never a dead end"
```

### Task 4: Full gate

- [ ] **Step 1:** `.venv/bin/pytest -q` — all green. Watch for other tests referencing the removed `_*_MESSAGE` constants or the old `ExplanationContext` shape; update them.
- [ ] **Step 2:** `.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy && .venv/bin/lint-imports --config .importlinter` — all clean.
- [ ] **Step 3:** Fix anything; re-run until clean.
- [ ] **Step 4:** Commit fixes: `git add -A && git commit -m "chore: satisfy gates for robust explain"`.

---

## Self-Review

**Spec coverage:** M1 broaden whitelist + facts → Task 1; M2 prompt steering → Task 2; M3 deterministic fallback (never a dead end) → Tasks 2–3. ✓

**Placeholder scan:** the tests defer to the file's existing context helper (`_context()`/fixture) — the implementer matches what's there; all production code is complete.

**Type consistency:** the six new `ExplanationContext` fields are populated in `build_context` from the matching `DashboardData` fields (present since Plan L), surfaced in `to_facts`, and whitelisted in `allowed_numbers`; `deterministic_summary(ctx)` reads only those fields (so it's provenance-clean by construction); `Explainer.explain` returns it in all non-LLM-text branches with `generated=False`. The guard/`check_provenance` is unchanged — provenance is still enforced; the LLM reply is only ever shown when it passes. ✓
