# Plan N — Actionable Recommendation UI (frontend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the recommended schedule side-by-side with the current one (with the R/day saving), replace the confusing month balance with a forward "more to finish the month" figure, and render the explain panel's built-in summary cleanly instead of an alarming "withheld" box.

**Architecture:** Consume the new dashboard fields (`recommended_slots`, `current_daily_cost`, `recommended_daily_cost`, `daily_saving`, `month_remaining_cost`; the old `month_projected_cost`/`month_balance` are gone). A new `ScheduleCompare` wraps the existing `ScheduleTable` twice with a savings banner. Presentational only.

**Tech Stack:** Vue 3 `<script setup lang="ts">`, TS strict, Vitest + @vue/test-utils, ESLint flat + Prettier (no semicolons, single quotes, 2-space indent).

**Reference (read first):** spec `docs/superpowers/specs/2026-06-26-actionable-recommendation-design.md` (§N). Files: `src/api/types.ts`, `src/components/ScheduleTable.vue` (renders one schedule; `:slots`), `src/components/RecommendationPanel.vue` (currently takes `monthSpend`/`monthProjectedCost`/`monthBalance`), `src/components/ExplainPanel.vue` (has a `!guard_ok` "withheld" block + a `!generated` "Note" block), `src/views/Dashboard.vue` (renders `<ScheduleTable :slots="dashboard.slots" />` and `<RecommendationPanel .../>`). **From `frontend/`: `npm install` if needed; after any `.vue` edit `npx eslint --fix <file>`. `npm run check` = lint → typecheck → test → build.**

---

## File Structure

| File | Change |
|------|--------|
| `src/api/types.ts` | `DashboardView`: drop `month_projected_cost`/`month_balance`; add `month_remaining_cost`, `recommended_slots: SlotView[]`, `current_daily_cost`, `recommended_daily_cost`, `daily_saving`. |
| `src/components/ScheduleTable.vue` | optional `title` prop (default "Today's plan"). |
| `src/components/ScheduleCompare.vue` (create) | savings banner + current/recommended ScheduleTables. |
| `src/components/RecommendationPanel.vue` | month line → forward "more to finish"; drop projected/balance props. |
| `src/views/Dashboard.vue` | use `ScheduleCompare`; pass `month-remaining-cost`. |
| `src/components/ExplainPanel.vue` | render built-in summary cleanly; drop the alarming withheld box. |
| tests | `components.test.ts`, `dashboard.test.ts`, `explain-panel.test.ts`. |

---

## Group 1 — Types + ScheduleTable title

### Task 1: Types

**Files:** Modify `src/api/types.ts`.

- [ ] **Step 1:** In `DashboardView`, remove `month_projected_cost` and `month_balance`, and add (keep `month_spend`):
```ts
  month_spend: number
  month_remaining_cost: number
  recommended_slots: SlotView[]
  current_daily_cost: number
  recommended_daily_cost: number
  daily_saving: number
```

- [ ] **Step 2:** `npm run typecheck` — will FAIL where `month_projected_cost`/`month_balance` are still referenced (RecommendationPanel props, test fixtures). That's expected; later tasks fix them. (Don't chase it here beyond confirming the type edit is right.)

- [ ] **Step 3: Commit**
```bash
git add src/api/types.ts
git commit -m "feat(fe): dashboard types for recommended schedule, costs and month-remaining"
```

### Task 2: ScheduleTable optional title

**Files:** Modify `src/components/ScheduleTable.vue`.

- [ ] **Step 1:** Change the props + title so it can be relabeled. Replace `defineProps<{ slots: SlotView[] }>()` with:
```ts
const props = withDefaults(defineProps<{ slots: SlotView[]; title?: string }>(), {
  title: "Today's plan",
})
```
and in the template change `<h3 class="schedule__title">Today's plan</h3>` to `<h3 class="schedule__title">{{ props.title }}</h3>`.

- [ ] **Step 2:** `npm run test -- components` — the existing ScheduleTable tests still pass (default title unchanged). `npx eslint --fix src/components/ScheduleTable.vue`.

- [ ] **Step 3: Commit**
```bash
git add src/components/ScheduleTable.vue
git commit -m "feat(fe): optional title on ScheduleTable for reuse"
```

---

## Group 2 — Schedule compare + recommendation month line

### Task 3: `ScheduleCompare.vue`

