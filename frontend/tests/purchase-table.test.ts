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

  it('enters edit mode and emits update with the edited body', async () => {
    const w = mount(PurchaseTable, { props: { purchases } })
    await w.get('[data-test="edit-1"]').trigger('click')
    await w.get('[data-test="edit-rand-1"]').setValue('1200')
    await w.get('[data-test="edit-units-1"]').setValue('300')
    await w.get('[data-test="save-1"]').trigger('click')
    const ev = w.emitted('update')?.[0]?.[0] as { id: number; body: Record<string, unknown> }
    expect(ev.id).toBe(1)
    expect(ev.body).toMatchObject({ rand: 1200, units_kwh: 300 })
  })

  it('cancel exits edit mode without emitting', async () => {
    const w = mount(PurchaseTable, { props: { purchases } })
    await w.get('[data-test="edit-1"]').trigger('click')
    await w.get('[data-test="cancel-edit-1"]').trigger('click')
    expect(w.emitted('update')).toBeFalsy()
    expect(w.find('[data-test="edit-rand-1"]').exists()).toBe(false)
  })

  it('shows days of cover when daily consumption is provided', () => {
    const w = mount(PurchaseTable, { props: { purchases, dailyConsumption: 25 } })
    expect(w.text()).toContain('≈ 10 days')
  })

  it('omits days of cover when daily consumption is unknown', () => {
    const w = mount(PurchaseTable, { props: { purchases, dailyConsumption: 0 } })
    expect(w.text()).not.toContain('days')
  })
})
