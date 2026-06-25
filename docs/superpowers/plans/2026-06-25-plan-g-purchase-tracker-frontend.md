# Plan G — Purchase Tracker Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the user a Purchases screen to log prepaid electricity buys (date, rand, units) with a live R/kWh preview, list/delete them, graph the price trend, and show the dashboard's tariff with its data provenance.

**Architecture:** A new `Purchases` view (reached via a simple two-tab nav in `App.vue`, since the app has no router) composes a self-submitting `PurchaseForm`, a `PurchaseTable` with inline delete-confirm, and hand-rolled SVG `PurchaseCharts`. The typed GET-only client gains its first write calls (`createPurchase`, `deletePurchase`) plus `getPurchases`. A small `TariffBadge` surfaces the derived rate + source on both the Purchases view and the dashboard. Components follow the existing presentational pattern; charts mirror `TrendChart.vue`'s projection approach.

**Tech Stack:** Vue 3 (`<script setup lang="ts">`), TypeScript strict, Vite, Vitest + @vue/test-utils, ESLint flat config + Prettier (no semicolons, single quotes, 2-space indent — match existing files).

**Reference (read before starting):** spec `docs/superpowers/specs/2026-06-25-purchase-tracker-design.md` (§6 frontend). Backend (already merged, Plan F) exposes: `POST /api/purchases` (body `{purchased_at, rand, units_kwh, note?}` → 201 `{id, purchased_at, rand, units_kwh, note, effective_rate}`; 422 on rand/units ≤ 0 or future date), `GET /api/purchases` → `{purchases: [...]}` newest-first, `DELETE /api/purchases/{id}` → 204 / 404; and `/api/dashboard` now returns `tariff_source: string` and `tariff_source_date: string | null`. Existing patterns to mirror: `frontend/src/api/client.ts`, `frontend/src/api/types.ts`, `frontend/src/components/TrendChart.vue` (SVG), `frontend/src/components/ExplainPanel.vue` (self-fetching component), `frontend/tests/client.test.ts`, `frontend/tests/components.test.ts`. All commands run from `frontend/`. Toolchain is already installed (`node_modules` present); if missing, run `npm install` first.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/api/types.ts` (modify) | Add `PurchaseCreate`, `PurchaseView`, `PurchaseListView`; add `tariff_source`/`tariff_source_date` to `DashboardView`. |
| `src/api/client.ts` (modify) | Add `getPurchases`, `createPurchase`, `deletePurchase`; shared error extractor handling FastAPI string- and array-`detail`. |
| `src/lib/format.ts` (modify) | Add `formatRatePerKwh`, `formatUnits`, `formatDate`. |
| `src/components/PurchaseForm.vue` (create) | Capture form with live effective-rate preview, client-side validation, self-submits, emits `created`. |
| `src/components/PurchaseTable.vue` (create) | Newest-first list with inline two-click delete-confirm; emits `delete`. |
| `src/components/TariffBadge.vue` (create) | Shows derived rate + provenance ("from purchase on …" vs "config default"). |
| `src/components/PurchaseCharts.vue` (create) | SVG charts: effective R/kWh over time (with current-rate reference line), rand spent, units received. |
| `src/views/Purchases.vue` (create) | Composes badge + form + table + charts; fetches purchases + dashboard; refetches on create/delete. |
| `src/App.vue` (modify) | Two-tab nav between Dashboard and Purchases. |
| `src/views/Dashboard.vue` (modify) | Add `TariffBadge` in the side column. |
| `tests/client.test.ts` (modify) | create/delete/list calls + 422 message extraction. |
| `tests/format.test.ts` (modify) | new formatters. |
| `tests/purchase-form.test.ts` (create) | preview, validation, submit. |
| `tests/purchase-table.test.ts` (create) | rows + delete-confirm. |
| `tests/tariff-badge.test.ts` (create) | provenance text. |
| `tests/purchase-charts.test.ts` (create) | renders series + empty state. |
| `tests/purchases-view.test.ts` (create) | composition + refetch on create/delete. |

---

## Group 1 — Types, client, formatters

### Task 1: API types

**Files:** Modify `src/api/types.ts`.

- [ ] **Step 1: Add the new interfaces and dashboard fields.**

In `DashboardView`, add two fields right after `tariff_rate: number`:
```ts
  tariff_rate: number
  tariff_source: string
  tariff_source_date: string | null
```

Append at the end of the file:
```ts
export interface PurchaseCreate {
  purchased_at: string // YYYY-MM-DD
  rand: number
  units_kwh: number
  note?: string | null
}

export interface PurchaseView {
  id: number
  purchased_at: string
  rand: number
  units_kwh: number
  note: string | null
  effective_rate: number
}

