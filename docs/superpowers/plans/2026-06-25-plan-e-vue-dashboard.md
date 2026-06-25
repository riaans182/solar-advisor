# Plan E — Vue 3 Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. For the **presentational components** (Tasks 6–9), also use the **frontend-design** skill — those tasks give the data contract, interactions, and a behavior test, but the markup/styling is yours to design for a genuinely-readable result.

**Goal:** A clean, modern, self-hosted Vue 3 dashboard that is genuinely easier to read than the stock SolarAssistant UI — live tiles, the 6-slot schedule with per-slot cost/behavior, the recommendation, a cost↔resilience slider that re-runs the engine, an Explain & Suggest panel backed by `/api/explain`, history trend charts, and a visible advisory disclaimer.

**Architecture:** Vite + Vue 3 (`<script setup lang="ts">`) + TypeScript strict. A typed API client wraps the existing FastAPI endpoints (`/api/dashboard`, `/api/explain`, `/api/health`, and a new `/api/history`). A `Dashboard` shell owns the objective state and polls `/api/dashboard`; presentational components render the typed data. Everything is read-only — the UI never writes to the inverter, and the advisory disclaimer is always visible.

**Tech Stack:** Vue 3, Vite, TypeScript (strict), ESLint + Prettier, Vitest + @vue/test-utils, hand-rolled SVG charts (no chart-lib dependency). Backend addition: one FastAPI endpoint (Python, same toolchain as Plans A–D). Served in production as static files via nginx behind Docker Compose.

**Covers spec stages:** 5 (dashboard, slider — frontend half), the §1 goals 2/3/4/5 (clean dashboard, explain panel, slider, history charts), §7 (visible disclaimer). See `docs/superpowers/specs/2026-06-22-solar-advisor-design.md`.

**Builds on `main`:** the API contract in `backend/src/solar_advisor/api/schemas.py` (`DashboardView`, `SlotView`, `RecommendationView`, `ExplanationView`) and `api/app.py` (`build_app`/`create_production_app`, `app.state`, `get_*` deps), `storage/sqlite_store.py` (`SqliteTelemetryStore.query_range`).

---

## API contract (frozen, from `main`)

```
GET /api/health   -> { status, telemetry_ready, schedule_ready, telemetry_ts }
GET /api/dashboard?objective=<0..1>  -> DashboardView   (503 until live state ready)
GET /api/explain?objective=<0..1>    -> ExplanationView (503 until ready)
GET /api/history?hours=<N>           -> HistoryView      (NEW — Task 1)
```
`DashboardView`: `objective, battery_soc, pv_power, grid_power, load_power, month_to_date_grid_import_kwh, usable_kwh, usable_kwh_confidence, daily_consumption_kwh, daily_consumption_confidence, tariff_rate, expected_pv_kwh_today, expected_pv_kwh_tomorrow, slots[SlotView], recommendation[RecommendationView], disclaimer`.
`SlotView`: `start, end, target_soc, grid_charge, behavior, end_soc, grid_import_kwh, cost`. `behavior ∈ {solar_charging, grid_charging, discharging, holding}`.
`RecommendationView`: `reserve_target_soc, enable_overnight_grid_charge, grid_charge_kwh, expected_daily_grid_import_kwh, expected_daily_cost, backup_hours, monthly_cost_so_far`.
`ExplanationView`: `explanation, generated, guard_ok, unverified_numbers[], disclaimer`.

---

## File structure (created by this plan)

```
backend/src/solar_advisor/api/
├─ schemas.py            # MODIFY: HistoryPoint, HistoryView
└─ app.py                # MODIFY: get_store dep, /api/history, app.state.store
frontend/
├─ package.json, tsconfig.json, vite.config.ts, .eslintrc.cjs, .prettierrc, index.html
├─ Dockerfile, nginx.conf
├─ src/
│  ├─ main.ts, App.vue
│  ├─ api/
│  │  ├─ types.ts        # TS mirror of the API contract
│  │  └─ client.ts       # typed fetch client
│  ├─ lib/
│  │  ├─ format.ts       # R / kWh / % / W formatters
│  │  └─ behavior.ts     # SlotBehavior → label + tone
│  ├─ components/
│  │  ├─ DisclaimerBanner.vue
│  │  ├─ LiveTiles.vue
│  │  ├─ ObjectiveSlider.vue
│  │  ├─ ScheduleTable.vue
│  │  ├─ RecommendationPanel.vue
│  │  ├─ ExplainPanel.vue
│  │  └─ TrendChart.vue
│  └─ views/Dashboard.vue
└─ tests/                # Vitest: client, format, behavior, component behavior
docker-compose.yml        # MODIFY: add `web` service
```

