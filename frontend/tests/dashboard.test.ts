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

it('renders the disclaimer and live data after load', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: async () => (url.includes('/api/history') ? { points: [] } : DASH),
      } as Response),
    ),
  )
  const w = mount(Dashboard)
  await flushPromises()
  expect(w.text().toLowerCase()).toContain('read-only')
  expect(w.text()).toContain('Grid-charging')
})
