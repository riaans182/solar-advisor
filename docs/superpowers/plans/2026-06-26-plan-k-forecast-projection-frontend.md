# Plan K — Prepaid Projection & Clearer UI (Frontend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show battery charge/discharge as %/hour, replace the misleading "bill so far" with a prepaid month projection, show per-purchase "days of cover", and make the recommendation actionable (incl. explaining the flat daily cost).

**Architecture:** Consume the new dashboard fields (`month_spend`, `month_projected_cost`, `month_balance`) added by Plan J. All changes are presentational; no new client calls.

**Tech Stack:** Vue 3 `<script setup lang="ts">`, TS strict, Vitest + @vue/test-utils, ESLint flat + Prettier (no semicolons, single quotes, 2-space indent).

**Reference (read first):** spec `docs/superpowers/specs/2026-06-26-forecast-prepaid-projection-design.md` (§K). Backend (merged) `/api/dashboard` now returns `month_spend`, `month_projected_cost`, `month_balance`. Files: `src/components/LiveTiles.vue` (has `batteryFlow`/`conversion` computeds), `src/components/RecommendationPanel.vue` (takes `recommendation`, shows "Bill so far"), `src/views/Dashboard.vue` (renders `<RecommendationPanel :recommendation="dashboard.recommendation" />`), `src/views/Purchases.vue` (fetches the dashboard for the tariff badge), `src/components/PurchaseTable.vue` (inline-edit table), `src/api/types.ts`. **From `frontend/`: `npm install` if needed; after any `.vue` edit run `npx eslint --fix <file>`. `npm run check` = lint → typecheck → test → build.**

---

## File Structure

| File | Change |
|------|--------|
| `src/api/types.ts` | `DashboardView` += `month_spend`, `month_projected_cost`, `month_balance`. |
| `src/components/LiveTiles.vue` | battery sub-line gains a %/hour rate. |
| `src/components/RecommendationPanel.vue` | replace "Bill so far" with the projection; actionable charge wording + flat-cost note. |
| `src/views/Dashboard.vue` | pass the projection props to `RecommendationPanel`. |
| `src/components/PurchaseTable.vue` | per-row "≈ N days" cover. |
| `src/views/Purchases.vue` | capture daily consumption from the dashboard; pass to the table. |
| tests | `components.test.ts`, `purchase-table.test.ts`. |

---

## Group 1 — Types + battery %/hour

### Task 1: Projection types

**Files:** Modify `src/api/types.ts`.

- [ ] **Step 1:** In `DashboardView`, add after `expected_pv_kwh_tomorrow: number`:
```ts
  expected_pv_kwh_tomorrow: number
  month_spend: number
  month_projected_cost: number
  month_balance: number
```

- [ ] **Step 2:** `npm run typecheck` — passes.

- [ ] **Step 3: Commit**
```bash
git add src/api/types.ts
git commit -m "feat(fe): add month projection types to DashboardView"
```

### Task 2: Battery %/hour in LiveTiles

**Files:** Modify `src/components/LiveTiles.vue`; Test `tests/components.test.ts`.

- [ ] **Step 1: Write the failing test** (append to the existing `describe('LiveTiles battery flow + conversion', ...)` block in `tests/components.test.ts`; it already has the `dash()` helper with `usable_kwh: 15`):
```ts
  it('shows a %/hour rate alongside the battery wattage', () => {
    // 420 W / (15 kWh * 1000) * 100 = 2.8 %/h
    const w = mount(LiveTiles, { props: { dashboard: dash({ battery_power: 420, usable_kwh: 15 }) } })
    expect(w.text()).toContain('%/h')
    expect(w.text()).toContain('2.8')
  })
```

- [ ] **Step 2:** `npm run test -- components` → FAIL.

- [ ] **Step 3: Implement.** In `LiveTiles.vue`, replace the `batteryFlow` computed with a version that appends the rate:
```ts
const batteryFlow = computed(() => {
  const p = props.dashboard.battery_power
  const capWh = props.dashboard.usable_kwh * 1000
  const rate = capWh > 0 ? (p / capWh) * 100 : 0 // %/h
  if (p > 1) return `charging ${Math.round(p)} W · +${rate.toFixed(1)}%/h`
  if (p < -1) return `discharging ${Math.round(-p)} W · ${rate.toFixed(1)}%/h`
  return 'idle'
})
```
(For discharge, `rate` is already negative so it renders e.g. `−2.8%/h`.)

- [ ] **Step 4:** `npm run test -- components` → PASS. `npx eslint --fix src/components/LiveTiles.vue`.

- [ ] **Step 5: Commit**
```bash
git add src/components/LiveTiles.vue tests/components.test.ts
git commit -m "feat(fe): show battery charge/discharge rate as %/hour"
```

---

## Group 2 — Recommendation: projection + actionable wording

### Task 3: RecommendationPanel projection + wording

