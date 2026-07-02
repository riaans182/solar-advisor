// tests/embed.test.ts
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import App from '../src/App.vue'

const DASH = {
  objective: 0.5,
  battery_soc: 82,
  pv_power: 4200,
  grid_power: 0,
  load_power: 2300,
  battery_power: 1800,
  conversion_power: 100,
  month_to_date_grid_import_kwh: 12.5,
  usable_kwh: 15,
  usable_kwh_confidence: 0.6,
  battery_soc_floor: 20,
  daily_consumption_kwh: 20,
  daily_consumption_confidence: 0.5,
  tariff_rate: 3.56,
  expected_pv_kwh_today: 12.6,
  expected_pv_kwh_tomorrow: 10.4,
  month_spend: 1500,
  month_remaining_cost: 54,
  recommended_slots: [],
  current_daily_cost: 0,
  recommended_daily_cost: 0,
  daily_saving: 0,
  pv_energy_today: 6.2,
  load_energy_today: 9.1,
  slots: [],
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

function okResponse(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as Response
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockImplementation((url: string) =>
        Promise.resolve(okResponse(url.includes('/api/history') ? { points: [] } : DASH)),
      ),
  )
})

afterEach(() => {
  vi.restoreAllMocks()
  window.history.pushState({}, '', '/') // reset the URL between tests
})

it('embed mode (?embed=tiles) renders only the live tiles, no nav or masthead', async () => {
  window.history.pushState({}, '', '/?embed=tiles')
  const w = mount(App)
  await flushPromises()

  // The live tiles are present...
  expect(w.text()).toContain('Battery')
  expect(w.text()).toContain('Solar today')
  expect(w.text()).toContain('Conversion / idle')

  // ...but the chrome is gone: no primary nav, no Purchases tab, no masthead tagline.
  expect(w.find('nav.nav').exists()).toBe(false)
  expect(w.text()).not.toContain('Purchases')
  expect(w.text()).not.toContain('Deterministic engine · read-only · advisory')
})

it('default mode (no embed param) renders the full app with nav', async () => {
  const w = mount(App)
  await flushPromises()

  expect(w.find('nav.nav').exists()).toBe(true)
  expect(w.text()).toContain('Purchases')
})