**Files:** Create `src/components/ScheduleCompare.vue`; Test `tests/schedule-compare.test.ts`.

- [ ] **Step 1: Write the failing test** `tests/schedule-compare.test.ts`:
```ts
// tests/schedule-compare.test.ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ScheduleCompare from '../src/components/ScheduleCompare.vue'
import type { SlotView } from '../src/api/types'

function slot(over: Partial<SlotView> = {}): SlotView {
  return {
    start: '00:00',
    end: '05:00',
    target_soc: 65,
    grid_charge: true,
    behavior: 'grid_charging',
    end_soc: 90,
    grid_import_kwh: 13,
    cost: 46,
    ...over,
  }
}

describe('ScheduleCompare', () => {
  it('shows the saving + changed slots and both schedules when they differ', () => {
    const current = [slot({ grid_charge: true })]
    const recommended = [slot({ grid_charge: false, target_soc: 60, behavior: 'holding', cost: 0 })]
    const w = mount(ScheduleCompare, {
      props: { current, recommended, dailySaving: 46, currentCost: 46, recommendedCost: 0 },
    })
    expect(w.text()).toContain('R46') // saving
    expect(w.text().toLowerCase()).toContain('recommended schedule')
    // two schedule tables (current + recommended)
    expect(w.findAll('table').length).toBe(2)
  })

  it('says it already matches when current == recommended', () => {
    const s = [slot({ grid_charge: false })]
    const w = mount(ScheduleCompare, {
      props: { current: s, recommended: [slot({ grid_charge: false })], dailySaving: 0, currentCost: 0, recommendedCost: 0 },
    })
    expect(w.text().toLowerCase()).toContain('already matches')
    expect(w.findAll('table').length).toBe(1) // only the current schedule
  })
})
```

- [ ] **Step 2:** `npm run test -- schedule-compare` → FAIL.

- [ ] **Step 3: Implement** `src/components/ScheduleCompare.vue`:
```vue
<script setup lang="ts">
import { computed } from 'vue'
import type { SlotView } from '../api/types'
import { formatRand } from '../lib/format'
import ScheduleTable from './ScheduleTable.vue'

const props = defineProps<{
  current: SlotView[]
  recommended: SlotView[]
  dailySaving: number
  currentCost: number
  recommendedCost: number
}>()

// Slot numbers (1-based) where the advised target SOC or grid-charge differs.
const changedSlots = computed(() =>
  props.current
    .map((s, i) => {
      const r = props.recommended[i]
      const changed = !r || s.grid_charge !== r.grid_charge || s.target_soc !== r.target_soc
      return { n: i + 1, changed }
    })
    .filter((x) => x.changed)
    .map((x) => x.n),
)

const matches = computed(() => changedSlots.value.length === 0)
</script>

<template>
  <section class="cmp" aria-label="Schedule recommendation">
    <p v-if="matches" class="cmp__ok" role="status">
      Your inverter schedule already matches the advice — nothing to change.
    </p>
    <p v-else class="cmp__action" role="status">
      <strong>Save ≈ {{ formatRand(dailySaving) }}/day</strong> — switch to the recommended schedule
      (today {{ formatRand(currentCost) }} → {{ formatRand(recommendedCost) }}). Changes in
      slot{{ changedSlots.length > 1 ? 's' : '' }} {{ changedSlots.join(', ') }}.
    </p>

    <div class="cmp__tables">
      <ScheduleTable :slots="current" title="Current schedule" />
      <ScheduleTable v-if="!matches" :slots="recommended" title="Recommended schedule" />
    </div>
  </section>
</template>

<style scoped>
.cmp {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.cmp__action,
.cmp__ok {
  margin: 0;
  padding: 0.85rem 1.05rem;
  border-radius: 12px;
  font-size: 0.92rem;
  line-height: 1.5;
}
.cmp__action {
  background: var(--sa-warn-soft, #d8a83a14);
  border: 1px solid var(--sa-warn-line, #d8a83a44);
  color: var(--sa-text, #eef2f7);
}
.cmp__action strong {
  color: var(--sa-warn, #e0b54a);
}
.cmp__ok {
  background: var(--sa-good-soft, #34d39912);
  border: 1px solid var(--sa-good-line, #34d39930);
  color: var(--sa-text, #eef2f7);
}
.cmp__tables {
  display: grid;
  gap: 1rem;
}
</style>
```

