# Plan I — Dashboard & Purchases Polish (Frontend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add chart hover tooltips, a collapsible purchase form, battery-flow + conversion tiles, a 24h/7d/30d history range with a battery chart, inline purchase editing, and fix the rate-chart dropoff and table alignment.

**Architecture:** Consume the new backend fields (`battery_power`, `conversion_power` on the dashboard; `battery_power` on history; `PUT /api/purchases/{id}`). Hand-rolled SVG hover tooltips (no chart lib). Inline edit in the purchase table. Decouple history fetching from the 10s dashboard poll.

**Tech Stack:** Vue 3 `<script setup lang="ts">`, TS strict, Vitest + @vue/test-utils, ESLint flat + Prettier (no semicolons, single quotes, 2-space indent).

**Reference (read first):** spec `docs/superpowers/specs/2026-06-26-dashboard-purchases-polish-design.md`. Backend (merged): `/api/dashboard` now returns `battery_power` + `conversion_power`; `/api/history?hours=` accepts up to 720 and each point has `battery_power`; `PUT /api/purchases/{id}` edits (200 / 404 / 422). Mirror existing patterns: `src/components/TrendChart.vue`, `PurchaseCharts.vue`, `LiveTiles.vue`, `PurchaseTable.vue`, `src/views/Dashboard.vue`, `Purchases.vue`, `src/api/{types,client}.ts`. **All commands run from `frontend/`. Bootstrap once with `npm install` if `node_modules` is absent.** After editing any `.vue`, run `npx eslint --fix <file>` to keep attribute ordering clean. `npm run check` = lint → typecheck → test → build.

---

## File Structure

| File | Change |
|------|--------|
| `src/api/types.ts` | `DashboardView` += `battery_power`, `conversion_power`; `HistoryPoint` += `battery_power`. |
| `src/api/client.ts` | add `updatePurchase(id, body)`. |
| `src/components/LiveTiles.vue` | battery charge/discharge sub-line; new Conversion/idle tile. |
| `src/components/PurchaseCharts.vue` | pad rate y-domain (dropoff fix); hover tooltips. |
| `src/components/TrendChart.vue` | hover tooltips. |
| `src/components/PurchaseTable.vue` | right-align numeric headers; inline edit. |
| `src/views/Purchases.vue` | collapsible form; wire `@update`. |
| `src/views/Dashboard.vue` | 24h/7d/30d range selector; battery-power chart; decoupled history polling. |
| tests | `client.test.ts`, `components.test.ts`, `purchase-charts.test.ts`, `purchase-table.test.ts`, `trend-chart.test.ts`, `dashboard.test.ts`, `purchases-view.test.ts`. |

---

## Group 1 — Types + client

### Task 1: Types for new fields

**Files:** Modify `src/api/types.ts`.

- [ ] **Step 1:** In `DashboardView`, add after `load_power: number`:
```ts
  load_power: number
  battery_power: number
  conversion_power: number
```
In `HistoryPoint`, add after `load_power: number`:
```ts
  load_power: number
  battery_power: number
```

- [ ] **Step 2:** `npm run typecheck` — passes.

- [ ] **Step 3: Commit**
```bash
git add src/api/types.ts
git commit -m "feat(fe): add battery_power/conversion_power and history battery_power types"
```

### Task 2: `updatePurchase` client call

**Files:** Modify `src/api/client.ts`; Test `tests/client.test.ts`.

- [ ] **Step 1: Write the failing test** (append inside `describe('api client', ...)`; extend the import at the top to include `updatePurchase`):
```ts
  it('updatePurchase PUTs the body to the id and returns the row', async () => {
    const fetchMock = mockFetch(200, { id: 5, rand: 900 })
    vi.stubGlobal('fetch', fetchMock)
    const updated = await updatePurchase(5, {
      purchased_at: '2026-06-02',
      rand: 900,
      units_kwh: 300,
    })
    expect(updated.id).toBe(5)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toContain('/api/purchases/5')
    expect(init).toMatchObject({ method: 'PUT' })
    expect(JSON.parse((init as RequestInit).body as string)).toMatchObject({ rand: 900 })
  })
```

- [ ] **Step 2:** `npm run test -- client` → FAIL (no `updatePurchase`).

- [ ] **Step 3: Implement.** In `src/api/client.ts`, append (mirrors `createPurchase`, reuses `failure`):
```ts
export async function updatePurchase(id: number, body: PurchaseCreate): Promise<PurchaseView> {
  const resp = await fetch(`${BASE}/api/purchases/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!resp.ok) throw await failure(resp)
  return (await resp.json()) as PurchaseView
}
```

- [ ] **Step 4:** `npm run test -- client` → PASS.

- [ ] **Step 5: Commit**
```bash
git add src/api/client.ts tests/client.test.ts
git commit -m "feat(fe): add updatePurchase client call (PUT)"
```

---

## Group 2 — Tiles, alignment, dropoff fix

### Task 3: Battery-flow + Conversion tiles

**Files:** Modify `src/components/LiveTiles.vue`; Test `tests/components.test.ts`.

- [ ] **Step 1: Write the failing test** (append to `tests/components.test.ts`; it already uses `mount`):
```ts
import LiveTiles from '../src/components/LiveTiles.vue'
import type { DashboardView } from '../src/api/types'