**Files:** Modify `src/components/RecommendationPanel.vue`, `src/views/Dashboard.vue`; Test `tests/components.test.ts`.

- [ ] **Step 1: Write/update tests** in `tests/components.test.ts`.

The existing `describe('RecommendationPanel', ...)` mounts with only `{ recommendation }`; the panel gains three required projection props, so **update that existing mount** and add new assertions. Replace the existing `RecommendationPanel` describe block with:
```ts
describe('RecommendationPanel', () => {
  const base = {
    recommendation,
    monthSpend: 1500,
    monthProjectedCost: 1200,
    monthBalance: 300,
  }

  it('reflects new values when the recommendation prop is reassigned', async () => {
    const w = mount(RecommendationPanel, { props: { ...base } })
    expect(w.text()).toContain('R12.34')
    await w.setProps({ recommendation: { ...recommendation, expected_daily_cost: 99.99 } })
    expect(w.text()).toContain('R99.99')
    expect(w.text()).not.toContain('R12.34')
  })

  it('shows the month projection instead of a bill-so-far', () => {
    const w = mount(RecommendationPanel, { props: { ...base } })
    expect(w.text().toLowerCase()).toContain('this month')
    expect(w.text()).toContain('R1500.00') // spent
    expect(w.text()).toContain('R1200.00') // projected
    expect(w.text().toLowerCase()).toContain('to spare')
  })

  it('shows a top-up when projected exceeds spend', () => {
    const w = mount(RecommendationPanel, { props: { ...base, monthBalance: -250 } })
    expect(w.text().toLowerCase()).toContain('to top up')
    expect(w.text()).toContain('R250.00')
  })

  it('explains the flat cost when no grid charging is needed', () => {
    const w = mount(RecommendationPanel, {
      props: { ...base, recommendation: { ...recommendation, enable_overnight_grid_charge: false, grid_charge_kwh: 0 } },
    })
    expect(w.text().toLowerCase()).toContain("won't change")
  })
})
```
(The file's existing `recommendation` fixture has `expected_daily_cost: 12.34`, `enable_overnight_grid_charge: false`, `grid_charge_kwh: 0`, `reserve_target_soc: 40`, `backup_hours: 8.5`.)

- [ ] **Step 2:** `npm run test -- components` → FAIL.

- [ ] **Step 3: Implement** `RecommendationPanel.vue`:

Add the three props:
```ts
const props = defineProps<{
  recommendation: RecommendationView
  monthSpend: number
  monthProjectedCost: number
  monthBalance: number
}>()
const r = computed(() => props.recommendation)
```

Replace the **"Bill so far" metric block** (the 4th `.metric` div) with the month projection:
```html
      <div class="metric metric--cost">
        <span class="metric__label">This month</span>
        <span class="metric__value">{{ formatRand(monthSpend) }}</span>
        <span class="metric__note">spent · projected {{ formatRand(monthProjectedCost) }}</span>
      </div>
```

Add a balance line immediately after the `.rec__grid` closing `</div>` (before `.rec__charge`):
```html
    <p class="rec__balance" :data-short="monthBalance < 0">
      <template v-if="monthBalance < 0">≈ {{ formatRand(-monthBalance) }} more to top up this month</template>
      <template v-else>≈ {{ formatRand(monthBalance) }} to spare this month</template>
      <span class="rec__balance-note">estimate from your usage so far</span>
    </p>
```

Make the charge advisory actionable + explain the flat cost. Replace the `<span v-if="r.enable_overnight_grid_charge">...</span>` / `<span v-else>...</span>` pair with:
```html
      <span v-if="r.enable_overnight_grid_charge" class="rec__charge-text">
        Set your inverter to grid-charge to ~<strong>{{ formatPercent(r.reserve_target_soc) }}</strong>
        overnight — about {{ formatKwh(r.grid_charge_kwh) }} from the grid buys ~{{ r.backup_hours.toFixed(1) }} h
        of backup at a cost.
      </span>
      <span v-else class="rec__charge-text">
        No grid-charging needed — solar &amp; battery cover your
        {{ formatPercent(r.reserve_target_soc) }} reserve. Today's cost won't change as you move the
        slider until backup needs grid energy.
      </span>
```

Add styles for the balance line to `<style scoped>`:
```css
.rec__balance {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  margin: 0.9rem 0 0;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--sa-good, #34d399);
}
.rec__balance[data-short='true'] {
  color: var(--sa-warn, #d8a83a);
}
.rec__balance-note {
  font-size: 0.74rem;
  font-weight: 400;
  color: var(--sa-text-dim, #9aa6b6);
}
```

- [ ] **Step 4: Wire the props in `Dashboard.vue`** — change the `<RecommendationPanel ... />` usage to:
```html
            <RecommendationPanel
              :recommendation="dashboard.recommendation"
              :month-spend="dashboard.month_spend"
              :month-projected-cost="dashboard.month_projected_cost"
              :month-balance="dashboard.month_balance"
            />
```

- [ ] **Step 5:** `npm run test -- components` → PASS. `npx eslint --fix src/components/RecommendationPanel.vue src/views/Dashboard.vue`.

- [ ] **Step 6: Commit**
```bash
git add src/components/RecommendationPanel.vue src/views/Dashboard.vue tests/components.test.ts
git commit -m "feat(fe): replace bill-so-far with prepaid projection; actionable recommendation"
```

---

## Group 3 — Per-purchase days of cover + gate

### Task 4: "Days of cover" in the purchase table

**Files:** Modify `src/components/PurchaseTable.vue`, `src/views/Purchases.vue`; Test `tests/purchase-table.test.ts`.

- [ ] **Step 1: Write the failing test** (append to `tests/purchase-table.test.ts`; its `purchases` fixture has a row `id: 1` with `units_kwh: 250`):
```ts
it('shows days of cover when daily consumption is provided', () => {
  const w = mount(PurchaseTable, { props: { purchases, dailyConsumption: 25 } })
  // 250 units / 25 kWh per day = 10 days
  expect(w.text()).toContain('≈ 10 days')
})

it('omits days of cover when daily consumption is unknown', () => {
  const w = mount(PurchaseTable, { props: { purchases, dailyConsumption: 0 } })
  expect(w.text()).not.toContain('days')
})
```

- [ ] **Step 2:** `npm run test -- purchase-table` → FAIL.

- [ ] **Step 3: Implement** in `PurchaseTable.vue`:

Add the prop (extend the existing `defineProps`):
```ts
const props = defineProps<{ purchases: PurchaseView[]; dailyConsumption?: number }>()
```
(If the existing `defineProps` was not assigned to `props`, assign it now since we need `props.dailyConsumption`. The emits/refs stay as they are.)

Add a helper in `<script setup>`:
```ts
function daysCover(unitsKwh: number): number | null {
  const daily = props.dailyConsumption
  if (!daily || daily <= 0) return null
  return Math.round(unitsKwh / daily)
}
```

In the **display-mode** Units cell (the non-editing `<td class="pt__num">{{ formatUnits(p.units_kwh) }}</td>`), append a cover sub-note:
```html
            <td class="pt__num">
              {{ formatUnits(p.units_kwh) }}
              <span v-if="daysCover(p.units_kwh) !== null" class="pt__cover">≈ {{ daysCover(p.units_kwh) }} days</span>
            </td>
```

Add a style:
```css
.pt__cover {
  display: block;
  font-size: 0.72rem;
  font-weight: 400;
  color: var(--sa-text-dim, #9aa6b6);
}
```

- [ ] **Step 4: Pass daily consumption from `Purchases.vue`.** It already calls `getDashboard(0.5)` in `loadTariff`. Add a ref and capture it:
```ts
const dailyConsumption = ref(0)
```
In `loadTariff`, after the existing assignments (`rate.value = d.tariff_rate` etc.), add:
```ts
    dailyConsumption.value = d.daily_consumption_kwh
```
And pass it to the table:
```html
      <PurchaseTable
        :purchases="purchases"
        :daily-consumption="dailyConsumption"
        @delete="onDelete"
        @update="onUpdate"
      />
```

- [ ] **Step 5:** `npm run test -- purchase-table` → PASS. `npx eslint --fix src/components/PurchaseTable.vue src/views/Purchases.vue`.

- [ ] **Step 6: Commit**
```bash
git add src/components/PurchaseTable.vue src/views/Purchases.vue tests/purchase-table.test.ts
git commit -m "feat(fe): show per-purchase days of cover in the table"
```

### Task 5: Full gate

- [ ] **Step 1:** `npm run check` (lint → typecheck → test → build). All four pass, **0 lint warnings** (run `npx eslint --fix` on any flagged file). Fix anything failing for files in this plan; re-run until fully green.
- [ ] **Step 2: Commit** any gate fixes:
```bash
git add -A && git commit -m "chore(fe): satisfy gate for prepaid projection & UI"
```

---

## Self-Review

**Spec coverage:** K1 battery %/h → Task 2; K2 projection panel → Tasks 1 + 3; K3 per-purchase days → Task 4; K4 actionable recommendation + flat-cost note → Task 3. ✓

**Placeholder scan:** the RecommendationPanel test replaces the *existing* describe block (the panel gains required props, so the old single-prop mount must be updated) — concrete props specified. All component code complete.

**Type consistency:** `month_spend`/`month_projected_cost`/`month_balance` added to `DashboardView` (Task 1), passed as `:month-spend` etc. → `RecommendationPanel` props `monthSpend`/`monthProjectedCost`/`monthBalance` (Task 3); `dailyConsumption?: number` prop ↔ `:daily-consumption="dailyConsumption"` from `Purchases.vue` (Task 4, sourced from `DashboardView.daily_consumption_kwh`); `formatRand`/`formatPercent`/`formatKwh` already imported in `RecommendationPanel`. ✓