export interface PurchaseListView {
  purchases: PurchaseView[]
}
```

- [ ] **Step 2: Typecheck.**

Run: `npm run typecheck`
Expected: passes (no usages broken yet).

- [ ] **Step 3: Commit**

```bash
git add src/api/types.ts
git commit -m "feat(fe): add purchase types and dashboard tariff provenance fields"
```

### Task 2: API client write methods

**Files:** Modify `src/api/client.ts`; Test `tests/client.test.ts`.

- [ ] **Step 1: Add failing tests** (append inside `tests/client.test.ts`, and extend the import line at the top to include the new functions).

Change the import at the top of the file to:
```ts
import {
  getDashboard,
  getExplain,
  getHistory,
  getPurchases,
  createPurchase,
  deletePurchase,
  ApiError,
} from '../src/api/client'
```

Append these tests inside the `describe('api client', ...)` block:
```ts
  it('getPurchases returns the list', async () => {
    vi.stubGlobal('fetch', mockFetch(200, { purchases: [{ id: 1 }] }))
    const data = await getPurchases()
    expect(data.purchases).toHaveLength(1)
  })

  it('createPurchase POSTs the body and returns the created row', async () => {
    const fetchMock = mockFetch(201, { id: 7, effective_rate: 4.0 })
    vi.stubGlobal('fetch', fetchMock)
    const created = await createPurchase({
      purchased_at: '2026-06-01',
      rand: 1000,
      units_kwh: 250,
    })
    expect(created.id).toBe(7)
    const [, init] = fetchMock.mock.calls[0]
    expect(init).toMatchObject({ method: 'POST' })
    expect(JSON.parse((init as RequestInit).body as string)).toMatchObject({
      purchased_at: '2026-06-01',
      rand: 1000,
      units_kwh: 250,
    })
  })

  it('deletePurchase issues a DELETE', async () => {
    const fetchMock = mockFetch(204, {})
    vi.stubGlobal('fetch', fetchMock)
    await deletePurchase(7)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toContain('/api/purchases/7')
    expect(init).toMatchObject({ method: 'DELETE' })
  })

  it('surfaces a FastAPI 422 array-detail message', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch(422, { detail: [{ msg: 'purchased_at cannot be in the future' }] }),
    )
    await expect(
      createPurchase({ purchased_at: '2999-01-01', rand: 1, units_kwh: 1 }),
    ).rejects.toMatchObject({ status: 422, message: 'purchased_at cannot be in the future' })
  })
```

- [ ] **Step 2: Run tests to verify they fail.**

Run: `npm run test -- client`
Expected: FAIL — `getPurchases`/`createPurchase`/`deletePurchase` are not exported.

- [ ] **Step 3: Implement.** Edit `src/api/client.ts`:

Extend the type import:
```ts
import type {
  DashboardView,
  ExplanationView,
  HistoryView,
  PurchaseCreate,
  PurchaseListView,
  PurchaseView,
} from './types'
```

Replace the body of `getJson` so the error path uses a shared extractor, and add the extractor + write helpers. Specifically, replace this existing block:
```ts
async function getJson<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`)
  if (!resp.ok) {
    let detail = resp.statusText
    try {
      detail = ((await resp.json()) as { detail?: string }).detail ?? detail
    } catch {
      // non-JSON body; keep statusText
    }
    throw new ApiError(resp.status, detail)
  }
  return (await resp.json()) as T
}
```
with:
```ts
// FastAPI returns `detail` as a string for HTTPException and as an array of
// {msg,...} for 422 validation errors. Surface a useful message for both.
async function failure(resp: Response): Promise<ApiError> {
  let detail = resp.statusText
  try {
    const body = (await resp.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') {
      detail = body.detail
    } else if (Array.isArray(body.detail) && body.detail.length > 0) {
      const first = body.detail[0] as { msg?: string }
      if (first.msg) detail = first.msg
    }
  } catch {
    // non-JSON body; keep statusText
  }
  return new ApiError(resp.status, detail)
}

async function getJson<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`)
  if (!resp.ok) throw await failure(resp)
  return (await resp.json()) as T
}
```

Append the purchase calls at the end of the file:
```ts
export function getPurchases(): Promise<PurchaseListView> {
  return getJson<PurchaseListView>('/api/purchases')
}

export async function createPurchase(body: PurchaseCreate): Promise<PurchaseView> {
  const resp = await fetch(`${BASE}/api/purchases`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!resp.ok) throw await failure(resp)
  return (await resp.json()) as PurchaseView
}

export async function deletePurchase(id: number): Promise<void> {
  const resp = await fetch(`${BASE}/api/purchases/${id}`, { method: 'DELETE' })
  if (!resp.ok) throw await failure(resp)
}
```

- [ ] **Step 4: Run tests to verify they pass.**

Run: `npm run test -- client`
Expected: PASS (existing 3 + new 4).

- [ ] **Step 5: Commit**

```bash
git add src/api/client.ts tests/client.test.ts
git commit -m "feat(fe): add purchase client calls (getPurchases/createPurchase/deletePurchase)"
```

### Task 3: Formatters

**Files:** Modify `src/lib/format.ts`; Test `tests/format.test.ts`.

- [ ] **Step 1: Add failing tests** (append to `tests/format.test.ts`; extend the existing import from `../src/lib/format` to include the three new functions).

```ts
describe('purchase formatters', () => {
  it('formatRatePerKwh shows two decimals and unit', () => {
    expect(formatRatePerKwh(3.561)).toBe('R3.56/kWh')
  })

  it('formatUnits shows one decimal and unit', () => {
    expect(formatUnits(280.94)).toBe('280.9 units')
  })

  it('formatDate renders an ISO date as D Mon YYYY', () => {
    expect(formatDate('2026-04-12')).toBe('12 Apr 2026')
  })
})
```

- [ ] **Step 2: Run to verify fail.**

Run: `npm run test -- format`
Expected: FAIL — formatters not exported.

- [ ] **Step 3: Implement.** Append to `src/lib/format.ts`:
```ts
export const formatRatePerKwh = (v: number): string => `R${v.toFixed(2)}/kWh`
export const formatUnits = (v: number): string => `${v.toFixed(1)} units`

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// Parse a 'YYYY-MM-DD' string without timezone shifts and render '12 Apr 2026'.
export const formatDate = (iso: string): string => {
  const [y, m, d] = iso.split('-').map(Number)
  return `${d} ${MONTHS[m - 1]} ${y}`
}
```

- [ ] **Step 4: Run to verify pass.**

Run: `npm run test -- format`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lib/format.ts tests/format.test.ts
git commit -m "feat(fe): add rate/units/date formatters"
```

