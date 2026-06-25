// tests/components.test.ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ScheduleTable from '../src/components/ScheduleTable.vue'
import ObjectiveSlider from '../src/components/ObjectiveSlider.vue'
import type { SlotView } from '../src/api/types'

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
})

describe('ObjectiveSlider', () => {
  it('emits update:modelValue on input', async () => {
    const w = mount(ObjectiveSlider, { props: { modelValue: 0.5 } })
    const input = w.get('input[type="range"]')
    await input.setValue('0.8')
    expect(w.emitted('update:modelValue')?.[0]).toEqual([0.8])
  })
})