Backend tooling: `cd backend && make check`. Frontend tooling: `cd frontend && npm run check` (lint + typecheck + test + build), defined in Task 2.

---

## Task 1: Backend `/api/history` endpoint

**Files:**
- Modify: `backend/src/solar_advisor/api/schemas.py`
- Modify: `backend/src/solar_advisor/api/app.py`
- Test: `backend/tests/test_api_history.py`

- [ ] **Step 1: Add the schemas**

In `backend/src/solar_advisor/api/schemas.py`:

```python
class HistoryPoint(BaseModel):
    ts: str
    battery_soc: float
    pv_power: float
    grid_power: float
    load_power: float


class HistoryView(BaseModel):
    points: list[HistoryPoint]
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_api_history.py
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from solar_advisor.api.app import build_app, get_store
from solar_advisor.storage.sqlite_store import SqliteTelemetryStore
from tests.conftest import make_telemetry
from tests.test_api import _ready_state


def _client_with_store(tmp_path):
    store = SqliteTelemetryStore(tmp_path / "h.db", min_interval=timedelta(0))
    base = datetime(2026, 6, 22, 8, 0, tzinfo=UTC)
    for i in range(3):
        store.save(make_telemetry(base + timedelta(hours=i), battery_soc=60.0 + i, pv_power=100.0 * i))
    app = build_app(state=_ready_state())
    app.dependency_overrides[get_store] = lambda: store
    return TestClient(app), base


def test_history_returns_points(tmp_path):
    client, _ = _client_with_store(tmp_path)
    resp = client.get("/api/history?hours=24")
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 3
    assert points[0]["battery_soc"] == 60.0
    assert {"ts", "battery_soc", "pv_power", "grid_power", "load_power"} <= set(points[0])


def test_history_hours_bounds(tmp_path):
    client, _ = _client_with_store(tmp_path)
    assert client.get("/api/history?hours=0").status_code == 422  # ge=1
    assert client.get("/api/history?hours=999").status_code == 422  # le=168
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_api_history.py -v`
Expected: FAIL with `ImportError: cannot import name 'get_store'`.

- [ ] **Step 4: Implement the endpoint**

In `backend/src/solar_advisor/api/app.py`:

Add imports:

```python
from datetime import UTC, datetime, timedelta

from solar_advisor.api.schemas import (
    DashboardView, ExplanationView, HistoryPoint, HistoryView,
    RecommendationView, SlotView,
)
from solar_advisor.storage.store import TelemetryStore
```

Add the dependency (next to `get_service`):

```python
def get_store(request: Request) -> TelemetryStore:
    store = getattr(request.app.state, "store", None)
    if not isinstance(store, TelemetryStore):
        raise HTTPException(status_code=500, detail="store not initialised")
    return store
```

Add the endpoint inside `build_app` (after `explain`):

```python
    @app.get("/api/history", response_model=HistoryView)
    def history(
        hours: int = Query(default=24, ge=1, le=168),
        store: TelemetryStore = Depends(get_store),  # noqa: B008
    ) -> HistoryView:
        end = datetime.now(UTC)
        rows = store.query_range(end - timedelta(hours=hours), end)
        return HistoryView(
            points=[
                HistoryPoint(
                    ts=r.ts.isoformat(),
                    battery_soc=r.battery_soc,
                    pv_power=r.pv_power,
                    grid_power=r.grid_power,
                    load_power=r.load_power,
                )
                for r in rows
            ]
        )
```

Note: `TelemetryStore` is a `Protocol`. `isinstance(store, TelemetryStore)` requires it to be `@runtime_checkable` — if it is not already, add `@runtime_checkable` to the `TelemetryStore` protocol in `storage/store.py` (it has 3 methods; this is safe and matches the `ForecastProvider`/`TelemetrySource` pattern). If you prefer not to, use `getattr(...) or raise` without the isinstance and accept the looser type (but the isinstance form is cleaner and mypy-friendly).

In `create_production_app`, attach the store: after `store = SqliteTelemetryStore(...)` and `app = build_app(...)`, add `app.state.store = store`.

- [ ] **Step 5: Run to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_api_history.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Full backend suite**