function dash(over: Partial<DashboardView> = {}): DashboardView {
  return {
    objective: 0.5,
    battery_soc: 75,
    pv_power: 0,
    grid_power: 656,
    load_power: 600,
    battery_power: 420,
    conversion_power: 30,
    month_to_date_grid_import_kwh: 100,
    usable_kwh: 15,
    usable_kwh_confidence: 0.6,
    daily_consumption_kwh: 24,
    daily_consumption_confidence: 0.5,
    tariff_rate: 3.56,
    tariff_source: 'config',
    tariff_source_date: null,
    expected_pv_kwh_today: 20,
    expected_pv_kwh_tomorrow: 20,
    slots: [],
    recommendation: {
      reserve_target_soc: 40,
      enable_overnight_grid_charge: false,
      grid_charge_kwh: 0,
      expected_daily_grid_import_kwh: 3,
      expected_daily_cost: 12,
      backup_hours: 8,
      monthly_cost_so_far: 100,
    },
    disclaimer: 'x',
    ...over,
  }
}

describe('LiveTiles battery flow + conversion', () => {
  it('shows charging when battery_power > 0', () => {
    const w = mount(LiveTiles, { props: { dashboard: dash({ battery_power: 420 }) } })
    expect(w.text().toLowerCase()).toContain('charging')
  })

  it('shows discharging when battery_power < 0', () => {
    const w = mount(LiveTiles, { props: { dashboard: dash({ battery_power: -300 }) } })
    expect(w.text().toLowerCase()).toContain('discharging')
  })

  it('renders a conversion tile clamped at 0 for negative residual', () => {
    const w = mount(LiveTiles, { props: { dashboard: dash({ conversion_power: -12 }) } })
    expect(w.text().toLowerCase()).toContain('conversion')
    expect(w.text()).toContain('0 W')
  })
})
```

- [ ] **Step 2:** `npm run test -- components` → FAIL.

- [ ] **Step 3: Implement** in `src/components/LiveTiles.vue`:

In `<script setup>`, add computeds after the existing ones:
```ts
const batteryFlow = computed(() => {
  const p = props.dashboard.battery_power
  if (p > 1) return `charging ${Math.round(p)} W`
  if (p < -1) return `discharging ${Math.round(-p)} W`
  return 'idle'
})

const conversion = computed(() => Math.max(0, Math.round(props.dashboard.conversion_power)))
```

In the Battery tile, replace the existing `<p class="tile__sub">state of charge</p>` line with a flow sub-line:
```html
        <p class="tile__sub">{{ batteryFlow }}</p>
```

Add a new Conversion tile at the end of the tiles section (after the Load `</article>`, before the closing `</section>`):
```html
    <article class="tile" data-tone="neutral">
      <header class="tile__head">
        <span class="tile__icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8">
            <path d="M12 3v18M5 8l7-5 7 5M5 16l7 5 7-5" stroke-linejoin="round" />
          </svg>
        </span>
        <span class="tile__label">Conversion / idle</span>
      </header>
      <p class="tile__value">{{ formatPower(conversion) }}</p>
      <p class="tile__sub">inverter overhead + losses</p>
    </article>
```

(`formatPower` is already imported. If `formatPower(conversion)` renders e.g. "30 W"; for the clamped-negative case it renders "0 W", satisfying the test.)

- [ ] **Step 4:** `npm run test -- components` → PASS. Then `npx eslint --fix src/components/LiveTiles.vue`.

- [ ] **Step 5: Commit**
```bash
git add src/components/LiveTiles.vue tests/components.test.ts
git commit -m "feat(fe): battery charge/discharge sub-line and conversion/idle tile"
```

### Task 4: Table header alignment + rate-chart dropoff fix

**Files:** Modify `src/components/PurchaseTable.vue`, `src/components/PurchaseCharts.vue`; Test `tests/purchase-charts.test.ts`.

- [ ] **Step 1 (alignment, no test — pure CSS):** In `PurchaseTable.vue`, give the numeric headers a right-aligned class. Change the `<thead>` row to:
```html
        <tr>
          <th>Date</th>
          <th class="pt__th-num">Paid</th>
          <th class="pt__th-num">Units</th>
          <th class="pt__th-num">Rate</th>
          <th>Note</th>
          <th aria-label="actions" />
        </tr>
