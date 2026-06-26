# Actionable Recommendation, Forward Month Figure & Robust Explain — Design

**Date:** 2026-06-26
**Status:** Approved (brainstorming) — ready for plans
**Depends on:** everything merged through Plans A–K + the timezone fix.

## 1. Purpose

From real use, three problems:
1. **The recommendation isn't actionable.** Live data shows the inverter grid-charging in every slot (~14.52 kWh/day ≈ R49.86) while the advisor computes that *no* grid-charging is needed for the chosen reserve. The panel never says "your schedule is doing X; change it to Y." Decision: show a **recommended 6-slot schedule side-by-side with the current one**, plus the cost delta.
2. **The prepaid "to spare" figure is wrong.** `month_to_date_grid_import_kwh` resets to ~0 on every container restart (in-memory baseline), so the projection is garbage ("R2348 to spare"). Decision: replace it with a **forward** estimate — "≈ R X more to finish the month at today's usage" — derived from the engine's realistic daily grid import, which doesn't depend on the broken counter.
3. **The explain guard blanket-withholds.** The provenance guard discards the *entire* explanation when the LLM cites one unverifiable number, so the user intermittently sees only "explanation withheld." Decision: keep the guard strict but (a) broaden the legitimately-citeable number set, (b) steer the prompt, and (c) **fall back to a deterministic engine-only summary** instead of a dead-end message.

## 2. Locked decisions
- Recommendation = **side-by-side recommended schedule** (per-slot target SOC + grid-charge) vs current, with daily cost delta.
- Month figure = **forward "more to finish the month"** = `expected_daily_grid_import_kwh × days_remaining × rate`.
- Explain guard stays strict; withheld → deterministic summary (never a bare "withheld").

---

## PLAN L — Recommended schedule + forward month figure (backend/engine)

### L1. Engine: `recommend_schedule`
New pure module `engine/recommend_schedule.py`:
`recommend_schedule(current, battery, forecast, load, daylight, objective, current_soc) -> list[Slot]`.

Policy for a **flat tariff with no cheap window** (grid-charging is pure cost, justified only to hold the resilience reserve):
- Keep each slot's `start`/`end`/`gen_charge` (same time points as the inverter's current schedule).
- For each slot:
  - **Daylight slot** (overlaps the daylight window): `target_soc = 100`, `grid_charge = False` — let solar fill the battery, never pay to charge.
  - **Night slot** (no daylight overlap): `target_soc = round(reserve_target_soc(objective, floor))`, `grid_charge = need_grid_charge` — hold the reserve; only grid-charge if the day's energy balance can't keep SOC above the reserve.
- `need_grid_charge` = the existing `recommend(...).enable_overnight_grid_charge` (i.e. `grid_charge_kwh > 0`). Reuse `engine/optimize.recommend` and `engine/objective.reserve_target_soc` — no new policy math, just project them onto the slot grid.

Pure: lives in `engine/`, imports only engine modules + `domain.schedule.Slot`; the import-linter contract is unaffected.

### L2. Service: assess both schedules, expose the diff + costs
In `RecommendationService.build()`:
- Build `recommended = recommend_schedule(...)`.
- `recommended_assessments = assess_schedule(recommended, …)` (same inputs as the current-schedule assessment already computed).
- `current_daily_cost = sum(a.cost for current assessments)`, `recommended_daily_cost = sum(a.cost for recommended)`, `daily_saving = current_daily_cost − recommended_daily_cost`.
- Add to `DashboardData` + `DashboardView`: `recommended_slots` (list of the same `SlotView` shape), `current_daily_cost`, `recommended_daily_cost`, `daily_saving`.

### L3. Forward month figure (replace the broken projection)
- `days_remaining = days_in_month − telemetry.ts.day + 1` (today inclusive; guard ≥ 1).
- `month_remaining_cost = recommendation.expected_daily_grid_import_kwh × days_remaining × derived.rate` (energy only).
- Keep `month_spend`. **Replace** `month_projected_cost`/`month_balance` with `month_remaining_cost` on `DashboardData`/`DashboardView` (and drop the two old fields). `_to_view` rounds to whole rand.
- Note: this sidesteps `month_to_date_grid_import_kwh` entirely, so the in-memory-counter reset no longer corrupts the headline figure. (Persisting that counter is still a nice-to-have but is now non-critical; leave it as a noted follow-up, not in scope.)

---