Run: `cd backend && make check`
Expected: ruff, mypy strict, import-linter (1 kept), all tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/src/solar_advisor/api/ backend/tests/test_api_history.py backend/src/solar_advisor/storage/store.py
git commit -m "feat(api): /api/history endpoint for trend charts"
```

---

## Task 2: Frontend scaffold & conventions

**Files:** `frontend/package.json`, `tsconfig.json`, `tsconfig.node.json`, `vite.config.ts`, `.eslintrc.cjs`, `.prettierrc`, `index.html`, `src/main.ts`, `src/App.vue`, `.gitignore` (frontend).

- [ ] **Step 1: Scaffold with Vite (Vue + TS)**

```bash
cd /Users/riaans/Projects/solar-assisstant
npm create vite@latest frontend -- --template vue-ts
cd frontend
npm install
npm install -D vitest @vue/test-utils jsdom @vitejs/plugin-vue eslint prettier eslint-plugin-vue @vue/eslint-config-typescript @vue/eslint-config-prettier
```

- [ ] **Step 2: Strict TS + lint/format config**

Ensure `tsconfig.json` has `"strict": true` (the vue-ts template does). Add `.prettierrc`:

```json
{ "semi": false, "singleQuote": true, "printWidth": 100 }
```

Add `.eslintrc.cjs`:

```javascript
/* eslint-env node */
module.exports = {
  root: true,
  extends: [
    'plugin:vue/vue3-recommended',
    '@vue/eslint-config-typescript',
    '@vue/eslint-config-prettier',
  ],
  parserOptions: { ecmaVersion: 'latest' },
}
```

Configure Vitest in `vite.config.ts`:

```typescript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: { environment: 'jsdom', globals: true },
  server: { port: 5173 },
})
```

(Add a Vitest types reference at the top of `vite.config.ts` if needed: `/// <reference types="vitest" />`.)

- [ ] **Step 3: Add npm scripts**

In `package.json` `"scripts"`:

```json
{
  "dev": "vite",
  "build": "vue-tsc --noEmit && vite build",
  "preview": "vite preview",
  "lint": "eslint 'src/**/*.{ts,vue}'",
  "format": "prettier --check 'src/**/*.{ts,vue}'",
  "typecheck": "vue-tsc --noEmit",
  "test": "vitest run",
  "check": "npm run lint && npm run typecheck && npm run test && npm run build"
}
```

- [ ] **Step 4: Minimal app + verify the toolchain is green**

Replace `src/App.vue` with a minimal shell:

```vue
<script setup lang="ts">
</script>

<template>
  <main><h1>Solar Advisor</h1></main>
</template>
```

Remove the template's demo components (`src/components/HelloWorld.vue`, demo assets) and any imports of them in `App.vue`/`main.ts`.

Run: `cd frontend && npm run check`
Expected: lint clean, typecheck clean, vitest runs (0 tests is fine), `vite build` succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/ -- ':!frontend/node_modules'
git commit -m "chore(frontend): scaffold Vue 3 + TS strict + ESLint/Prettier/Vitest"
```

(Ensure `frontend/node_modules` and `frontend/dist` are gitignored — add a `frontend/.gitignore` with `node_modules` and `dist` if the template didn't.)

---

## Task 3: API types + typed client

**Files:** `frontend/src/api/types.ts`, `frontend/src/api/client.ts`, `frontend/tests/client.test.ts`

- [ ] **Step 1: Write `types.ts` (mirror the frozen contract)**

```typescript
// src/api/types.ts
export type SlotBehavior = 'solar_charging' | 'grid_charging' | 'discharging' | 'holding'

export interface SlotView {
  start: string
  end: string
  target_soc: number
  grid_charge: boolean
  behavior: SlotBehavior
  end_soc: number
  grid_import_kwh: number
  cost: number
}

export interface RecommendationView {
  reserve_target_soc: number
  enable_overnight_grid_charge: boolean
  grid_charge_kwh: number
  expected_daily_grid_import_kwh: number
  expected_daily_cost: number
  backup_hours: number
  monthly_cost_so_far: number
}

export interface DashboardView {
  objective: number
  battery_soc: number
  pv_power: number
  grid_power: number
  load_power: number
  month_to_date_grid_import_kwh: number
  usable_kwh: number
  usable_kwh_confidence: number
  daily_consumption_kwh: number
  daily_consumption_confidence: number
  tariff_rate: number
  expected_pv_kwh_today: number
  expected_pv_kwh_tomorrow: number
  slots: SlotView[]
  recommendation: RecommendationView
  disclaimer: string
}

