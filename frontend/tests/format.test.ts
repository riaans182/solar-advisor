// tests/format.test.ts
import { describe, expect, it } from 'vitest'
import {
  formatRand,
  formatKwh,
  formatPercent,
  formatPower,
  formatRatePerKwh,
  formatUnits,
  formatDate,
} from '../src/lib/format'
import { behaviorLabel, behaviorTone } from '../src/lib/behavior'

describe('format', () => {
  it('rand', () => expect(formatRand(46.28)).toBe('R46.28'))
  it('kwh', () => expect(formatKwh(13)).toBe('13.0 kWh'))
  it('percent', () => expect(formatPercent(90)).toBe('90%'))
  it('power rounds watts', () => expect(formatPower(1136.4)).toBe('1136 W'))
})

describe('behavior', () => {
  it('labels grid_charging', () => expect(behaviorLabel('grid_charging')).toBe('Grid-charging'))
  it('tone for grid_charging is a cost warning', () =>
    expect(behaviorTone('grid_charging')).toBe('warn'))
  it('tone for solar_charging is good', () => expect(behaviorTone('solar_charging')).toBe('good'))
})

describe('purchase formatters', () => {
  it('formatRatePerKwh shows two decimals and unit', () => {
    expect(formatRatePerKwh(3.561)).toBe('R3.56/kWh')
  })

  it('formatUnits shows one decimal and unit', () => {
    expect(formatUnits(280.94)).toBe('280.9 units')
  })

  it('formatDate renders an ISO date as D Mon YYYY', () => {
    expect(formatDate('2026-04-12')).toBe('12 Apr 2026')
  })
})
