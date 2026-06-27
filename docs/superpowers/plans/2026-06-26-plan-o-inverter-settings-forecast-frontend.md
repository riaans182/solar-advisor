# Plan O — Inverter Settings Sheet & Forecast Tile (frontend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Present the recommendation as a "what to set on your inverter" sheet (Time | State of charge | Charge, diff-highlighted), and surface the solar forecast as a tile.

**Architecture:** Display-only — all data is already on `DashboardView` (`slots`, `recommended_slots` with `target_soc`/`grid_charge`, `expected_pv_kwh_today`/`tomorrow`). New `ScheduleSettings` component; `ScheduleCompare` uses it for the recommended side; a forecast tile in `LiveTiles`.

**Tech Stack:** Vue 3 `<script setup lang="ts">`, TS strict, Vitest + @vue/test-utils, ESLint flat + Prettier (no semicolons, single quotes, 2-space indent).

**Reference (read first):** spec `docs/superpowers/specs/2026-06-26-inverter-settings-and-forecast-design.md`. Files: `src/components/ScheduleCompare.vue` (banner + current `ScheduleTable` + recommended `ScheduleTable`), `src/components/ScheduleTable.vue` (reused for "Today's plan"), `src/components/LiveTiles.vue` (tiles; has `formatPercent`/`formatPower` imports), `src/lib/format.ts` (`formatKwh`, `formatPercent`), `src/api/types.ts` (`SlotView`, `DashboardView`). **From `frontend/`: `npm install` if needed; after any `.vue` edit `npx eslint --fix <file>`. `npm run check` = lint → typecheck → test → build.**

---

## File Structure

| File | Change |
|------|--------|
| `src/components/ScheduleSettings.vue` (create) | Time / State of charge / Charge diff sheet. |
| `src/components/ScheduleCompare.vue` | use `ScheduleSettings` for the recommended side. |
| `src/components/LiveTiles.vue` | add a Solar forecast tile. |
| tests | `schedule-settings.test.ts` (new), `schedule-compare.test.ts`, `components.test.ts`. |

---

## Group 1 — Settings sheet

### Task 1: `ScheduleSettings.vue`

**Files:** Create `src/components/ScheduleSettings.vue`; Test `tests/schedule-settings.test.ts`.

- [ ] **Step 1: Write the failing test** `tests/schedule-settings.test.ts`:
```ts
// tests/schedule-settings.test.ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ScheduleSettings from '../src/components/ScheduleSettings.vue'
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

describe('ScheduleSettings', () => {
  it('shows SOC% and Charge on/off per slot, highlighting changes with the old value', () => {
    const current = [slot({ target_soc: 65, grid_charge: true })]
    const recommended = [slot({ target_soc: 60, grid_charge: false })]
    const w = mount(ScheduleSettings, { props: { current, recommended } })
    expect(w.text()).toContain('60%')
    expect(w.text().toLowerCase()).toContain('off')
    // shows what it was
    expect(w.text()).toContain('was 65%')
    expect(w.text().toLowerCase()).toContain('was on')
    // changed cells flagged
    expect(w.get('[data-test="soc-0"]').classes()).toContain('is-changed')
    expect(w.get('[data-test="charge-0"]').classes()).toContain('is-changed')
  })

  it('does not flag unchanged slots', () => {
    const s = [slot({ target_soc: 100, grid_charge: false })]
    const w = mount(ScheduleSettings, {
      props: { current: s, recommended: [slot({ target_soc: 100, grid_charge: false })] },
    })
    expect(w.text()).not.toContain('was')
    expect(w.get('[data-test="soc-0"]').classes()).not.toContain('is-changed')
  })
})
```

- [ ] **Step 2:** `npm run test -- schedule-settings` → FAIL.