export interface ExplanationView {
  explanation: string
  generated: boolean
  guard_ok: boolean
  unverified_numbers: number[]
  disclaimer: string
}

export interface HistoryPoint {
  ts: string
  battery_soc: number
  pv_power: number
  grid_power: number
  load_power: number
}

export interface HistoryView {
  points: HistoryPoint[]
}
```

- [ ] **Step 2: Write the failing client test**

```typescript
// tests/client.test.ts
import { afterEach, describe, expect, it, vi } from 'vitest'
import { getDashboard, getExplain, getHistory, ApiError } from '../src/api/client'

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response)
}

afterEach(() => vi.restoreAllMocks())

describe('api client', () => {
  it('getDashboard passes objective and returns parsed body', async () => {
    const fetchMock = mockFetch(200, { objective: 0.7, slots: [] })
    vi.stubGlobal('fetch', fetchMock)
    const data = await getDashboard(0.7)
    expect(data.objective).toBe(0.7)
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('objective=0.7'))
  })

  it('getHistory passes hours', async () => {
    const fetchMock = mockFetch(200, { points: [] })
    vi.stubGlobal('fetch', fetchMock)
    await getHistory(12)
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('hours=12'))
  })

  it('throws ApiError with status on non-2xx', async () => {
    vi.stubGlobal('fetch', mockFetch(503, { detail: 'not ready' }))
    await expect(getExplain(0.5)).rejects.toMatchObject({ status: 503 })
  })
})
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd frontend && npx vitest run tests/client.test.ts`
Expected: FAIL (module `../src/api/client` not found).

- [ ] **Step 4: Write `client.ts`**

```typescript
// src/api/client.ts
import type { DashboardView, ExplanationView, HistoryView } from './types'

const BASE = import.meta.env.VITE_API_BASE ?? ''

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

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

export function getDashboard(objective: number): Promise<DashboardView> {
  return getJson<DashboardView>(`/api/dashboard?objective=${objective}`)
}

export function getExplain(objective: number): Promise<ExplanationView> {
  return getJson<ExplanationView>(`/api/explain?objective=${objective}`)
}

export function getHistory(hours: number): Promise<HistoryView> {
  return getJson<HistoryView>(`/api/history?hours=${hours}`)
}
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd frontend && npx vitest run tests/client.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api frontend/tests/client.test.ts
git commit -m "feat(frontend): typed API client and contract types"
```

---

## Task 4: Formatting + behavior presentation utils

**Files:** `frontend/src/lib/format.ts`, `frontend/src/lib/behavior.ts`, `frontend/tests/format.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// tests/format.test.ts
import { describe, expect, it } from 'vitest'
import { formatRand, formatKwh, formatPercent, formatPower } from '../src/lib/format'
import { behaviorLabel, behaviorTone } from '../src/lib/behavior'

describe('format', () => {
  it('rand', () => expect(formatRand(46.28)).toBe('R46.28'))
  it('kwh', () => expect(formatKwh(13)).toBe('13.0 kWh'))
  it('percent', () => expect(formatPercent(90)).toBe('90%'))
  it('power rounds watts', () => expect(formatPower(1136.4)).toBe('1136 W'))
})

