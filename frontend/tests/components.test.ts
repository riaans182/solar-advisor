// tests/components.test.ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ScheduleTable from '../src/components/ScheduleTable.vue'
import ObjectiveSlider from '../src/components/ObjectiveSlider.vue'
import RecommendationPanel from '../src/components/RecommendationPanel.vue'
import type { RecommendationView, SlotView } from '../src/api/types'

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
  it('reflects new values when the recommendation prop is reassigned', async () => {
    const w = mount(RecommendationPanel, { props: { recommendation } })
    expect(w.text()).toContain('R12.34')

    const next: RecommendationView = {
      ...recommendation,
      expected_daily_cost: 99.99,
    }
    await w.setProps({ recommendation: next })
    expect(w.text()).toContain('R99.99')
    expect(w.text()).not.toContain('R12.34')
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