```
Add to `<style scoped>`:
```css
.pt__th-num {
  text-align: right;
}
```

- [ ] **Step 2: Write the failing dropoff test** (append to `tests/purchase-charts.test.ts`):
```ts
it('keeps the lowest rate off the chart baseline (no false zero)', () => {
  // Newest purchase is the cheapest → would hug the baseline without padding.
  const rising = [
    { id: 2, purchased_at: '2026-06-15', rand: 1000, units_kwh: 320, note: null, effective_rate: 3.125 },
    { id: 1, purchased_at: '2026-05-01', rand: 1000, units_kwh: 250, note: null, effective_rate: 4.0 },
  ]
  const w = mount(PurchaseCharts, { props: { purchases: rising, currentRate: 3.125 } })
  const pts = w.get('[data-test="rate-line"]').attributes('points') as string
  const ys = pts.split(' ').map((pair) => Number(pair.split(',')[1]))
  // viewBox H=110, PAD=10 → baseline y=100. Padding must keep all points strictly above it.
  expect(Math.max(...ys)).toBeLessThan(100)
})
```

- [ ] **Step 3:** `npm run test -- purchase-charts` → the new test FAILS (lowest point sits at y=100).

- [ ] **Step 4: Implement the padding.** In `PurchaseCharts.vue` `rateGeom`, change the min/max block to add headroom:
```ts
  let min = Math.min(...all)
  let max = Math.max(...all)
  if (min === max) {
    min -= 0.5
    max += 0.5
  } else {
    const pad = (max - min) * 0.08
    min -= pad
    max += pad
  }
```

- [ ] **Step 5:** `npm run test -- purchase-charts` → PASS. `npx eslint --fix src/components/PurchaseTable.vue src/components/PurchaseCharts.vue`.

- [ ] **Step 6: Commit**
```bash
git add src/components/PurchaseTable.vue src/components/PurchaseCharts.vue tests/purchase-charts.test.ts
git commit -m "fix(fe): right-align numeric table headers; pad rate chart so min floats off baseline"
```

---

## Group 3 — Hover tooltips

### Task 5: TrendChart tooltip

**Files:** Modify `src/components/TrendChart.vue`; Test `tests/trend-chart.test.ts`.

- [ ] **Step 1: Write the failing test** (append to `tests/trend-chart.test.ts`; it already mounts TrendChart with points):
```ts
it('shows a tooltip with the value on pointer move and hides on leave', async () => {
  const points = [
    { ts: '2026-06-26T08:00:00+00:00', battery_soc: 40, pv_power: 0, grid_power: 0, load_power: 0 },
    { ts: '2026-06-26T12:00:00+00:00', battery_soc: 90, pv_power: 0, grid_power: 0, load_power: 0 },
  ]
  const w = mount(TrendChart, { props: { points, metric: 'battery_soc', label: 'Battery SOC', unit: '%' } })
  const svg = w.get('svg.chart__svg')
  // jsdom getBoundingClientRect returns zeros; with rel=0 the snapped index is 0.
  await svg.trigger('pointermove', { clientX: 0 })
  expect(w.find('[data-test="chart-tip"]').exists()).toBe(true)
  await svg.trigger('pointerleave')
  expect(w.find('[data-test="chart-tip"]').exists()).toBe(false)
})
```

- [ ] **Step 2:** `npm run test -- trend-chart` → FAIL.

- [ ] **Step 3: Implement.** In `TrendChart.vue` `<script setup>`, add hover state + handlers + a time formatter (place after the existing computeds):
```ts
const hover = ref<number | null>(null)

function onMove(e: PointerEvent): void {
  const n = props.points.length
  if (!n) return
  const rect = (e.currentTarget as SVGGraphicsElement).getBoundingClientRect()
  const rel = rect.width > 0 ? (e.clientX - rect.left) / rect.width : 0
  hover.value = Math.max(0, Math.min(n - 1, Math.round(rel * (n - 1))))
}

function onLeave(): void {
  hover.value = null
}

const hoverPoint = computed(() => (hover.value === null ? null : project(hover.value)))

const hoverLabel = computed(() => {
  if (hover.value === null) return ''
  const p = props.points[hover.value]
  const d = new Date(p.ts)
  const t = d.toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
  return `${fmtLatest(values.value[hover.value])} · ${t}`
})
```
(`ref` is already imported via `vue`? It imports `computed` only — change the import to `import { computed, ref } from 'vue'`.)

In the template, make the `<figure>` the positioning context and add the interaction. Add `@pointermove="onMove"` and `@pointerleave="onLeave"` to the `<svg class="chart__svg" ...>`. Inside that `<svg>`, after the `<circle v-if="lastPoint" ...>`, add a hover marker:
```html
      <line
        v-if="hoverPoint"
        :x1="hoverPoint.x"
        :x2="hoverPoint.x"
        :y1="PAD"
        :y2="H - PAD"
        stroke="var(--sa-text-dim, #9aa6b6)"
        stroke-width="1"
        stroke-dasharray="3 3"
        vector-effect="non-scaling-stroke"
      />
      <circle v-if="hoverPoint" :cx="hoverPoint.x" :cy="hoverPoint.y" r="3.5" :fill="`var(--line, #5aa9ff)`" />