---

## Group 2 — Form, table, badge

### Task 4: `PurchaseForm.vue`

**Files:** Create `src/components/PurchaseForm.vue`; Test `tests/purchase-form.test.ts`.

- [ ] **Step 1: Write the failing test** `tests/purchase-form.test.ts`:
```ts
// tests/purchase-form.test.ts
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import PurchaseForm from '../src/components/PurchaseForm.vue'

vi.mock('../src/api/client', () => ({
  createPurchase: vi.fn().mockResolvedValue({ id: 1 }),
}))
import { createPurchase } from '../src/api/client'

afterEach(() => vi.clearAllMocks())

function fill(w: ReturnType<typeof mount>, rand: string, units: string) {
  return Promise.all([
    w.get('input[name="purchased_at"]').setValue('2026-06-01'),
    w.get('input[name="rand"]').setValue(rand),
    w.get('input[name="units_kwh"]').setValue(units),
  ])
}

describe('PurchaseForm', () => {
  it('shows a live effective-rate preview', async () => {
    const w = mount(PurchaseForm)
    await fill(w, '1000', '250')
    expect(w.text()).toContain('R4.00/kWh')
  })

  it('blocks submit and shows an error when units are zero', async () => {
    const w = mount(PurchaseForm)
    await fill(w, '1000', '0')
    await w.get('form').trigger('submit.prevent')
    await flushPromises()
    expect(createPurchase).not.toHaveBeenCalled()
    expect(w.text().toLowerCase()).toContain('greater than 0')
  })

  it('submits a valid purchase and emits created', async () => {
    const w = mount(PurchaseForm)
    await fill(w, '1000', '250')
    await w.get('form').trigger('submit.prevent')
    await flushPromises()
    expect(createPurchase).toHaveBeenCalledWith({
      purchased_at: '2026-06-01',
      rand: 1000,
      units_kwh: 250,
      note: null,
    })
    expect(w.emitted('created')).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run to verify fail.**

Run: `npm run test -- purchase-form`
Expected: FAIL — component file does not exist.

- [ ] **Step 3: Implement** `src/components/PurchaseForm.vue`:
```vue
<script setup lang="ts">
import { computed, ref } from 'vue'
import { createPurchase } from '../api/client'
import { formatRatePerKwh } from '../lib/format'

const emit = defineEmits<{ created: [] }>()

const purchasedAt = ref('')
const randStr = ref('')
const unitsStr = ref('')
const note = ref('')
const submitting = ref(false)
const errorMsg = ref('')

const rand = computed(() => Number(randStr.value))
const units = computed(() => Number(unitsStr.value))

const preview = computed(() =>
  randStr.value !== '' && unitsStr.value !== '' && rand.value > 0 && units.value > 0
    ? rand.value / units.value
    : null,
)

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

const validationError = computed<string | null>(() => {
  if (!purchasedAt.value) return 'Pick the purchase date.'
  if (purchasedAt.value > todayIso()) return 'Date cannot be in the future.'
  if (!(rand.value > 0)) return 'Rand amount must be greater than 0.'
  if (!(units.value > 0)) return 'Units must be greater than 0.'
  return null
})

