// tests/schedule-compare.test.ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ScheduleCompare from '../src/components/ScheduleCompare.vue'
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

describe('ScheduleCompare', () => {
  it('shows the saving + changed slots and both schedules when they differ', () => {
    const current = [slot({ grid_charge: true })]
    const recommended = [slot({ grid_charge: false, target_soc: 60, behavior: 'holding', cost: 0 })]
    const w = mount(ScheduleCompare, {
      props: { current, recommended, dailySaving: 46, currentCost: 46, recommendedCost: 0 },
    })
    expect(w.text()).toContain('R46')
    expect(w.text().toLowerCase()).toContain('recommended inverter settings')
    expect(w.findAll('table').length).toBe(2)
  })

  it('says it already matches when current == recommended', () => {
    const w = mount(ScheduleCompare, {
      props: {
        current: [slot({ grid_charge: false })],
        recommended: [slot({ grid_charge: false })],
        dailySaving: 0,
        currentCost: 0,
        recommendedCost: 0,
      },
    })
    expect(w.text().toLowerCase()).toContain('already matches')
    expect(w.findAll('table').length).toBe(1)
  })
})