describe('behavior', () => {
  it('labels grid_charging', () => expect(behaviorLabel('grid_charging')).toBe('Grid-charging'))
  it('tone for grid_charging is a cost warning', () =>
    expect(behaviorTone('grid_charging')).toBe('warn'))
  it('tone for solar_charging is good', () =>
    expect(behaviorTone('solar_charging')).toBe('good'))
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run tests/format.test.ts`
Expected: FAIL (modules not found).

- [ ] **Step 3: Write `format.ts`**

```typescript
// src/lib/format.ts
export const formatRand = (v: number): string => `R${v.toFixed(2)}`
export const formatKwh = (v: number): string => `${v.toFixed(1)} kWh`
export const formatPercent = (v: number): string => `${Math.round(v)}%`
export const formatPower = (watts: number): string => `${Math.round(watts)} W`
```

- [ ] **Step 4: Write `behavior.ts`**

```typescript
// src/lib/behavior.ts
import type { SlotBehavior } from '../api/types'

export type Tone = 'good' | 'warn' | 'neutral'

const LABELS: Record<SlotBehavior, string> = {
  solar_charging: 'Solar-charging',
  grid_charging: 'Grid-charging',
  discharging: 'Discharging',
  holding: 'Holding',
}

const TONES: Record<SlotBehavior, Tone> = {
  solar_charging: 'good',
  grid_charging: 'warn', // pure cost under a flat tariff
  discharging: 'neutral',
  holding: 'neutral',
}

export const behaviorLabel = (b: SlotBehavior): string => LABELS[b]
export const behaviorTone = (b: SlotBehavior): Tone => TONES[b]
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd frontend && npx vitest run tests/format.test.ts`
Expected: PASS (7 tests).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib frontend/tests/format.test.ts
git commit -m "feat(frontend): money/energy formatters and slot-behavior presentation"
```

---

## Task 5: Presentational components — disclaimer, tiles, recommendation, schedule, slider

> **Use the frontend-design skill for this task.** The data contracts, props, interactions, and a behavior test are specified; design the markup and styling for a clean, readable, modern result (the explicit goal is "easier to read than the stock UI"). Keep it dependency-light (scoped CSS, no UI framework needed). Use the `Tone` from `lib/behavior` to color states (good/warn/neutral).

**Files:** `frontend/src/components/{DisclaimerBanner,LiveTiles,RecommendationPanel,ScheduleTable,ObjectiveSlider}.vue`, `frontend/tests/components.test.ts`

Component requirements (props are typed from `api/types`):

- **`DisclaimerBanner.vue`** — props: `text: string`. Always-visible, unmissable banner conveying advisory/read-only. (Spec §7.)
- **`LiveTiles.vue`** — props: `dashboard: DashboardView`. Tiles for **Battery SOC** (`battery_soc` %), **Solar** (`pv_power` W), **Grid** (`grid_power` W, label "importing"/"exporting" by sign), **Load** (`load_power` W). Use the formatters.
- **`RecommendationPanel.vue`** — props: `recommendation: RecommendationView`. Show reserve target SOC, whether overnight grid-charge is needed (highlight as a cost if true), expected daily cost (`formatRand`), backup runtime (`backup_hours` h), and month-to-date bill. Make the cost↔resilience trade-off legible.
- **`ScheduleTable.vue`** — props: `slots: SlotView[]`. A row per slot: time window (`start`–`end`), target SOC, behavior (via `behaviorLabel`, colored via `behaviorTone`), projected end SOC, grid import kWh, and cost (`formatRand`). Visually flag grid-charging slots as a cost.
- **`ObjectiveSlider.vue`** — props: `modelValue: number` (0..1); emits `update:modelValue`. A labeled slider from "Cheapest bill" (0) to "Most backup" (1) with the current value shown. (The parent debounces re-fetch — Task 8.)

- [ ] **Step 1: Write the behavior test FIRST (pins the contract; design comes after)**

```typescript
// tests/components.test.ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ScheduleTable from '../src/components/ScheduleTable.vue'
import ObjectiveSlider from '../src/components/ObjectiveSlider.vue'
import type { SlotView } from '../src/api/types'

const slots: SlotView[] = [
  { start: '00:00', end: '05:00', target_soc: 90, grid_charge: true,
    behavior: 'grid_charging', end_soc: 90, grid_import_kwh: 13, cost: 46.28 },
  { start: '08:00', end: '16:30', target_soc: 95, grid_charge: false,
    behavior: 'solar_charging', end_soc: 95, grid_import_kwh: 0, cost: 0 },
]

describe('ScheduleTable', () => {
  it('renders a row per slot with behavior label and cost', () => {
    const w = mount(ScheduleTable, { props: { slots } })
    expect(w.text()).toContain('Grid-charging')
    expect(w.text()).toContain('Solar-charging')
    expect(w.text()).toContain('R46.28')
  })
})

describe('ObjectiveSlider', () => {
  it('emits update:modelValue on input', async () => {
    const w = mount(ObjectiveSlider, { props: { modelValue: 0.5 } })
    const input = w.get('input[type="range"]')
    await input.setValue('0.8')
    expect(w.emitted('update:modelValue')?.[0]).toEqual([0.8])
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run tests/components.test.ts`
Expected: FAIL (components not found).

- [ ] **Step 3: Build the five components (frontend-design skill)**

Design and implement the five `.vue` files to satisfy the requirements above. Ensure `ScheduleTable` uses `behaviorLabel`/`formatRand` (so the test passes) and `ObjectiveSlider` uses a native `<input type="range" min="0" max="1" step="0.05">` with `:value="modelValue"` and `@input="$emit('update:modelValue', Number(($event.target as HTMLInputElement).value))"`. Keep all styles scoped.

- [ ] **Step 4: Run to verify it passes + lint/typecheck**

Run: `cd frontend && npx vitest run tests/components.test.ts && npm run lint && npm run typecheck`
Expected: PASS (2 tests); lint + typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components frontend/tests/components.test.ts
git commit -m "feat(frontend): live tiles, schedule table, recommendation, slider, disclaimer"
```

---

## Task 6: Explain & Suggest panel

> **Use the frontend-design skill.** Behavior + states are specified and tested; design the panel.

**Files:** `frontend/src/components/ExplainPanel.vue`, `frontend/tests/explain-panel.test.ts`

Requirements — props: `objective: number`. A button ("Explain my schedule") fetches `getExplain(objective)`; while loading, show a spinner/disabled state; on success render `explanation` (preserve line breaks). State handling from `ExplanationView`:
- `generated === false` → render the message as an informational note (AI off / rate-limited / unavailable), not as advice.
- `guard_ok === false` → render a visible **warning** that the explanation was withheld because it cited unverified numbers (this surfaces the provenance guard to the user — a feature, not an error). Show `unverified_numbers` if present.
- Always show the `disclaimer`.
On `ApiError` (e.g. 503 not-ready) show a friendly "live data not ready yet" message.

- [ ] **Step 1: Write the failing test (inject the fetch the panel uses)**

```typescript
// tests/explain-panel.test.ts
import { describe, expect, it, vi, afterEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ExplainPanel from '../src/components/ExplainPanel.vue'

function stubFetch(body: unknown, status = 200) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: status < 300, status, json: async () => body } as Response),
  )
}
afterEach(() => vi.restoreAllMocks())

