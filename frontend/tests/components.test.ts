// tests/components.test.ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ScheduleTable from '../src/components/ScheduleTable.vue'
import ObjectiveSlider from '../src/components/ObjectiveSlider.vue'
import RecommendationPanel from '../src/components/RecommendationPanel.vue'
import LiveTiles from '../src/components/LiveTiles.vue'
import type { DashboardView, RecommendationView, SlotView } from '../src/api/types'

const slots: SlotView[] = [
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
  {
    start: '08:00',
    end: '16:30',
    target_soc: 95,
    grid_charge: false,
    behavior: 'solar_charging',
    end_soc: 95,
    grid_import_kwh: 0,
    cost: 0,
  },
]

describe('ScheduleTable', () => {
  it('renders a row per slot with behavior label and cost', () => {
    const w = mount(ScheduleTable, { props: { slots } })
    expect(w.text()).toContain('Grid-charging')
    expect(w.text()).toContain('Solar-charging')
    expect(w.text()).toContain('R46.28')
  })

  it('shows the actual slot count in the caption', () => {
    const w = mount(ScheduleTable, { props: { slots } })
    expect(w.text()).toContain('2 slots')
  })

  it('renders a no-schedule message and does not crash when empty', () => {
    const w = mount(ScheduleTable, { props: { slots: [] } })
    expect(w.text().toLowerCase()).toContain('no schedule')
    expect(w.find('tbody tr').exists()).toBe(false)
  })
})

const recommendation: RecommendationView = {
  reserve_target_soc: 40,
  enable_overnight_grid_charge: false,
  grid_charge_kwh: 0,
  expected_daily_grid_import_kwh: 3,
  expected_daily_cost: 12.34,
  backup_hours: 8.5,
  monthly_cost_so_far: 100,
}

describe('RecommendationPanel', () => {
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
    expect(w.text()).toContain('R1500.00')
    expect(w.text()).toContain('R650.00')
    expect(w.text().toLowerCase()).toContain('to finish')
  })

  it('explains the flat cost when no grid charging is needed', () => {
    const w = mount(RecommendationPanel, {
      props: {
        ...base,
        recommendation: { ...recommendation, enable_overnight_grid_charge: false, grid_charge_kwh: 0 },
      },
    })
    expect(w.text().toLowerCase()).toContain("won't change")
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
    month_spend: 0,
    month_remaining_cost: 0,
    recommended_slots: [],
    current_daily_cost: 0,
    recommended_daily_cost: 0,
    daily_saving: 0,
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

  it('shows a %/hour rate alongside the battery wattage', () => {
    const w = mount(LiveTiles, { props: { dashboard: dash({ battery_power: 420, usable_kwh: 15 }) } })
    expect(w.text()).toContain('%/h')
    expect(w.text()).toContain('2.8')
  })

  it('shows a solar forecast tile with today and tomorrow', () => {
    const w = mount(LiveTiles, {
      props: { dashboard: dash({ expected_pv_kwh_today: 10.9, expected_pv_kwh_tomorrow: 12.4 }) },
    })
    expect(w.text().toLowerCase()).toContain('forecast')
    expect(w.text()).toContain('10.9')
    expect(w.text().toLowerCase()).toContain('tomorrow')
  })
})
