// tests/purchase-charts.test.ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PurchaseCharts from '../src/components/PurchaseCharts.vue'
import type { PurchaseView } from '../src/api/types'

const purchases: PurchaseView[] = [
  {
    id: 3,
    purchased_at: '2026-06-15',
    rand: 1000,
    units_kwh: 280,
    note: null,
    effective_rate: 3.57,
  },
  {
    id: 2,
    purchased_at: '2026-05-01',
    rand: 1000,
    units_kwh: 250,
    note: null,
    effective_rate: 4.0,
  },
  { id: 1, purchased_at: '2026-04-01', rand: 800, units_kwh: 242, note: null, effective_rate: 3.3 },
]

describe('PurchaseCharts', () => {
  it('renders a rate polyline and one spend bar per purchase', () => {
    const w = mount(PurchaseCharts, { props: { purchases, currentRate: 3.3 } })
    expect(w.find('[data-test="rate-line"]').exists()).toBe(true)
    expect(w.findAll('[data-test="spend-bar"]')).toHaveLength(3)
  })

  it('draws a reference line for the current derived rate', () => {
    const w = mount(PurchaseCharts, { props: { purchases, currentRate: 3.3 } })
    expect(w.find('[data-test="rate-ref"]').exists()).toBe(true)
  })

  it('shows an empty state with no purchases', () => {
    const w = mount(PurchaseCharts, { props: { purchases: [], currentRate: 3.56 } })
    expect(w.text().toLowerCase()).toContain('no purchases')
    expect(w.find('[data-test="rate-line"]').exists()).toBe(false)
  })

  it('renders a single purchase and a flat-rate series without crashing', () => {
    const one = [
      { id: 1, purchased_at: '2026-06-01', rand: 1000, units_kwh: 250, note: null, effective_rate: 4.0 },
    ]
    const w = mount(PurchaseCharts, { props: { purchases: one, currentRate: 4.0 } })
    expect(w.findAll('[data-test="spend-bar"]')).toHaveLength(1)
    expect(w.find('[data-test="rate-ref"]').exists()).toBe(true)
  })

  it('keeps the lowest rate off the chart baseline (no false zero)', () => {
    const rising = [
      { id: 2, purchased_at: '2026-06-15', rand: 1000, units_kwh: 320, note: null, effective_rate: 3.125 },
      { id: 1, purchased_at: '2026-05-01', rand: 1000, units_kwh: 250, note: null, effective_rate: 4.0 },
    ]
    const w = mount(PurchaseCharts, { props: { purchases: rising, currentRate: 3.125 } })
    const pts = w.get('[data-test="rate-line"]').attributes('points') as string
    const ys = pts.split(' ').map((pair) => Number(pair.split(',')[1]))
    // viewBox H=110, PAD=10 -> baseline y=100. Padding must keep all points strictly above it.
    expect(Math.max(...ys)).toBeLessThan(100)
  })

  it('shows a rate tooltip on pointer move over the rate chart', async () => {
    const w = mount(PurchaseCharts, { props: { purchases, currentRate: 3.3 } })
    await w.get('[data-test="rate-svg"]').trigger('pointermove', { clientX: 0 })
    expect(w.find('[data-test="pc-tip"]').exists()).toBe(true)
  })

  it('clears the rate tooltip without error when purchases shrink past the hovered index', async () => {
    const w = mount(PurchaseCharts, { props: { purchases, currentRate: 3.3 } })
    await w.get('[data-test="rate-svg"]').trigger('pointermove', { clientX: 0 })
    expect(w.find('[data-test="pc-tip"]').exists()).toBe(true)
    await w.setProps({ purchases: [] })
    expect(w.find('[data-test="pc-tip"]').exists()).toBe(false)
  })
})