```
After the `</svg>`, still inside the `<figure>`, add the tooltip:
```html
    <div
      v-if="hoverPoint"
      data-test="chart-tip"
      class="chart__tip"
      :style="{ left: `${(hoverPoint.x / W) * 100}%` }"
    >
      {{ hoverLabel }}
    </div>
```
Expose `PAD`, `H`, `W` to the template (they are top-level `const` in setup, so already available). Add CSS to `<style scoped>`:
```css
.chart {
  position: relative;
}
.chart__tip {
  position: absolute;
  top: 1.6rem;
  transform: translateX(-50%);
  padding: 0.2rem 0.45rem;
  border-radius: 6px;
  background: var(--sa-bg, #0f141b);
  border: 1px solid var(--sa-line, #273140);
  color: var(--sa-text, #eef2f7);
  font-size: 0.72rem;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  pointer-events: none;
}
```

- [ ] **Step 4:** `npm run test -- trend-chart` → PASS. `npx eslint --fix src/components/TrendChart.vue`.

- [ ] **Step 5: Commit**
```bash
git add src/components/TrendChart.vue tests/trend-chart.test.ts
git commit -m "feat(fe): hover tooltip on trend charts"
```

### Task 6: PurchaseCharts tooltip

**Files:** Modify `src/components/PurchaseCharts.vue`; Test `tests/purchase-charts.test.ts`.

- [ ] **Step 1: Write the failing test** (append to `tests/purchase-charts.test.ts`; reuses the module's `purchases` fixture):
```ts
it('shows a rate tooltip on pointer move over the rate chart', async () => {
  const w = mount(PurchaseCharts, { props: { purchases, currentRate: 3.3 } })
  await w.get('[data-test="rate-svg"]').trigger('pointermove', { clientX: 0 })
  expect(w.find('[data-test="pc-tip"]').exists()).toBe(true)
})
```
(`purchases` is the array already defined at the top of this test file.)

- [ ] **Step 2:** `npm run test -- purchase-charts` → FAIL (no `rate-svg`/`pc-tip`).

- [ ] **Step 3: Implement.** In `PurchaseCharts.vue` `<script setup>` add a shared hover index over the chronological series + handlers + label helpers:
```ts
import { computed, ref } from 'vue'
// ...existing imports/props...
import { formatDate, formatRand, formatRatePerKwh, formatUnits } from '../lib/format'

const hover = ref<number | null>(null)

function onMove(e: PointerEvent): void {
  const n = chrono.value.length
  if (!n) return
  const rect = (e.currentTarget as SVGGraphicsElement).getBoundingClientRect()
  const rel = rect.width > 0 ? (e.clientX - rect.left) / rect.width : 0
  hover.value = Math.max(0, Math.min(n - 1, Math.round(rel * (n - 1))))
}

function onLeave(): void {
  hover.value = null
}

const hoverX = computed(() => (hover.value === null ? 0 : xFor(hover.value, chrono.value.length)))
const hoverItem = computed(() => (hover.value === null ? null : chrono.value[hover.value]))
```
(The file currently imports only `formatRatePerKwh` — extend it to also import `formatDate`, `formatRand`, `formatUnits` as shown.)

In the template, on the **rate** chart `<svg>` add `data-test="rate-svg"`, `@pointermove="onMove"`, `@pointerleave="onLeave"`, and after the `<polyline data-test="rate-line" ...>` add a hover guide:
```html
        <line
          v-if="hoverItem"
          :x1="hoverX"
          :x2="hoverX"
          :y1="PAD"
          :y2="H - PAD"
          stroke="var(--sa-text-dim, #9aa6b6)"
          stroke-width="1"
          stroke-dasharray="3 3"
          vector-effect="non-scaling-stroke"
        />
```
Right after that rate chart's `</svg>` (inside its `<figure class="pc__chart">`), add the tooltip:
```html
        <div
          v-if="hoverItem"
          data-test="pc-tip"
          class="pc__tip"
          :style="{ left: `${(hoverX / W) * 100}%` }"
        >
          {{ formatRatePerKwh(hoverItem.effective_rate) }} · {{ formatDate(hoverItem.purchased_at) }}
        </div>
```
Make that `<figure>` positioned and add the tip style. Add to `<style scoped>`:
```css
.pc__chart {
  position: relative;
}
.pc__tip {
  position: absolute;
  top: 1.4rem;
  transform: translateX(-50%);
  padding: 0.2rem 0.45rem;
  border-radius: 6px;
  background: var(--sa-bg, #0f141b);
  border: 1px solid var(--sa-line, #273140);
  color: var(--sa-text, #eef2f7);
  font-size: 0.72rem;
  white-space: nowrap;
  pointer-events: none;
}
```
(Optional but nice: apply `@pointermove`/`@pointerleave` + `data-test="spend-svg"`/`"units-svg"` to the spend and units `<svg>`s too, each with their own tip using `formatRand(hoverItem.rand)` / `formatUnits(hoverItem.units_kwh)`. Only the rate chart is required by the test; add the others for consistency if straightforward.)

- [ ] **Step 4:** `npm run test -- purchase-charts` → PASS. `npx eslint --fix src/components/PurchaseCharts.vue`.

- [ ] **Step 5: Commit**
```bash
git add src/components/PurchaseCharts.vue tests/purchase-charts.test.ts
git commit -m "feat(fe): hover tooltip on purchase charts"
```

---

## Group 4 — History range selector + battery chart + decoupled polling

### Task 7: Dashboard range selector, battery-power chart, throttled history fetch

**Files:** Modify `src/views/Dashboard.vue`; Test `tests/dashboard.test.ts`.

- [ ] **Step 1: Write the failing test.** First read `tests/dashboard.test.ts` to match its mocking of the client. Add a test that selecting a range calls `getHistory` with the mapped hours. Use the file's existing mock setup; the essence:
```ts
it('refetches history with the selected range', async () => {
  // (Use the file's existing client mock; getHistory is mocked.)
  // mount Dashboard, wait for initial load, click the "30d" range button,
  // assert the history client was called with 720.
  // See existing dashboard.test.ts for the mock/clock pattern; mirror it.
})
```
Implement it concretely against the existing mock harness in `dashboard.test.ts` (assert `getHistory` called with `720` after clicking `[data-test="range-720"]`).

- [ ] **Step 2:** `npm run test -- dashboard` → FAIL.

- [ ] **Step 3: Implement** in `src/views/Dashboard.vue`:

Replace the single `HISTORY_HOURS` constant and history wiring. In `<script setup>`:
- Add a range ref + a 60s history timer, decoupled from the 10s `POLL_MS`:
```ts
const HISTORY_POLL_MS = 60_000
const historyHours = ref(24)
```
- Change `fetchHistory` to use `historyHours.value`:
```ts
async function fetchHistory(): Promise<void> {
  try {
    const view = await getHistory(historyHours.value)
    history.value = view.points
  } catch {
    // History is non-critical; leave the last good series in place.
  }
}
```
- Remove `fetchHistory` from the 10s `refreshAll` (keep only `fetchDashboard` there); drive history separately. Update lifecycle:
```ts
function refreshAll(): void {
  void fetchDashboard()
}

watch(historyHours, () => {
  void fetchHistory()
})

let historyTimer: ReturnType<typeof setInterval> | undefined

onMounted(() => {
  refreshAll()
  void fetchHistory()
  pollTimer = setInterval(refreshAll, POLL_MS)
  historyTimer = setInterval(() => void fetchHistory(), HISTORY_POLL_MS)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (debounceTimer) clearTimeout(debounceTimer)
  if (historyTimer) clearInterval(historyTimer)
})
```
(Keep the existing `objective` watch/debounce untouched.)

In the template, above the charts grid (inside the history `<section>`, before `<div class="dash__charts">`), add the range selector and a battery-power chart. Replace the history-section header block with:
```html
            <section class="dash__history" aria-label="Recent history">
              <div class="dash__history-head">
                <h2 class="dash__history-title">History</h2>
                <div class="dash__range" role="group" aria-label="History range">
                  <button
                    v-for="r in [{ h: 24, label: '24h' }, { h: 168, label: '7d' }, { h: 720, label: '30d' }]"
                    :key="r.h"
                    class="dash__range-btn"
                    :data-test="`range-${r.h}`"
                    :data-active="historyHours === r.h"
                    @click="historyHours = r.h"
                  >
                    {{ r.label }}
                  </button>
                </div>
              </div>
              <div class="dash__charts">
                <TrendChart :points="history" metric="battery_soc" label="Battery SOC" unit="%" />
                <TrendChart :points="history" metric="pv_power" label="Solar" unit="W" />
                <TrendChart :points="history" metric="grid_power" label="Grid" unit="W" />
                <TrendChart :points="history" metric="load_power" label="Load" unit="W" />
                <TrendChart :points="history" metric="battery_power" label="Battery flow" unit="W" />
              </div>
            </section>
```
For the new `battery_power` metric to typecheck, update `TrendChart.vue`'s `Metric` type to include it:
```ts
type Metric = 'battery_soc' | 'pv_power' | 'grid_power' | 'load_power' | 'battery_power'
```
Add range-selector styles to Dashboard's `<style scoped>`:
```css
.dash__history-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.9rem;
}
.dash__range {
  display: inline-flex;
  gap: 0.25rem;
}
.dash__range-btn {
  padding: 0.25rem 0.6rem;
  border-radius: 8px;
  border: 1px solid var(--sa-line, #273140);
  background: transparent;
  color: var(--sa-text-dim, #9aa6b6);
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
}
.dash__range-btn[data-active='true'] {
  color: var(--sa-text, #eef2f7);
  border-color: var(--sa-accent, #5aa9ff);
}
```
(Remove the old standalone `.dash__history-title` margin if it now double-applies; keep styling coherent.)

- [ ] **Step 4:** `npm run test -- dashboard` → PASS. `npx eslint --fix src/views/Dashboard.vue src/components/TrendChart.vue`.

- [ ] **Step 5: Commit**
```bash
git add src/views/Dashboard.vue src/components/TrendChart.vue tests/dashboard.test.ts
git commit -m "feat(fe): history range selector (24h/7d/30d), battery-flow chart, throttled history fetch"
```

---

## Group 5 — Collapsible form + inline edit + gate

### Task 8: Collapsible "Log a purchase"

**Files:** Modify `src/views/Purchases.vue`; Test `tests/purchases-view.test.ts`.

- [ ] **Step 1: Write the failing test** (append to `tests/purchases-view.test.ts`; reuses its mock of `../src/api/client`):
```ts
it('keeps the log form collapsed until the button is clicked', async () => {
  getPurchases.mockResolvedValue({ purchases: [] })
  getDashboard.mockResolvedValue({ tariff_rate: 3.56, tariff_source: 'config', tariff_source_date: null })
  const w = mount(Purchases)
  await flushPromises()
  expect(w.findComponent({ name: 'PurchaseForm' }).exists()).toBe(false)
  await w.get('[data-test="toggle-form"]').trigger('click')
  expect(w.findComponent({ name: 'PurchaseForm' }).exists()).toBe(true)
})
```
(If `findComponent({ name: ... })` is unreliable, assert on a stable element the form renders, e.g. `w.find('form.pf').exists()`. Prefer the `form.pf` selector.)

Rewrite the assertions to use `w.find('form.pf')`:
```ts
  expect(w.find('form.pf').exists()).toBe(false)
  await w.get('[data-test="toggle-form"]').trigger('click')
  expect(w.find('form.pf').exists()).toBe(true)
```

- [ ] **Step 2:** `npm run test -- purchases-view` → FAIL.

- [ ] **Step 3: Implement** in `src/views/Purchases.vue`:
- Add `import { onMounted, ref } from 'vue'` already present; add a `showForm` ref:
```ts
const showForm = ref(false)
```
- On successful create, collapse + refresh:
```ts
async function onCreated(): Promise<void> {
  showForm.value = false
  await refresh()
}
```
- In the template, replace `<PurchaseForm @created="refresh" />` with a toggle + conditional form:
```html
      <div class="pv__formbar">
        <button class="pv__toggle" data-test="toggle-form" @click="showForm = !showForm">
          {{ showForm ? '× Close' : '+ Log a purchase' }}
        </button>
      </div>
      <PurchaseForm v-if="showForm" @created="onCreated" />
```
- Add styles:
```css
.pv__formbar {
  display: flex;
}
.pv__toggle {
  padding: 0.5rem 0.9rem;
  border-radius: 10px;
  border: 1px solid var(--sa-accent, #5aa9ff);
  background: transparent;
  color: var(--sa-accent, #5aa9ff);
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
}
```

- [ ] **Step 4:** `npm run test -- purchases-view` → PASS. `npx eslint --fix src/views/Purchases.vue`.

- [ ] **Step 5: Commit**
```bash
git add src/views/Purchases.vue tests/purchases-view.test.ts
git commit -m "feat(fe): collapse the log-a-purchase form behind a button"
```

### Task 9: Inline edit in the purchase table

**Files:** Modify `src/components/PurchaseTable.vue`, `src/views/Purchases.vue`; Test `tests/purchase-table.test.ts`, `tests/purchases-view.test.ts`.

- [ ] **Step 1: Write the failing tests.**

Append to `tests/purchase-table.test.ts`:
```ts
it('enters edit mode and emits update with the edited body', async () => {
  const w = mount(PurchaseTable, { props: { purchases } })
  await w.get('[data-test="edit-1"]').trigger('click')
  // inputs appear for the edited row
  await w.get('[data-test="edit-rand-1"]').setValue('1200')
  await w.get('[data-test="edit-units-1"]').setValue('300')
  await w.get('[data-test="save-1"]').trigger('click')
  const ev = w.emitted('update')?.[0]?.[0] as { id: number; body: Record<string, unknown> }
  expect(ev.id).toBe(1)
  expect(ev.body).toMatchObject({ rand: 1200, units_kwh: 300 })
})

it('cancel exits edit mode without emitting', async () => {
  const w = mount(PurchaseTable, { props: { purchases } })
  await w.get('[data-test="edit-1"]').trigger('click')
  await w.get('[data-test="cancel-edit-1"]').trigger('click')
  expect(w.emitted('update')).toBeFalsy()
  expect(w.find('[data-test="edit-rand-1"]').exists()).toBe(false)
})
```
(`purchases` in that file includes a row with `id: 1`.)

Append to `tests/purchases-view.test.ts` (reuses the client mock — add `updatePurchase` to the mock):
```ts
it('calls updatePurchase and refreshes on row update', async () => {
  getPurchases.mockResolvedValue({
    purchases: [
      { id: 1, purchased_at: '2026-06-01', rand: 1000, units_kwh: 250, note: null, effective_rate: 4 },
    ],
  })
  getDashboard.mockResolvedValue({ tariff_rate: 3.56, tariff_source: 'config', tariff_source_date: null })
  const w = mount(Purchases)
  await flushPromises()
  getPurchases.mockClear()
  await w.get('[data-test="edit-1"]').trigger('click')
  await w.get('[data-test="save-1"]').trigger('click')
  await flushPromises()
  expect(updatePurchase).toHaveBeenCalled()
  expect(getPurchases).toHaveBeenCalled()
})
```
Update that test file's `vi.mock('../src/api/client', ...)` to also export `updatePurchase: (id: number, body: unknown) => updatePurchase(id, body)` with a module-level `const updatePurchase = vi.fn().mockResolvedValue({})` (mirror the existing `deletePurchase` mock pattern).

- [ ] **Step 2:** `npm run test -- purchase-table purchases-view` → FAIL.

- [ ] **Step 3: Implement the table edit mode.** Rewrite `src/components/PurchaseTable.vue` to support an editing row. Full `<script setup>`:
```ts
import { ref } from 'vue'
import type { PurchaseView } from '../api/types'
import { formatDate, formatRand, formatRatePerKwh, formatUnits } from '../lib/format'

defineProps<{ purchases: PurchaseView[] }>()
const emit = defineEmits<{
  delete: [id: number]
  update: [payload: { id: number; body: { purchased_at: string; rand: number; units_kwh: number; note: string | null } }]
}>()

const confirmingId = ref<number | null>(null)
const editingId = ref<number | null>(null)
const editDate = ref('')
const editRand = ref('')
const editUnits = ref('')
const editNote = ref('')
const editError = ref('')

function arm(id: number): void {
  confirmingId.value = id
}
function cancel(): void {
  confirmingId.value = null
}
function confirm(id: number): void {
  emit('delete', id)
  confirmingId.value = null
}

function startEdit(p: PurchaseView): void {
  editingId.value = p.id
  editDate.value = p.purchased_at
  editRand.value = String(p.rand)
  editUnits.value = String(p.units_kwh)
  editNote.value = p.note ?? ''
  editError.value = ''
}
function cancelEdit(): void {
  editingId.value = null
  editError.value = ''
}
function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}
function saveEdit(id: number): void {
  const rand = Number(editRand.value)
  const units = Number(editUnits.value)
  if (!editDate.value || editDate.value > todayIso()) {
    editError.value = 'Date cannot be in the future.'
    return
  }
  if (!(rand > 0) || !(units > 0)) {
    editError.value = 'Rand and units must be greater than 0.'
    return
  }
  emit('update', {
    id,
    body: { purchased_at: editDate.value, rand, units_kwh: units, note: editNote.value.trim() || null },
  })
  editingId.value = null
  editError.value = ''
}
```
Full `<template>` table body — replace the `<tbody>` with a version that swaps to inputs for the editing row:
```html
      <tbody>
        <tr v-for="p in purchases" :key="p.id">
          <template v-if="editingId === p.id">
            <td><input type="date" :max="todayIso()" :data-test="`edit-date-${p.id}`" v-model="editDate" /></td>
            <td><input type="number" min="0" step="0.01" :data-test="`edit-rand-${p.id}`" v-model="editRand" /></td>
            <td><input type="number" min="0" step="0.01" :data-test="`edit-units-${p.id}`" v-model="editUnits" /></td>
            <td class="pt__num pt__rate">—</td>
            <td><input type="text" :data-test="`edit-note-${p.id}`" v-model="editNote" /></td>
            <td class="pt__actions">
              <button class="pt__btn" :data-test="`save-${p.id}`" @click="saveEdit(p.id)">Save</button>
              <button class="pt__btn" :data-test="`cancel-edit-${p.id}`" @click="cancelEdit">Cancel</button>
            </td>
          </template>
          <template v-else>
            <td>{{ formatDate(p.purchased_at) }}</td>
            <td class="pt__num">{{ formatRand(p.rand) }}</td>
            <td class="pt__num">{{ formatUnits(p.units_kwh) }}</td>
            <td class="pt__num pt__rate">{{ formatRatePerKwh(p.effective_rate) }}</td>
            <td class="pt__note">{{ p.note ?? '' }}</td>
            <td class="pt__actions">
              <template v-if="confirmingId === p.id">
                <button class="pt__btn pt__btn--danger" :data-test="`confirm-${p.id}`" @click="confirm(p.id)">
                  Confirm
                </button>
                <button class="pt__btn" @click="cancel">Cancel</button>
              </template>
              <template v-else>
                <button class="pt__btn" :data-test="`edit-${p.id}`" @click="startEdit(p)">Edit</button>
                <button class="pt__btn" :data-test="`del-${p.id}`" @click="arm(p.id)">Delete</button>
              </template>
            </td>
          </template>
        </tr>
      </tbody>
```
Add an inline error row under the table (after `</table>`, inside the section):
```html
    <p v-if="editError" class="pt__error" role="alert">{{ editError }}</p>
```
Add input + error styles to `<style scoped>`:
```css
.pt__table input {
  width: 100%;
  min-width: 0;
  padding: 0.3rem 0.4rem;
  border-radius: 6px;
  border: 1px solid var(--sa-line, #273140);
  background: var(--sa-bg, #0f141b);
  color: var(--sa-text, #eef2f7);
  font-size: 0.85rem;
}
.pt__error {
  margin: 0.6rem 0 0;
  font-size: 0.84rem;
  color: var(--sa-bad, #ef6b6b);
}
```

- [ ] **Step 4: Wire `@update` in `Purchases.vue`.** Add `updatePurchase` to the import from `../api/client`, and a handler:
```ts
async function onUpdate(payload: {
  id: number
  body: { purchased_at: string; rand: number; units_kwh: number; note: string | null }
}): Promise<void> {
  try {
    await updatePurchase(payload.id, payload.body)
    await refresh()
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : 'Could not update the purchase.'
  }
}
```
And on the table element: `<PurchaseTable :purchases="purchases" @delete="onDelete" @update="onUpdate" />`.

- [ ] **Step 5:** `npm run test -- purchase-table purchases-view` → PASS. `npx eslint --fix src/components/PurchaseTable.vue src/views/Purchases.vue`.

- [ ] **Step 6: Commit**
```bash
git add src/components/PurchaseTable.vue src/views/Purchases.vue tests/purchase-table.test.ts tests/purchases-view.test.ts
git commit -m "feat(fe): inline edit a purchase in the table"
```

### Task 10: Full gate

- [ ] **Step 1:** `npm run check` (lint → typecheck → test → build). All four stages pass; **0 lint warnings** (run `npx eslint --fix` on any flagged file). Fix anything failing for files in this plan; re-run until fully green.
- [ ] **Step 2: Commit** any gate fixes:
```bash
git add -A && git commit -m "chore(fe): satisfy gate for dashboard/purchases polish"
```

---

## Self-Review

**Spec coverage:** I1 tooltips → Tasks 5–6; I2 collapsible form → Task 8; I3 dropoff → Task 4; I4 alignment → Task 4; I5 tiles → Task 3; I6 range selector + battery chart + decoupled poll → Task 7; I7 inline edit → Tasks 1–2 (`updatePurchase`) + Task 9. ✓

**Placeholder scan:** the Dashboard test (Task 7 Step 1) and the collapsible test reference the file's existing mock harness — the implementer must read `tests/dashboard.test.ts`/`tests/purchases-view.test.ts` and mirror the established mock pattern; concrete assertions (`getHistory` called with 720; `form.pf` presence) are specified. All component code is complete.

**Type consistency:** `battery_power`/`conversion_power` added to `DashboardView` (Task 1) consumed by `LiveTiles` (Task 3); `HistoryPoint.battery_power` (Task 1) consumed by the new `TrendChart` metric `battery_power` (Task 7, `Metric` union updated); `updatePurchase(id, body: PurchaseCreate)` (Task 2) called from `Purchases.onUpdate` (Task 9); `PurchaseTable` emits `update: [{id, body}]` matching `onUpdate`'s param; `range-${h}` / `edit-${id}` / `save-${id}` / `cancel-edit-${id}` data-test hooks match between components and tests. ✓