- [ ] **Step 3: Implement** `src/components/ScheduleSettings.vue`:
```vue
<script setup lang="ts">
import { computed } from 'vue'
import type { SlotView } from '../api/types'
import { formatPercent } from '../lib/format'

const props = defineProps<{ current: SlotView[]; recommended: SlotView[] }>()

interface Row {
  time: string
  soc: number
  socChanged: boolean
  socWas: number
  charge: boolean
  chargeChanged: boolean
  chargeWas: boolean
}

const rows = computed<Row[]>(() =>
  props.recommended.map((r, i) => {
    const c = props.current[i]
    return {
      time: `${r.start}–${r.end}`,
      soc: r.target_soc,
      socChanged: !!c && c.target_soc !== r.target_soc,
      socWas: c ? c.target_soc : r.target_soc,
      charge: r.grid_charge,
      chargeChanged: !!c && c.grid_charge !== r.grid_charge,
      chargeWas: c ? c.grid_charge : r.grid_charge,
    }
  }),
)

function onOff(v: boolean): string {
  return v ? 'On' : 'Off'
}
</script>

<template>
  <section class="set" aria-label="Recommended inverter settings">
    <header class="set__head">
      <h3 class="set__title">Recommended inverter settings</h3>
      <p class="set__hint">Set these per time slot on your inverter</p>
    </header>

    <div class="set__scroll" role="region" aria-label="Settings per slot" tabindex="0">
      <table class="set__table">
        <thead>
          <tr>
            <th scope="col">Time</th>
            <th scope="col" class="num">State of charge</th>
            <th scope="col">Charge <span class="set__qual">(grid)</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in rows" :key="i">
            <td class="set__time">{{ row.time }}</td>
            <td class="num" :class="{ 'is-changed': row.socChanged }" :data-test="`soc-${i}`">
              {{ formatPercent(row.soc) }}
              <span v-if="row.socChanged" class="set__was">(was {{ formatPercent(row.socWas) }})</span>
            </td>
            <td :class="{ 'is-changed': row.chargeChanged }" :data-test="`charge-${i}`">
              {{ onOff(row.charge) }}
              <span v-if="row.chargeChanged" class="set__was">(was {{ onOff(row.chargeWas) }})</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p class="set__foot">
      Only State of charge and Charge change. Leave Power as-is; Sell stays off (zero-export).
    </p>
  </section>
</template>

<style scoped>
.set {
  padding: 1.25rem 1.35rem 1.4rem;
  border-radius: 16px;
  background: var(--sa-surface, #161c24);
  border: 1px solid var(--sa-line, #273140);
}
.set__head {
  margin-bottom: 0.9rem;
}
.set__title {
  margin: 0;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
}
.set__hint {
  margin: 0.2rem 0 0;
  font-size: 0.82rem;
  color: var(--sa-text-dim, #9aa6b6);
}
.set__scroll {
  overflow-x: auto;
}
.set__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}
.set__table th {
  text-align: left;
  padding: 0.4rem 0.6rem;
  font-size: 0.7rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
  border-bottom: 1px solid var(--sa-line, #273140);
}
.set__table th.num,
.set__table td.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.set__table td {
  padding: 0.55rem 0.6rem;
  border-bottom: 1px solid var(--sa-line, #1f2733);
  color: var(--sa-text, #eef2f7);
}
.set__qual {
  font-weight: 400;
  text-transform: none;
  letter-spacing: 0;
  color: var(--sa-text-dim, #6b7689);
}
.is-changed {
  background: var(--sa-warn-soft, #d8a83a14);
  color: var(--sa-warn, #e0b54a);
  font-weight: 600;
}
.set__was {
  font-size: 0.76rem;
  font-weight: 400;
  color: var(--sa-text-dim, #9aa6b6);
}
.set__foot {
  margin: 0.85rem 0 0;
  font-size: 0.78rem;
  color: var(--sa-text-dim, #9aa6b6);
}
</style>
```

- [ ] **Step 4:** `npm run test -- schedule-settings` → PASS (2). `npx eslint --fix src/components/ScheduleSettings.vue`.

- [ ] **Step 5: Commit**
```bash
git add src/components/ScheduleSettings.vue tests/schedule-settings.test.ts
git commit -m "feat(fe): add ScheduleSettings sheet (Time / SOC / Charge, diff-highlighted)"
```

### Task 2: `ScheduleCompare` uses the settings sheet

**Files:** Modify `src/components/ScheduleCompare.vue`; Test `tests/schedule-compare.test.ts`.

- [ ] **Step 1: Update the test** in `tests/schedule-compare.test.ts`. The "differ" case currently asserts the text contains `'recommended schedule'` (the old ScheduleTable title) — that title is gone; the recommended side is now the settings sheet. Update the assertion in the differ test:
```ts
    expect(w.text()).toContain('R46') // saving
    expect(w.text().toLowerCase()).toContain('recommended inverter settings')
    // current ScheduleTable + ScheduleSettings table = 2 tables
    expect(w.findAll('table').length).toBe(2)
```
The "already matches" test is unchanged (one table, "already matches").

- [ ] **Step 2:** `npm run test -- schedule-compare` → FAIL.

- [ ] **Step 3: Edit `ScheduleCompare.vue`.** Add the import:
```ts
import ScheduleSettings from './ScheduleSettings.vue'
```
Change the current ScheduleTable title to "Today's plan" and replace the recommended `ScheduleTable` with `ScheduleSettings`:
```html
    <div class="cmp__tables">
      <ScheduleTable :slots="current" title="Today's plan" />
      <ScheduleSettings v-if="!matches" :current="current" :recommended="recommended" />
    </div>
```
(The `ScheduleTable` import stays — still used for the current schedule.)