it('shows a withheld warning when guard_ok is false', async () => {
  stubFetch({
    explanation: 'An explanation could not be verified...', generated: true,
    guard_ok: false, unverified_numbers: [777], disclaimer: 'Advisory only.',
  })
  const w = mount(ExplainPanel, { props: { objective: 0.5 } })
  await w.get('button').trigger('click')
  await flushPromises()
  expect(w.text().toLowerCase()).toContain('withheld')
  expect(w.text()).toContain('777')
})

it('renders a generated explanation', async () => {
  stubFetch({
    explanation: 'Your battery grid-charges overnight.', generated: true,
    guard_ok: true, unverified_numbers: [], disclaimer: 'Advisory only.',
  })
  const w = mount(ExplainPanel, { props: { objective: 1 } })
  await w.get('button').trigger('click')
  await flushPromises()
  expect(w.text()).toContain('grid-charges overnight')
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run tests/explain-panel.test.ts`
Expected: FAIL (component not found).

- [ ] **Step 3: Build `ExplainPanel.vue` (frontend-design skill)**

Implement to satisfy the requirements and tests (use `getExplain` from `api/client`; the test stubs `fetch`, which the client uses). The withheld branch (`!guard_ok`) must render text containing "withheld" and the `unverified_numbers`.

- [ ] **Step 4: Run to verify it passes + lint/typecheck**

Run: `cd frontend && npx vitest run tests/explain-panel.test.ts && npm run lint && npm run typecheck`
Expected: PASS (2 tests); clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ExplainPanel.vue frontend/tests/explain-panel.test.ts
git commit -m "feat(frontend): Explain & Suggest panel with provenance-withheld warning"
```

---

## Task 7: Trend chart (history)

> **Use the frontend-design skill.** Hand-roll a clean SVG line chart — no chart library.

**Files:** `frontend/src/components/TrendChart.vue`, `frontend/tests/trend-chart.test.ts`

Requirements — props: `points: HistoryPoint[]`, `metric: 'battery_soc' | 'pv_power' | 'grid_power' | 'load_power'`, `label: string`, `unit: string`. Render an SVG line of the chosen metric over time, auto-scaled to the data's min/max, with the label + latest value. Handle the empty-data case (render a "no data yet" state). Keep it a pure presentational SVG (no fetch — the parent supplies points).

- [ ] **Step 1: Write the failing test**

```typescript
// tests/trend-chart.test.ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TrendChart from '../src/components/TrendChart.vue'
import type { HistoryPoint } from '../src/api/types'

const points: HistoryPoint[] = [
  { ts: '2026-06-22T08:00:00+00:00', battery_soc: 60, pv_power: 0, grid_power: 100, load_power: 200 },
  { ts: '2026-06-22T09:00:00+00:00', battery_soc: 64, pv_power: 500, grid_power: 0, load_power: 300 },
]

it('renders an svg polyline for the metric', () => {
  const w = mount(TrendChart, { props: { points, metric: 'battery_soc', label: 'Battery SOC', unit: '%' } })
  expect(w.find('svg').exists()).toBe(true)
  expect(w.find('polyline').exists()).toBe(true)
  expect(w.text()).toContain('Battery SOC')
})

it('renders a no-data state for empty points', () => {
  const w = mount(TrendChart, { props: { points: [], metric: 'pv_power', label: 'Solar', unit: 'W' } })
  expect(w.text().toLowerCase()).toContain('no data')
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run tests/trend-chart.test.ts`
Expected: FAIL (component not found).

- [ ] **Step 3: Build `TrendChart.vue` (frontend-design skill)**

Implement: compute an SVG `<polyline>` from `points[metric]` scaled into the viewBox; show `label` and the latest value with `unit`; render a "No data yet" state when `points.length === 0`.

- [ ] **Step 4: Run to verify it passes + lint/typecheck**

Run: `cd frontend && npx vitest run tests/trend-chart.test.ts && npm run lint && npm run typecheck`
Expected: PASS (2 tests); clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/TrendChart.vue frontend/tests/trend-chart.test.ts
git commit -m "feat(frontend): SVG trend chart for telemetry history"
```

---

## Task 8: Dashboard shell (compose + poll + slider state)

> **Use the frontend-design skill** for the overall layout — this is the page the user sees.

**Files:** `frontend/src/views/Dashboard.vue`, `frontend/src/App.vue` (mount Dashboard), `frontend/tests/dashboard.test.ts`

Requirements: `Dashboard.vue` owns `objective` (ref, init 0.5) and the latest `DashboardView`. On mount and every 10s, fetch `getDashboard(objective)`; on slider change, debounce (~300ms) and re-fetch (so the slider "re-runs the engine"). Fetch `getHistory(24)` on mount (and on the 10s poll). Compose: `DisclaimerBanner` (top, from `dashboard.disclaimer`), `LiveTiles`, `ObjectiveSlider` (v-model objective), `RecommendationPanel`, `ScheduleTable`, `ExplainPanel` (pass `objective`), and `TrendChart`(s). Handle the not-ready 503 (`ApiError`) with a "waiting for live data…" state. Clean up the interval on unmount.

- [ ] **Step 1: Write the failing smoke test**

```typescript
// tests/dashboard.test.ts
import { describe, expect, it, vi, afterEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import Dashboard from '../src/views/Dashboard.vue'

const DASH = {
  objective: 0.5, battery_soc: 64, pv_power: 106, grid_power: 1140, load_power: 1086,
  month_to_date_grid_import_kwh: 12.5, usable_kwh: 15, usable_kwh_confidence: 0.6,
  daily_consumption_kwh: 20, daily_consumption_confidence: 0.5, tariff_rate: 3.56,
  expected_pv_kwh_today: 8, expected_pv_kwh_tomorrow: 8,
  slots: [{ start: '00:00', end: '05:00', target_soc: 90, grid_charge: true,
    behavior: 'grid_charging', end_soc: 90, grid_import_kwh: 13, cost: 46.28 }],
  recommendation: { reserve_target_soc: 60, enable_overnight_grid_charge: false,
    grid_charge_kwh: 0, expected_daily_grid_import_kwh: 12, expected_daily_cost: 42.72,
    backup_hours: 18, monthly_cost_so_far: 956 },
  disclaimer: 'Advisory only. Read-only against your inverter.',
}

afterEach(() => vi.restoreAllMocks())

it('renders the disclaimer and live data after load', async () => {
  vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) =>
    Promise.resolve({
      ok: true, status: 200,
      json: async () => (url.includes('/api/history') ? { points: [] } : DASH),
    } as Response),
  ))
  const w = mount(Dashboard)
  await flushPromises()
  expect(w.text().toLowerCase()).toContain('read-only')
  expect(w.text()).toContain('Grid-charging')
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run tests/dashboard.test.ts`
Expected: FAIL (view not found).

- [ ] **Step 3: Build `Dashboard.vue` + mount it in `App.vue` (frontend-design skill)**

Implement the composition, polling (`setInterval`, cleared on unmount), debounced slider re-fetch, history fetch, and the 503 waiting-state. Point `App.vue` at `<Dashboard />`.

- [ ] **Step 4: Run to verify it passes + full frontend check**

Run: `cd frontend && npx vitest run tests/dashboard.test.ts && npm run check`
Expected: PASS; lint + typecheck + all tests + build all green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views frontend/src/App.vue frontend/tests/dashboard.test.ts
git commit -m "feat(frontend): dashboard shell with polling, slider re-run, and history"
```

---

## Task 9: Container + compose + README

**Files:** `frontend/Dockerfile`, `frontend/nginx.conf`, `docker-compose.yml`, `backend/README.md` (or root README)

- [ ] **Step 1: Frontend Dockerfile (build static, serve via nginx)**

```dockerfile
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
```

`frontend/nginx.conf` (serve the SPA and proxy `/api` to the backend container):

```nginx
server {
  listen 80;
  root /usr/share/nginx/html;
  index index.html;
  location /api/ { proxy_pass http://api:8000; }
  location / { try_files $uri $uri/ /index.html; }
}
```

(With the nginx `/api` proxy, the app calls same-origin `/api/...`, so `VITE_API_BASE` stays empty in production.)

- [ ] **Step 2: Add the `web` service to `docker-compose.yml`**

```yaml
  web:
    build:
      context: ./frontend
    ports:
      - "8080:80"
    depends_on:
      - api
    restart: unless-stopped
```

- [ ] **Step 3: Validate compose config**

Run (if docker available): `cd backend && SA_MQTT_HOST=x ANTHROPIC_API_KEY=x docker compose config -q && echo OK`
Expected: `OK` (note that `docker-compose.yml` is in `backend/` — adjust the `web` build context to `../frontend` if the compose file lives in `backend/`). If docker is unavailable, confirm the file is textually consistent.

- [ ] **Step 4: README — make it read as a portfolio piece**

Update the README with: a one-paragraph overview, an architecture diagram/description making the **deterministic engine vs LLM explanation** boundary explicit (the project's thesis), the advisory-only/read-only guarantee, how to run (`docker compose up`), and the env vars (`SA_*`, `ANTHROPIC_API_KEY`). Keep it concise and accurate to what's built.

- [ ] **Step 5: Commit**

```bash
git add frontend/Dockerfile frontend/nginx.conf docker-compose.yml backend/README.md
git commit -m "build: frontend container, compose web service, portfolio README"
```

---

## Definition of done (Plan E)

- Backend `make check` green (with the new `/api/history` endpoint + test).
- `cd frontend && npm run check` green: ESLint, `vue-tsc` typecheck, Vitest, and `vite build` all pass.
- The dashboard renders live tiles, the schedule with per-slot behavior/cost, the recommendation, the cost↔resilience slider (re-runs the engine on change), the Explain & Suggest panel (with the provenance-withheld warning surfaced), history trend charts, and an always-visible advisory disclaimer.
- Read-only throughout — the frontend only issues GETs; nothing writes to the inverter.
- `docker compose up` serves the SPA (nginx) with `/api` proxied to the backend.

**This completes the MVP.** Optional follow-ups (deferred across plans): wire `HomeAssistantForecastProvider` behind a config switch; an `ExplanationView.reason` enum for clearer UI states; visual polish passes; the structural no-publish MQTT client wrapper.

---

## Self-review notes

- **Spec coverage:** goal-2 clean dashboard (Tasks 5, 8), goal-3 explain panel (Task 6), goal-4 slider re-runs engine (Tasks 5, 8 — `ObjectiveSlider` → debounced `getDashboard`), goal-5 history charts (Tasks 1, 7), §7 visible disclaimer (Task 5 `DisclaimerBanner`, shown in Task 8). The provenance guard is surfaced to the user (Task 6 withheld warning) — a deliberate feature.
- **Type consistency:** `types.ts` mirrors the frozen `schemas.py` field-for-field (`SlotView`/`RecommendationView`/`DashboardView`/`ExplanationView` + the new `HistoryPoint`/`HistoryView`); the client returns those types; components consume them; `SlotBehavior` union matches the engine's `SlotBehavior` enum values. `getDashboard/getExplain/getHistory` signatures are used identically in the panel/dashboard tests and components.
- **No placeholders in testable layers:** backend endpoint, client, formatters, and every component's behavior test are complete and runnable. Visual markup is intentionally delegated to the frontend-design skill with explicit contracts + tests pinning behavior — the right division for UI quality.
- **Read-only:** the client exposes only GET helpers; no POST/PUT/DELETE anywhere; the disclaimer is always rendered.
```