- [ ] **Step 4:** `npm run test -- schedule-compare` → PASS. `npx eslint --fix src/components/ScheduleCompare.vue`.

- [ ] **Step 5: Commit**
```bash
git add src/components/ScheduleCompare.vue tests/schedule-compare.test.ts
git commit -m "feat(fe): add ScheduleCompare (current vs recommended + saving)"
```

### Task 4: RecommendationPanel forward month line + Dashboard wiring

**Files:** Modify `src/components/RecommendationPanel.vue`, `src/views/Dashboard.vue`; Test `tests/components.test.ts`, `tests/dashboard.test.ts`.

- [ ] **Step 1: Update the RecommendationPanel test** in `tests/components.test.ts`. Its `describe('RecommendationPanel', ...)` `base` props use `monthSpend`/`monthProjectedCost`/`monthBalance`. Replace `monthProjectedCost`/`monthBalance` with `monthRemainingCost`, and update the assertions:
```ts
  const base = {
    recommendation,
    monthSpend: 1500,
    monthRemainingCost: 650,
  }

  it('reflects new values when the recommendation prop is reassigned', async () => {
    const w = mount(RecommendationPanel, { props: { ...base } })
    expect(w.text()).toContain('R12.34')
    await w.setProps({ recommendation: { ...recommendation, expected_daily_cost: 99.99 } })
    expect(w.text()).toContain('R99.99')
  })

  it('shows spent + forward more-to-finish for the month', () => {
    const w = mount(RecommendationPanel, { props: { ...base } })
    expect(w.text()).toContain('R1500.00') // spent
    expect(w.text()).toContain('R650.00') // more to finish
    expect(w.text().toLowerCase()).toContain('to finish')
  })
```
(Delete the old "to spare"/"to top up" tests.)

- [ ] **Step 2:** `npm run test -- components` → FAIL.

- [ ] **Step 3: Edit `RecommendationPanel.vue`.** Replace the props:
```ts
const props = defineProps<{
  recommendation: RecommendationView
  monthSpend: number
  monthRemainingCost: number
}>()
```
Change the "This month" metric note to reference the forward figure:
```html
        <span class="metric__note">spent · ≈ {{ formatRand(monthRemainingCost) }} more to finish</span>
```
Replace the `.rec__balance` block (the `monthBalance < 0` top-up/spare paragraph) with:
```html
    <p class="rec__balance">
      ≈ {{ formatRand(monthRemainingCost) }} more to finish the month
      <span class="rec__balance-note">at today's usage</span>
    </p>
```
(Remove the `:data-short` binding and the `monthBalance` references.)

- [ ] **Step 4: Wire Dashboard.** In `src/views/Dashboard.vue`:
- Add the import: `import ScheduleCompare from '../components/ScheduleCompare.vue'`.
- Replace `<ScheduleTable :slots="dashboard.slots" />` with:
```html
            <ScheduleCompare
              :current="dashboard.slots"
              :recommended="dashboard.recommended_slots"
              :daily-saving="dashboard.daily_saving"
              :current-cost="dashboard.current_daily_cost"
              :recommended-cost="dashboard.recommended_daily_cost"
            />
```
- Update the `<RecommendationPanel .../>` usage: drop `:month-projected-cost`/`:month-balance`, add `:month-remaining-cost="dashboard.month_remaining_cost"` (keep `:recommendation` and `:month-spend`).
- Remove the now-unused `import ScheduleTable` from Dashboard (ScheduleTable is now only used inside ScheduleCompare). Verify ScheduleTable isn't referenced elsewhere in Dashboard.

- [ ] **Step 5: Fix `dashboard.test.ts` fixture.** Its `DASH` fixture has `month_projected_cost`/`month_balance` — replace with `month_remaining_cost: 0` and add `recommended_slots: [], current_daily_cost: 0, recommended_daily_cost: 0, daily_saving: 0` (so the dashboard + ScheduleCompare render). Keep `month_spend`.

- [ ] **Step 6:** `npm run test -- "components|dashboard"` (run as two invocations: `npm run test -- components` then `npm run test -- dashboard`) → PASS. `npx eslint --fix src/components/RecommendationPanel.vue src/views/Dashboard.vue`.

