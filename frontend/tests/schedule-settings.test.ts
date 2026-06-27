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
    expect(w.text()).toContain('was 65%')
    expect(w.text().toLowerCase()).toContain('was on')
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
