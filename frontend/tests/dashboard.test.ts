// tests/dashboard.test.ts
import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import Dashboard from '../src/views/Dashboard.vue'

const DASH = {
  objective: 0.5,
  battery_soc: 64,
  pv_power: 106,
  grid_power: 1140,
  load_power: 1086,
  month_to_date_grid_import_kwh: 12.5,
  usable_kwh: 15,
  usable_kwh_confidence: 0.6,
  daily_consumption_kwh: 20,
  daily_consumption_confidence: 0.5,
  tariff_rate: 3.56,
  expected_pv_kwh_today: 8,
  expected_pv_kwh_tomorrow: 8,
  month_spend: 1500,
  month_projected_cost: 1200,
  month_balance: 300,
  slots: [
    {
      start: '00:00',
      end: '05:00',
      target_soc: 90,
      grid_charge: true,
      behavior: 'grid_charging',
      end_soc: 90,
      grid_import_kwh: 13,
      cost: 46.28,
    },
  ],
  recommendation: {
    reserve_target_soc: 60,
    enable_overnight_grid_charge: false,
    grid_charge_kwh: 0,
    expected_daily_grid_import_kwh: 12,
    expected_daily_cost: 42.72,
    backup_hours: 18,
    monthly_cost_so_far: 956,
  },
  disclaimer: 'Advisory only. Read-only against your inverter.',
}

afterEach(() => vi.restoreAllMocks())

// A 200 OK Response wrapping the given JSON payload.
function okResponse(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as Response
}

// A failed Response (e.g. 503) whose JSON body carries a `detail`.
function errResponse(status: number, detail: string): Response {
  return { ok: false, status, statusText: detail, json: async () => ({ detail }) } as Response
}

// A controllable promise so a test can decide resolution order.
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

it('renders the disclaimer and live data after load', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) =>
      Promise.resolve(okResponse(url.includes('/api/history') ? { points: [] } : DASH)),
    ),
  )
  const w = mount(Dashboard)
  await flushPromises()
  expect(w.text().toLowerCase()).toContain('read-only')
  expect(w.text()).toContain('Grid-charging')
})

it('ignores a stale dashboard response that resolves after a newer one', async () => {
  // The initial load (objective 0.5) and a newer slider-driven change
  // (objective 1) race. We hold both dashboard responses open, then resolve the
  // OLDER one LAST. The sequence guard must keep the NEWER plan on screen.
  // Distinctive reserve-target values avoid colliding with other rendered
  // numbers (battery SOC 64, etc.): older = 33%, newer = 77%.
  const payloadFor = (reserve: number) => ({
    ...DASH,
    recommendation: { ...DASH.recommendation, reserve_target_soc: reserve },
  })

  // dashDeferreds[0] = initial load; we resolve it immediately so the slider
  // (which only renders once a dashboard exists) is on screen. Deferreds after
  // that are held open so we control resolution order.
  const dashDeferreds: Array<ReturnType<typeof deferred<Response>>> = []

  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/history')) return Promise.resolve(okResponse({ points: [] }))
      const d = deferred<Response>()
      dashDeferreds.push(d)
      return d.promise
    }),
  )

  vi.useFakeTimers()
  const w = mount(Dashboard)
  // Resolve the initial load so the slider becomes visible.
  dashDeferreds[0].resolve(okResponse(payloadFor(50)))
  await flushPromises()

  // A poll fires next with the CURRENT (old) objective 0.5 -> dashDeferreds[1].
  // Hold it open; its stale response will arrive LAST.
  vi.advanceTimersByTime(10_000)
  await flushPromises()
  expect(dashDeferreds.length).toBe(2)

  // Now the user drags the slider to objective 1; after the 300ms debounce a
  // newer fetch fires -> dashDeferreds[2].
  const input = w.find('input[type="range"]')
  await input.setValue(1)
  await input.trigger('input')
  vi.advanceTimersByTime(350)
  vi.useRealTimers()
  await flushPromises()
  expect(dashDeferreds.length).toBe(3)

  // Resolve the NEWER request first (reserve 77%), then the stale poll (33%).
  dashDeferreds[2].resolve(okResponse(payloadFor(77)))
  await flushPromises()
  dashDeferreds[1].resolve(okResponse(payloadFor(33)))
  await flushPromises()

  // The rendered plan must reflect the NEWER objective (77%), not the stale
  // poll response (33%) that arrived last.
  expect(w.text()).toContain('77%')
  expect(w.text()).not.toContain('33%')
})

it('re-fetches with the new objective after the slider debounce', async () => {
  const fetchMock = vi.fn().mockImplementation((url: string) =>
    Promise.resolve(okResponse(url.includes('/api/history') ? { points: [] } : DASH)),
  )
  vi.stubGlobal('fetch', fetchMock)

  const w = mount(Dashboard)
  await flushPromises()

  const dashboardUrls = () =>
    fetchMock.mock.calls.map((c) => String(c[0])).filter((u) => u.includes('/api/dashboard'))
  const before = dashboardUrls().length

  vi.useFakeTimers()
  const input = w.find('input[type="range"]')
  await input.setValue(0.8)
  await input.trigger('input')
  vi.advanceTimersByTime(350)
  vi.useRealTimers()
  await flushPromises()

  const after = dashboardUrls()
  expect(after.length).toBe(before + 1)
  expect(after[after.length - 1]).toContain('objective=0.8')
})

it('refetches history with the selected range', async () => {
  // The client mock inspects URLs (no per-fn mock): getHistory hits
  // /api/history?hours=<h>. Clicking the 30d button must refetch with 720.
  const fetchMock = vi.fn().mockImplementation((url: string) =>
    Promise.resolve(okResponse(url.includes('/api/history') ? { points: [] } : DASH)),
  )
  vi.stubGlobal('fetch', fetchMock)

  const w = mount(Dashboard)
  await flushPromises()

  await w.find('[data-test="range-720"]').trigger('click')
  await flushPromises()

  const historyUrls = fetchMock.mock.calls
    .map((c) => String(c[0]))
    .filter((u) => u.includes('/api/history'))
  expect(historyUrls.some((u) => u.includes('hours=720'))).toBe(true)
})

it('shows the waiting state on a 503 first load', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) =>
      url.includes('/api/history')
        ? Promise.resolve(okResponse({ points: [] }))
        : Promise.resolve(errResponse(503, 'live state not ready')),
    ),
  )
  const w = mount(Dashboard)
  await flushPromises()
  expect(w.text().toLowerCase()).toContain('waiting for live data')
})