## PLAN M — Robust explain (backend)

### M1. Broaden the legitimately-citeable numbers
In `explain/context.py` `allowed_numbers()`, add the engine-produced values the model reasonably references: `days_in_month`, `100.0` (percent ceiling), `24.0` (hours/day), the tariff **fixed charge**, and the new L2/L3 numbers (`recommended_slots` target_soc/end_soc/grid_import/cost, `current_daily_cost`, `recommended_daily_cost`, `daily_saving`, `month_spend`, `month_remaining_cost`). Keep the curated-whitelist approach (no scraping prose).

### M2. Prompt steering
In `explain/prompt.py`, instruct the model to use only the figures provided in the context, to avoid doing arithmetic that introduces new numbers, and to express percentages/rand exactly as given. (Reduces the rate at which the guard trips.)

### M3. Graceful fallback instead of a dead end
In the explain flow (`explain/client.py` / `/api/explain`), when the guard withholds the LLM text, **return a deterministic, engine-only summary** built from the curated facts (which by construction cite only verified numbers) rather than the bare "withheld" message. Surface a small flag (e.g. `ExplanationView.generated = false`) so the UI can note it's the built-in summary. The deterministic summary is a short template over the same `ExplanationContext` facts (current vs recommended action, daily cost, reserve/backup, the forward month figure). The provenance guarantee is preserved — the user only ever sees numbers traceable to the engine — but never a dead end.

---

## PLAN N — Frontend

### N1. Side-by-side schedule + savings
`types.ts`: `DashboardView` += `recommended_slots: SlotView[]`, `current_daily_cost`, `recommended_daily_cost`, `daily_saving`; drop `month_projected_cost`/`month_balance`, add `month_remaining_cost`.
`ScheduleTable.vue` (or a new `ScheduleCompare.vue`): render **current vs recommended** per slot — show each slot's target SOC + behaviour for both, highlighting where they differ (esp. grid-charge on→off). A header line states the action + saving: e.g. **"Switch off grid-charging in slots 1–6 → save ~R{daily_saving}/day."** When current == recommended, show "Your schedule already matches the advice."

### N2. Recommendation panel: forward month figure + action headline
`RecommendationPanel.vue`: replace the "to spare/top up" balance line with **"Spent R{month_spend} this month · ≈ R{month_remaining_cost} more to finish at today's usage."** Keep the reserve/backup/daily-cost metrics. The charge advisory becomes the action headline tied to the schedule diff (N1).

### N3. Explain panel
`ExplainPanel.vue`: when `generated == false`, render the deterministic summary normally (it's a valid explanation now) with a subtle "built-in summary" tag instead of the alarming "withheld" copy.

---

## 3. Testing
**Engine (L1):** daylight slots → target 100 / grid_charge False; night slots → target = reserve / grid_charge only when `need_grid_charge`; preserves time points; the "all-slots-grid-charging current schedule" case yields a recommended schedule with grid_charge off and a positive `daily_saving`.
**Service (L2/L3):** dual-cost + saving; `recommended_slots` populated; `month_remaining_cost = daily_import × days_remaining × rate`; days_remaining guard; old projection fields gone.
**Explain (M):** allowed_numbers includes the new values; a reply citing the fixed charge / daily saving now passes; when a stray number is cited, the response is the deterministic summary (not "withheld") and `generated == false`; the deterministic summary cites only whitelisted numbers.
**Frontend (N):** schedule compare renders both columns + highlights diffs + savings header; "already matches" case; month line shows spent + "more to finish"; explain panel shows summary without the alarming copy when `generated == false`.

## 4. Decomposition
- **Plan L** — engine `recommend_schedule` + dual-cost/diff on dashboard + forward month figure.
- **Plan M** — explain hardening (allowed numbers, prompt, deterministic fallback).
- **Plan N** — frontend (schedule compare, month line, explain panel).
Each its own worktree → subagent-driven → fast-forward merge.

## 5. Non-goals (YAGNI)
- Writing the recommended schedule to the inverter (still strictly read-only/advisory — the user applies it).
- Persisting the month-to-date counter across restarts (now non-critical since the headline figure no longer uses it; noted follow-up).
- Modeling intra-day load shape; sub-hourly forecast allocation.
- A full optimiser that searches slot permutations — the recommended schedule is the simple flat-tariff policy (no grid-charge unless reserve needs it), which is correct for this tariff.