async function onSubmit(): Promise<void> {
  if (validationError.value) {
    errorMsg.value = validationError.value
    return
  }
  submitting.value = true
  errorMsg.value = ''
  try {
    await createPurchase({
      purchased_at: purchasedAt.value,
      rand: rand.value,
      units_kwh: units.value,
      note: note.value.trim() || null,
    })
    emit('created')
    randStr.value = ''
    unitsStr.value = ''
    note.value = ''
    // Keep the date for quick consecutive entries.
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : 'Could not save the purchase.'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <form class="pf" @submit.prevent="onSubmit">
    <h2 class="pf__title">Log a purchase</h2>
    <div class="pf__grid">
      <label class="pf__field">
        <span class="pf__label">Date</span>
        <input name="purchased_at" type="date" v-model="purchasedAt" :max="todayIso()" />
      </label>
      <label class="pf__field">
        <span class="pf__label">Rand paid</span>
        <input name="rand" type="number" min="0" step="0.01" inputmode="decimal" v-model="randStr" placeholder="1000" />
      </label>
      <label class="pf__field">
        <span class="pf__label">Units received</span>
        <input name="units_kwh" type="number" min="0" step="0.01" inputmode="decimal" v-model="unitsStr" placeholder="280.9" />
      </label>
      <label class="pf__field pf__field--wide">
        <span class="pf__label">Note (optional)</span>
        <input name="note" type="text" v-model="note" placeholder="e.g. City of Cape Town" />
      </label>
    </div>

    <div class="pf__foot">
      <p class="pf__preview" :data-active="preview !== null">
        <span class="pf__preview-label">Effective rate</span>
        <span class="pf__preview-value">{{ preview !== null ? formatRatePerKwh(preview) : '—' }}</span>
      </p>
      <button class="pf__submit" type="submit" :disabled="submitting">
        {{ submitting ? 'Saving…' : 'Save purchase' }}
      </button>
    </div>

    <p v-if="errorMsg" class="pf__error" role="alert">{{ errorMsg }}</p>
  </form>
</template>

<style scoped>
.pf {
  padding: 1.25rem 1.35rem 1.4rem;
  border-radius: 16px;
  background: var(--sa-surface, #161c24);
  border: 1px solid var(--sa-line, #273140);
}
.pf__title {
  margin: 0 0 0.9rem;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
}
.pf__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 0.85rem;
}
.pf__field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  min-width: 0;
}
.pf__field--wide {
  grid-column: 1 / -1;
}
.pf__label {
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
}
.pf__field input {
  padding: 0.55rem 0.65rem;
  border-radius: 10px;
  border: 1px solid var(--sa-line, #273140);
  background: var(--sa-bg, #0f141b);
  color: var(--sa-text, #eef2f7);
  font-size: 0.95rem;
  font-variant-numeric: tabular-nums;
}
.pf__field input:focus {
  outline: none;
  border-color: var(--sa-accent, #5aa9ff);
}
.pf__foot {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
  margin-top: 1.05rem;
  flex-wrap: wrap;
}
.pf__preview {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.pf__preview-label {
  font-size: 0.72rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
}
.pf__preview-value {
  font-size: 1.25rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--sa-text-dim, #6b7689);
}
.pf__preview[data-active='true'] .pf__preview-value {
  color: var(--sa-solar, #f5b942);
}
.pf__submit {
  padding: 0.6rem 1.1rem;
  border-radius: 10px;
  border: 1px solid var(--sa-accent, #5aa9ff);
  background: var(--sa-accent, #5aa9ff);
  color: #06101c;
  font-size: 0.92rem;
  font-weight: 700;
  cursor: pointer;
}
.pf__submit:disabled {
  opacity: 0.6;
  cursor: progress;
}
.pf__error {
  margin: 0.85rem 0 0;
  font-size: 0.86rem;
  color: var(--sa-bad, #ef6b6b);
}
</style>
```

- [ ] **Step 4: Run to verify pass.**

Run: `npm run test -- purchase-form`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/components/PurchaseForm.vue tests/purchase-form.test.ts
git commit -m "feat(fe): add PurchaseForm with live rate preview and validation"
```

### Task 5: `PurchaseTable.vue`

**Files:** Create `src/components/PurchaseTable.vue`; Test `tests/purchase-table.test.ts`.

- [ ] **Step 1: Write the failing test** `tests/purchase-table.test.ts`:
```ts
// tests/purchase-table.test.ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PurchaseTable from '../src/components/PurchaseTable.vue'
import type { PurchaseView } from '../src/api/types'

const purchases: PurchaseView[] = [
  {
    id: 2,
    purchased_at: '2026-06-15',
    rand: 1000,
    units_kwh: 280.9,
    note: null,
    effective_rate: 3.56,
  },
  {
    id: 1,
    purchased_at: '2026-06-01',
    rand: 1000,
    units_kwh: 250,
    note: 'first buy',
    effective_rate: 4.0,
  },
]

describe('PurchaseTable', () => {
  it('renders a row per purchase with formatted rate', () => {
    const w = mount(PurchaseTable, { props: { purchases } })
    expect(w.findAll('tbody tr')).toHaveLength(2)
    expect(w.text()).toContain('R3.56/kWh')
    expect(w.text()).toContain('15 Jun 2026')
  })

  it('shows an empty message when there are no purchases', () => {
    const w = mount(PurchaseTable, { props: { purchases: [] } })
    expect(w.text().toLowerCase()).toContain('no purchases')
    expect(w.find('tbody tr').exists()).toBe(false)
  })

  it('requires confirmation before emitting delete', async () => {
    const w = mount(PurchaseTable, { props: { purchases } })
    await w.get('[data-test="del-2"]').trigger('click')
    expect(w.emitted('delete')).toBeFalsy() // first click only arms the confirm
    await w.get('[data-test="confirm-2"]').trigger('click')
    expect(w.emitted('delete')?.[0]).toEqual([2])
  })
})
```

- [ ] **Step 2: Run to verify fail.**

Run: `npm run test -- purchase-table`
Expected: FAIL — component file does not exist.

- [ ] **Step 3: Implement** `src/components/PurchaseTable.vue`:
```vue
<script setup lang="ts">
import { ref } from 'vue'
import type { PurchaseView } from '../api/types'
import { formatDate, formatRand, formatRatePerKwh, formatUnits } from '../lib/format'

defineProps<{ purchases: PurchaseView[] }>()
const emit = defineEmits<{ delete: [id: number] }>()

const confirmingId = ref<number | null>(null)

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
</script>

<template>
  <section class="pt" aria-label="Logged purchases">
    <h2 class="pt__title">Purchases</h2>
    <p v-if="!purchases.length" class="pt__empty">No purchases logged yet.</p>
    <table v-else class="pt__table">
      <thead>
        <tr>
          <th>Date</th>
          <th>Paid</th>
          <th>Units</th>
          <th>Rate</th>
          <th>Note</th>
          <th aria-label="actions" />
        </tr>
      </thead>
      <tbody>
        <tr v-for="p in purchases" :key="p.id">
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
            <button v-else class="pt__btn" :data-test="`del-${p.id}`" @click="arm(p.id)">
              Delete
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.pt {
  padding: 1.25rem 1.35rem 1.4rem;
  border-radius: 16px;
  background: var(--sa-surface, #161c24);
  border: 1px solid var(--sa-line, #273140);
}
.pt__title {
  margin: 0 0 0.9rem;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
}
.pt__empty {
  margin: 0;
  color: var(--sa-text-dim, #6b7689);
  font-size: 0.9rem;
}
.pt__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}
.pt__table th {
  text-align: left;
  padding: 0.4rem 0.6rem;
  font-size: 0.7rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
  border-bottom: 1px solid var(--sa-line, #273140);
}
.pt__table td {
  padding: 0.55rem 0.6rem;
  border-bottom: 1px solid var(--sa-line, #1f2733);
  color: var(--sa-text, #eef2f7);
}
.pt__num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.pt__rate {
  color: var(--sa-solar, #f5b942);
  font-weight: 600;
}
.pt__note {
  color: var(--sa-text-dim, #9aa6b6);
}
.pt__actions {
  text-align: right;
  white-space: nowrap;
}
.pt__btn {
  padding: 0.3rem 0.6rem;
  margin-left: 0.3rem;
  border-radius: 8px;
  border: 1px solid var(--sa-line, #273140);
  background: transparent;
  color: var(--sa-text-dim, #9aa6b6);
  font-size: 0.8rem;
  cursor: pointer;
}
.pt__btn--danger {
  border-color: var(--sa-bad-line, #ef6b6b3a);
  color: var(--sa-bad, #ef6b6b);
}
</style>
```

- [ ] **Step 4: Run to verify pass.**

Run: `npm run test -- purchase-table`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/components/PurchaseTable.vue tests/purchase-table.test.ts
git commit -m "feat(fe): add PurchaseTable with inline delete confirmation"
```

### Task 6: `TariffBadge.vue`

**Files:** Create `src/components/TariffBadge.vue`; Test `tests/tariff-badge.test.ts`.

- [ ] **Step 1: Write the failing test** `tests/tariff-badge.test.ts`:
```ts
// tests/tariff-badge.test.ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TariffBadge from '../src/components/TariffBadge.vue'

describe('TariffBadge', () => {
  it('shows the rate and purchase provenance with a date', () => {
    const w = mount(TariffBadge, {
      props: { rate: 3.56, source: 'purchase', sourceDate: '2026-04-12' },
    })
    expect(w.text()).toContain('R3.56/kWh')
    expect(w.text()).toContain('12 Apr 2026')
  })

  it('explains the config fallback when there is no purchase history', () => {
    const w = mount(TariffBadge, {
      props: { rate: 3.56, source: 'config', sourceDate: null },
    })
    expect(w.text().toLowerCase()).toContain('config default')
  })
})
```

- [ ] **Step 2: Run to verify fail.**

Run: `npm run test -- tariff-badge`
Expected: FAIL — component file does not exist.

- [ ] **Step 3: Implement** `src/components/TariffBadge.vue`:
```vue
<script setup lang="ts">
import { computed } from 'vue'
import { formatDate, formatRatePerKwh } from '../lib/format'

const props = defineProps<{
  rate: number
  source: string
  sourceDate: string | null
}>()

const provenance = computed(() =>
  props.source === 'purchase' && props.sourceDate
    ? `from your purchase on ${formatDate(props.sourceDate)}`
    : 'config default — log a purchase to track the real rate',
)
</script>

<template>
  <section class="tb" :data-source="source" aria-label="Current tariff rate">
    <span class="tb__label">Tariff</span>
    <span class="tb__rate">{{ formatRatePerKwh(rate) }}</span>
    <span class="tb__prov">{{ provenance }}</span>
  </section>
</template>

<style scoped>
.tb {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding: 1rem 1.1rem;
  border-radius: 14px;
  background: var(--sa-surface, #161c24);
  border: 1px solid var(--sa-line, #273140);
}
.tb__label {
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
}
.tb__rate {
  font-size: 1.4rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--sa-solar, #f5b942);
}
.tb__prov {
  font-size: 0.78rem;
  color: var(--sa-text-dim, #9aa6b6);
}
.tb[data-source='config'] .tb__rate {
  color: var(--sa-text-dim, #9aa6b6);
}
</style>
```

- [ ] **Step 4: Run to verify pass.**

Run: `npm run test -- tariff-badge`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/components/TariffBadge.vue tests/tariff-badge.test.ts
git commit -m "feat(fe): add TariffBadge showing derived rate provenance"
```

---

## Group 3 — Charts

### Task 7: `PurchaseCharts.vue`

**Files:** Create `src/components/PurchaseCharts.vue`; Test `tests/purchase-charts.test.ts`.

- [ ] **Step 1: Write the failing test** `tests/purchase-charts.test.ts`:
```ts
// tests/purchase-charts.test.ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PurchaseCharts from '../src/components/PurchaseCharts.vue'
import type { PurchaseView } from '../src/api/types'

const purchases: PurchaseView[] = [
  { id: 3, purchased_at: '2026-06-15', rand: 1000, units_kwh: 280, note: null, effective_rate: 3.57 },
  { id: 2, purchased_at: '2026-05-01', rand: 1000, units_kwh: 250, note: null, effective_rate: 4.0 },
  { id: 1, purchased_at: '2026-04-01', rand: 800, units_kwh: 242, note: null, effective_rate: 3.3 },
]

describe('PurchaseCharts', () => {
  it('renders a rate polyline and one spend bar per purchase', () => {
    const w = mount(PurchaseCharts, { props: { purchases, currentRate: 3.3 } })
    expect(w.find('[data-test="rate-line"]').exists()).toBe(true)
    expect(w.findAll('[data-test="spend-bar"]')).toHaveLength(3)
  })

  it('draws a reference line for the current derived rate', () => {
    const w = mount(PurchaseCharts, { props: { purchases, currentRate: 3.3 } })
    expect(w.find('[data-test="rate-ref"]').exists()).toBe(true)
  })

  it('shows an empty state with no purchases', () => {
    const w = mount(PurchaseCharts, { props: { purchases: [], currentRate: 3.56 } })
    expect(w.text().toLowerCase()).toContain('no purchases')
    expect(w.find('[data-test="rate-line"]').exists()).toBe(false)
  })
})
```

- [ ] **Step 2: Run to verify fail.**

Run: `npm run test -- purchase-charts`
Expected: FAIL — component file does not exist.

- [ ] **Step 3: Implement** `src/components/PurchaseCharts.vue`. The series are drawn oldest→newest, so reverse the newest-first prop. Three stacked mini-charts share one projection helper.
```vue
<script setup lang="ts">
import { computed } from 'vue'
import type { PurchaseView } from '../api/types'
import { formatRatePerKwh } from '../lib/format'

const props = defineProps<{
  purchases: PurchaseView[]
  currentRate: number
}>()

const W = 320
const H = 110
const PAD = 10

// Newest-first from the API; charts read left→right oldest→newest.
const chrono = computed(() => [...props.purchases].reverse())

const rates = computed(() => chrono.value.map((p) => p.effective_rate))
const spend = computed(() => chrono.value.map((p) => p.rand))
const units = computed(() => chrono.value.map((p) => p.units_kwh))

function xFor(i: number, n: number): number {
  if (n <= 1) return W / 2
  return PAD + (i / (n - 1)) * (W - PAD * 2)
}

// Line projection for the rate series; includes currentRate so the reference
// line sits inside the same vertical scale.
const rateGeom = computed(() => {
  const vals = rates.value
  const n = vals.length
  const all = [...vals, props.currentRate]
  let min = Math.min(...all)
  let max = Math.max(...all)
  if (min === max) {
    min -= 0.5
    max += 0.5
  }
  const y = (v: number): number => H - PAD - ((v - min) / (max - min)) * (H - PAD * 2)
  const line = vals.map((v, i) => `${xFor(i, n).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  return { line, refY: y(props.currentRate).toFixed(1) }
})

// Bar geometry for a non-negative series.
function bars(values: number[]): { x: number; y: number; w: number; h: number }[] {
  const n = values.length
  if (!n) return []
  const max = Math.max(...values, 0) || 1
  const slot = (W - PAD * 2) / n
  const bw = Math.max(2, slot * 0.6)
  return values.map((v, i) => {
    const h = (v / max) * (H - PAD * 2)
    return {
      x: PAD + i * slot + (slot - bw) / 2,
      y: H - PAD - h,
      w: bw,
      h,
    }
  })
}

const spendBars = computed(() => bars(spend.value))
const unitsBars = computed(() => bars(units.value))
const hasData = computed(() => props.purchases.length > 0)
</script>

<template>
  <section class="pc" aria-label="Purchase history charts">
    <h2 class="pc__title">Trends</h2>
    <p v-if="!hasData" class="pc__empty">No purchases to chart yet.</p>
    <div v-else class="pc__grid">
      <figure class="pc__chart">
        <figcaption class="pc__cap">
          Effective rate
          <span class="pc__cap-now">now {{ formatRatePerKwh(currentRate) }}</span>
        </figcaption>
        <svg :viewBox="`0 0 ${W} ${H}`" class="pc__svg" role="img" aria-label="Effective rate over time">
          <line
            data-test="rate-ref"
            :x1="PAD"
            :x2="W - PAD"
            :y1="rateGeom.refY"
            :y2="rateGeom.refY"
            stroke="var(--sa-text-dim, #9aa6b6)"
            stroke-width="1"
            stroke-dasharray="4 3"
            vector-effect="non-scaling-stroke"
          />
          <polyline
            data-test="rate-line"
            :points="rateGeom.line"
            fill="none"
            stroke="var(--sa-solar, #f5b942)"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            vector-effect="non-scaling-stroke"
          />
        </svg>
      </figure>

      <figure class="pc__chart">
        <figcaption class="pc__cap">Rand spent</figcaption>
        <svg :viewBox="`0 0 ${W} ${H}`" class="pc__svg" role="img" aria-label="Rand spent per purchase">
          <rect
            v-for="(b, i) in spendBars"
            :key="i"
            data-test="spend-bar"
            :x="b.x"
            :y="b.y"
            :width="b.w"
            :height="b.h"
            rx="1.5"
            fill="var(--sa-accent, #5aa9ff)"
          />
        </svg>
      </figure>

      <figure class="pc__chart">
        <figcaption class="pc__cap">Units received</figcaption>
        <svg :viewBox="`0 0 ${W} ${H}`" class="pc__svg" role="img" aria-label="Units received per purchase">
          <rect
            v-for="(b, i) in unitsBars"
            :key="i"
            data-test="units-bar"
            :x="b.x"
            :y="b.y"
            :width="b.w"
            :height="b.h"
            rx="1.5"
            fill="var(--sa-good, #34d399)"
          />
        </svg>
      </figure>
    </div>
  </section>
</template>

<style scoped>
.pc {
  padding: 1.25rem 1.35rem 1.4rem;
  border-radius: 16px;
  background: var(--sa-surface, #161c24);
  border: 1px solid var(--sa-line, #273140);
}
.pc__title {
  margin: 0 0 0.9rem;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
}
.pc__empty {
  margin: 0;
  color: var(--sa-text-dim, #6b7689);
  font-size: 0.9rem;
}
.pc__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0.9rem;
}
.pc__chart {
  margin: 0;
}
.pc__cap {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
  font-size: 0.74rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
  margin-bottom: 0.5rem;
}
.pc__cap-now {
  color: var(--sa-solar, #f5b942);
}
.pc__svg {
  display: block;
  width: 100%;
  height: 96px;
}
</style>
```

- [ ] **Step 4: Run to verify pass.**

Run: `npm run test -- purchase-charts`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/components/PurchaseCharts.vue tests/purchase-charts.test.ts
git commit -m "feat(fe): add PurchaseCharts (rate trend, spend, units)"
```

---

## Group 4 — View, nav, dashboard wiring, gate

### Task 8: `Purchases.vue` view

**Files:** Create `src/views/Purchases.vue`; Test `tests/purchases-view.test.ts`.

- [ ] **Step 1: Write the failing test** `tests/purchases-view.test.ts`:
```ts
// tests/purchases-view.test.ts
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import Purchases from '../src/views/Purchases.vue'

const getPurchases = vi.fn()
const getDashboard = vi.fn()
const deletePurchase = vi.fn().mockResolvedValue(undefined)

vi.mock('../src/api/client', () => ({
  getPurchases: () => getPurchases(),
  getDashboard: () => getDashboard(),
  deletePurchase: (id: number) => deletePurchase(id),
  createPurchase: vi.fn(),
  ApiError: class ApiError extends Error {},
}))

function listOf(rate: number) {
  return {
    purchases: [
      { id: 1, purchased_at: '2026-06-01', rand: 1000, units_kwh: 250, note: null, effective_rate: rate },
    ],
  }
}

afterEach(() => vi.clearAllMocks())

describe('Purchases view', () => {
  it('loads purchases and the derived tariff on mount', async () => {
    getPurchases.mockResolvedValue(listOf(4.0))
    getDashboard.mockResolvedValue({ tariff_rate: 3.56, tariff_source: 'purchase', tariff_source_date: '2026-06-01' })
    const w = mount(Purchases)
    await flushPromises()
    expect(w.text()).toContain('R4.00/kWh') // table row
    expect(w.text()).toContain('R3.56/kWh') // tariff badge
  })

  it('refetches after a delete', async () => {
    getPurchases.mockResolvedValue(listOf(4.0))
    getDashboard.mockResolvedValue({ tariff_rate: 3.56, tariff_source: 'config', tariff_source_date: null })
    const w = mount(Purchases)
    await flushPromises()
    getPurchases.mockClear()
    await w.get('[data-test="del-1"]').trigger('click')
    await w.get('[data-test="confirm-1"]').trigger('click')
    await flushPromises()
    expect(deletePurchase).toHaveBeenCalledWith(1)
    expect(getPurchases).toHaveBeenCalled() // list refreshed
  })
})
```

- [ ] **Step 2: Run to verify fail.**

Run: `npm run test -- purchases-view`
Expected: FAIL — view file does not exist.

- [ ] **Step 3: Implement** `src/views/Purchases.vue`:
```vue
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { deletePurchase, getDashboard, getPurchases } from '../api/client'
import type { PurchaseView } from '../api/types'
import PurchaseForm from '../components/PurchaseForm.vue'
import PurchaseTable from '../components/PurchaseTable.vue'
import PurchaseCharts from '../components/PurchaseCharts.vue'
import TariffBadge from '../components/TariffBadge.vue'

const purchases = ref<PurchaseView[]>([])
const rate = ref(0)
const source = ref('config')
const sourceDate = ref<string | null>(null)
const errorMsg = ref('')

async function loadPurchases(): Promise<void> {
  try {
    purchases.value = (await getPurchases()).purchases
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : 'Could not load purchases.'
  }
}

async function loadTariff(): Promise<void> {
  try {
    const d = await getDashboard(0.5)
    rate.value = d.tariff_rate
    source.value = d.tariff_source
    sourceDate.value = d.tariff_source_date
  } catch {
    // Tariff badge is non-critical; the page still works without it.
  }
}

async function refresh(): Promise<void> {
  await Promise.all([loadPurchases(), loadTariff()])
}

async function onDelete(id: number): Promise<void> {
  try {
    await deletePurchase(id)
    await refresh()
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : 'Could not delete the purchase.'
  }
}

onMounted(refresh)
</script>

<template>
  <div class="pv">
    <div class="pv__inner">
      <TariffBadge :rate="rate" :source="source" :source-date="sourceDate" />
      <p v-if="errorMsg" class="pv__error" role="alert">{{ errorMsg }}</p>
      <PurchaseForm @created="refresh" />
      <PurchaseCharts :purchases="purchases" :current-rate="rate" />
      <PurchaseTable :purchases="purchases" @delete="onDelete" />
    </div>
  </div>
</template>

<style scoped>
.pv {
  width: 100%;
  padding: clamp(1rem, 3vw, 2.4rem) clamp(1rem, 3vw, 2.4rem) 3rem;
}
.pv__inner {
  max-width: 1024px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 1.1rem;
}
.pv__error {
  margin: 0;
  padding: 0.75rem 1rem;
  border-radius: 12px;
  background: var(--sa-surface, #161c24);
  border: 1px solid var(--sa-bad-line, #ef6b6b3a);
  color: var(--sa-bad, #ef6b6b);
  font-size: 0.88rem;
}
</style>
```

- [ ] **Step 4: Run to verify pass.**

Run: `npm run test -- purchases-view`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/views/Purchases.vue tests/purchases-view.test.ts
git commit -m "feat(fe): add Purchases view composing form, charts, table"
```

### Task 9: App nav + Dashboard badge

**Files:** Modify `src/App.vue`, `src/views/Dashboard.vue`.

- [ ] **Step 1: Replace `src/App.vue`** with a two-tab shell:
```vue
<script setup lang="ts">
import { ref } from 'vue'
import Dashboard from './views/Dashboard.vue'
import Purchases from './views/Purchases.vue'

type Tab = 'dashboard' | 'purchases'
const tab = ref<Tab>('dashboard')
</script>

<template>
  <nav class="nav" aria-label="Primary">
    <button class="nav__tab" :data-active="tab === 'dashboard'" @click="tab = 'dashboard'">
      Dashboard
    </button>
    <button class="nav__tab" :data-active="tab === 'purchases'" @click="tab = 'purchases'">
      Purchases
    </button>
  </nav>
  <Dashboard v-if="tab === 'dashboard'" />
  <Purchases v-else />
</template>

<style scoped>
.nav {
  display: flex;
  gap: 0.4rem;
  padding: 0.8rem clamp(1rem, 3vw, 2.4rem) 0;
  max-width: 1280px;
  margin: 0 auto;
}
.nav__tab {
  padding: 0.5rem 1rem;
  border-radius: 10px 10px 0 0;
  border: 1px solid transparent;
  background: transparent;
  color: var(--sa-text-dim, #9aa6b6);
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
}
.nav__tab[data-active='true'] {
  color: var(--sa-text, #eef2f7);
  background: var(--sa-surface, #161c24);
  border-color: var(--sa-line, #273140);
  border-bottom-color: transparent;
}
</style>
```

- [ ] **Step 2: Add `TariffBadge` to the dashboard side column.** In `src/views/Dashboard.vue`:

Add the import alongside the others in `<script setup>`:
```ts
import TariffBadge from '../components/TariffBadge.vue'
```

In the `<aside class="dash__col dash__col--side">`, add the badge as the FIRST child (before `<ObjectiveSlider>`):
```html
          <aside class="dash__col dash__col--side">
            <TariffBadge
              :rate="dashboard.tariff_rate"
              :source="dashboard.tariff_source"
              :source-date="dashboard.tariff_source_date"
            />
            <ObjectiveSlider v-model="objective" />
```

- [ ] **Step 3: Verify typecheck + full test suite.**

Run: `npm run typecheck && npm run test`
Expected: typecheck clean; all tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/App.vue src/views/Dashboard.vue
git commit -m "feat(fe): add Purchases tab nav and dashboard tariff badge"
```

### Task 10: Full gate + README note

**Files:** Modify `README.md` (repo root) — a short feature note only.

- [ ] **Step 1: Run the full frontend gate.**

Run: `npm run check`
(This runs lint → typecheck → test → build.)
Expected: all four stages pass. Fix any lint/prettier/type errors surfaced (e.g. run `npx prettier --write 'src/**/*.{ts,vue}'` if `format` flags files, then re-run). Re-run until clean.

- [ ] **Step 2: Add a short note to `README.md`.** Find the features/section describing the dashboard and add a bullet near it:
```markdown
- **Purchase tracker:** log prepaid electricity purchases (date, rand, units); the app graphs the effective R/kWh over time and derives the engine's marginal tariff from your real purchases (lowest effective rate over a trailing window), falling back to the configured rate when no history exists. Writes go only to the app's own database — never to the inverter.
```
(If the README has no obviously matching section, add it under the main feature list. Keep it to this one bullet.)

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: note the purchase tracker in the README"
```

---

## Self-Review

**Spec coverage (§6 frontend):**
- Purchases section/view reachable from dashboard → Task 8 (view) + Task 9 (nav). ✓
- Capture form with live "= R X/kWh" preview + validation → Task 4. ✓
- Purchases table with delete → Task 5 (inline confirm). ✓
- Charts: effective R/kWh over time (with current-rate reference line), rand spent, units → Task 7. ✓
- Dashboard tariff figure gains a "derived from purchases" badge → Task 6 (component) + Task 9 (wiring). ✓
- Client gains first non-GET calls with consistent `ApiError` handling → Task 2. ✓

**Placeholder scan:** none — every step has complete code/commands.

**Type consistency:** `PurchaseCreate{purchased_at,rand,units_kwh,note?}` ↔ `createPurchase` body ↔ `PurchaseForm` submit; `PurchaseView` fields ↔ `PurchaseTable`/`PurchaseCharts` props; `DashboardView.tariff_source/tariff_source_date` ↔ `TariffBadge` props (`:source`, `:source-date`); `getPurchases` returns `PurchaseListView` ( `.purchases` ). Event names: `PurchaseForm` emits `created`; `PurchaseTable` emits `delete` with `id`; `Purchases.vue` handles both. `data-test` hooks (`del-{id}`, `confirm-{id}`, `rate-line`, `rate-ref`, `spend-bar`) match between components and tests. ✓