- [ ] **Step 7: Commit**
```bash
git add src/components/RecommendationPanel.vue src/views/Dashboard.vue tests/components.test.ts tests/dashboard.test.ts
git commit -m "feat(fe): side-by-side schedule on the dashboard; forward month-remaining line"
```

---

## Group 3 — Explain panel + gate

### Task 5: ExplainPanel built-in summary (drop the alarming withheld box)

**Files:** Modify `src/components/ExplainPanel.vue`; Test `tests/explain-panel.test.ts`.

- [ ] **Step 1: Update the test** in `tests/explain-panel.test.ts` (read it first). The backend now returns the deterministic summary as `explanation` with `generated=false` (and `guard_ok=false` only in the withheld case) — there is no dead-end "withheld" copy anymore. Replace any assertion expecting the "Explanation withheld" text with: when `generated=false`, the panel shows the explanation text + a "Built-in summary" tag (no alarming copy). Concretely add/replace:
```ts
it('shows the built-in summary (not an alarming withheld box) when not generated', async () => {
  // mount, mock getExplain to resolve a result with generated:false, guard_ok:false,
  // explanation:'## Built-in\nSwitch off grid-charge...', then click Explain.
  // Assert the explanation text is shown and the panel does NOT contain 'withheld'.
})
```
Implement it against the file's existing mock/click harness; assert `w.text()` contains the summary text and a "Built-in summary" label, and does NOT contain "withheld".

- [ ] **Step 2:** `npm run test -- explain-panel` → FAIL.

- [ ] **Step 3: Edit `ExplainPanel.vue`.** Replace the whole result block (the `v-if="!result.guard_ok"` withheld box + the `v-else-if="!result.generated"` note + the `v-else` body) with a two-way split:
```html
    <template v-else-if="result">
      <!-- A generated, provenance-verified explanation -->
      <p v-if="result.generated" class="explain__body">{{ result.explanation }}</p>

      <!-- Built-in deterministic summary (AI off / unavailable / draft set aside).
           Still a real, engine-verified explanation — shown plainly, not as an error. -->
      <div v-else class="explain__note" role="status">
        <span class="explain__note-tag">Built-in summary</span>
        <p class="explain__note-body">{{ result.explanation }}</p>
      </div>

      <p class="explain__disclaimer">{{ result.disclaimer }}</p>
    </template>
```
Delete the now-unused `.explain__withheld*` styles and the `.explain__num` style (optional cleanup; leave if unsure, but they'll be unused). The `unverified_numbers` field is no longer surfaced in the UI.

- [ ] **Step 4:** `npm run test -- explain-panel` → PASS. `npx eslint --fix src/components/ExplainPanel.vue`.

- [ ] **Step 5: Commit**
```bash
git add src/components/ExplainPanel.vue tests/explain-panel.test.ts
git commit -m "feat(fe): show the built-in explain summary cleanly, drop the withheld box"
```

### Task 6: Full gate

- [ ] **Step 1:** `npm run check` (lint → typecheck → test → build). All four pass, **0 lint warnings** (`npx eslint --fix` any flagged file). Fix anything failing for files in this plan (esp. any lingering `month_projected_cost`/`month_balance`/`ScheduleTable` references) until fully green.
- [ ] **Step 2: Commit** any fixes:
```bash
git add -A && git commit -m "chore(fe): satisfy gate for actionable recommendation UI"
```

---

## Self-Review

**Spec coverage:** N1 side-by-side schedule + savings → Tasks 2–4 (`ScheduleCompare`); N2 forward month line + Dashboard wiring → Task 4; N3 explain built-in summary → Task 5. ✓

**Placeholder scan:** the ExplainPanel test (Task 5) and dashboard fixture defer to the files' existing harness/fixture shapes — the implementer reads them and mirrors; all component code is complete.

**Type consistency:** `DashboardView` drops `month_projected_cost`/`month_balance`, adds `month_remaining_cost` + `recommended_slots`/`current_daily_cost`/`recommended_daily_cost`/`daily_saving` (Task 1); `RecommendationPanel` props become `monthSpend`/`monthRemainingCost` ← Dashboard `:month-spend`/`:month-remaining-cost`; `ScheduleCompare` props (`current`/`recommended`/`dailySaving`/`currentCost`/`recommendedCost`) ← Dashboard kebab-case bindings; `ScheduleTable` gains optional `title`; `ExplainPanel` keys off `result.generated` only (built-in summary otherwise). No references to the removed fields remain. ✓
