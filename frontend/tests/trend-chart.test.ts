// tests/trend-chart.test.ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TrendChart from '../src/components/TrendChart.vue'
import type { HistoryPoint } from '../src/api/types'

const points: HistoryPoint[] = [
  { ts: '2026-06-22T08:00:00+00:00', battery_soc: 60, pv_power: 0, grid_power: 100, load_power: 200 },
  { ts: '2026-06-22T09:00:00+00:00', battery_soc: 64, pv_power: 500, grid_power: 0, load_power: 300 },
]

it('renders an svg polyline for the metric', () => {
  const w = mount(TrendChart, {
    props: { points, metric: 'battery_soc', label: 'Battery SOC', unit: '%' },
  })
  expect(w.find('svg').exists()).toBe(true)
  expect(w.find('polyline').exists()).toBe(true)
  expect(w.text()).toContain('Battery SOC')
})

it('renders a no-data state for empty points', () => {
  const w = mount(TrendChart, {
    props: { points: [], metric: 'pv_power', label: 'Solar', unit: 'W' },
  })
  expect(w.text().toLowerCase()).toContain('no data')
})

it('produces no NaN in the polyline for a single point', () => {
  const single: HistoryPoint[] = [
    { ts: '2026-06-22T08:00:00+00:00', battery_soc: 60, pv_power: 0, grid_power: 100, load_power: 200 },
  ]
  const w = mount(TrendChart, {
    props: { points: single, metric: 'battery_soc', label: 'Battery SOC', unit: '%' },
  })
  const pts = w.find('polyline').attributes('points') ?? ''
  expect(pts).not.toBe('')
  expect(pts.includes('NaN')).toBe(false)
})

it('produces no NaN in the polyline for an all-equal series', () => {
  const flat: HistoryPoint[] = [
    { ts: '2026-06-22T08:00:00+00:00', battery_soc: 50, pv_power: 0, grid_power: 0, load_power: 0 },
    { ts: '2026-06-22T09:00:00+00:00', battery_soc: 50, pv_power: 0, grid_power: 0, load_power: 0 },
    { ts: '2026-06-22T10:00:00+00:00', battery_soc: 50, pv_power: 0, grid_power: 0, load_power: 0 },
  ]
  const w = mount(TrendChart, {
    props: { points: flat, metric: 'battery_soc', label: 'Battery SOC', unit: '%' },
  })
  const pts = w.find('polyline').attributes('points') ?? ''
  expect(pts).not.toBe('')
  expect(pts.includes('NaN')).toBe(false)
})