- [ ] **Step 4:** `npm run test -- schedule-compare` → PASS. `npx eslint --fix src/components/ScheduleCompare.vue`.

- [ ] **Step 5: Commit**
```bash
git add src/components/ScheduleCompare.vue tests/schedule-compare.test.ts
git commit -m "feat(fe): show recommended schedule as an inverter settings sheet"
```

---

## Group 2 — Forecast tile + gate

### Task 3: Solar forecast tile

**Files:** Modify `src/components/LiveTiles.vue`; Test `tests/components.test.ts`.

- [ ] **Step 1: Write the failing test** (append to the existing `describe('LiveTiles ...', ...)` block in `tests/components.test.ts`; its `dash()` helper returns a full `DashboardView` — confirm it has `expected_pv_kwh_today`/`expected_pv_kwh_tomorrow`; if not, add them to the helper, e.g. `expected_pv_kwh_today: 10.9, expected_pv_kwh_tomorrow: 12.4`):
```ts
  it('shows a solar forecast tile with today and tomorrow', () => {
    const w = mount(LiveTiles, {
      props: { dashboard: dash({ expected_pv_kwh_today: 10.9, expected_pv_kwh_tomorrow: 12.4 }) },
    })
    expect(w.text().toLowerCase()).toContain('forecast')
    expect(w.text()).toContain('10.9')
    expect(w.text().toLowerCase()).toContain('tomorrow')
  })
```

- [ ] **Step 2:** `npm run test -- components` → FAIL.

- [ ] **Step 3: Implement** in `LiveTiles.vue`:
- Extend the format import to include `formatKwh`: `import { formatKwh, formatPercent, formatPower } from '../lib/format'`.
- Add a Solar forecast tile inside the `<section class="tiles">`, after the Conversion tile (or after Load), before `</section>`:
```html
    <article class="tile" data-tone="solar">
      <header class="tile__head">
        <span class="tile__icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8">
            <path d="M3 12h2M19 12h2M12 3v2M5.6 5.6l1.4 1.4M17 17l1.4 1.4" stroke-linecap="round" />
            <path d="M8 18a4 4 0 0 1 8 0" stroke-linecap="round" />
            <path d="M12 9a3 3 0 0 0-3 3h6a3 3 0 0 0-3-3Z" />
          </svg>
        </span>
        <span class="tile__label">Solar forecast</span>
      </header>
      <p class="tile__value">{{ formatKwh(dashboard.expected_pv_kwh_today) }}</p>
      <p class="tile__sub">{{ formatKwh(dashboard.expected_pv_kwh_tomorrow) }} tomorrow</p>
    </article>
```

- [ ] **Step 4:** `npm run test -- components` → PASS. `npx eslint --fix src/components/LiveTiles.vue`.

- [ ] **Step 5: Commit**
```bash
git add src/components/LiveTiles.vue tests/components.test.ts
git commit -m "feat(fe): add a solar forecast tile (today + tomorrow kWh)"
```

### Task 4: Full gate

- [ ] **Step 1:** `npm run check` (lint → typecheck → test → build). All pass, **0 lint warnings** (`npx eslint --fix` any flagged file). Fix anything for files in this plan; re-run until green.
- [ ] **Step 2: Commit** any fixes:
```bash
git add -A && git commit -m "chore(fe): satisfy gate for settings sheet & forecast tile"
```

---

## Self-Review

**Spec coverage:** O1 `ScheduleSettings` → Task 1; O2 `ScheduleCompare` rewire → Task 2; O3 forecast tile → Task 3. ✓

**Placeholder scan:** the LiveTiles test defers to the file's `dash()` helper shape — the implementer confirms/extends `expected_pv_kwh_today`/`tomorrow`; all component code is complete.

**Type consistency:** `ScheduleSettings` props `current`/`recommended: SlotView[]` ← `ScheduleCompare`'s `current`/`recommended`; `target_soc:int`/`grid_charge:bool` read from `SlotView`; forecast tile reads `dashboard.expected_pv_kwh_today`/`expected_pv_kwh_tomorrow` (already on `DashboardView`); `formatKwh`/`formatPercent` exist in `lib/format`. `data-test` hooks (`soc-{i}`/`charge-{i}`) match between component and test. The schedule-compare table count stays 2 in the differ case (current `ScheduleTable` + `ScheduleSettings` table). ✓
