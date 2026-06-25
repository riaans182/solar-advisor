// tests/tariff-badge.test.ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TariffBadge from '../src/components/TariffBadge.vue'

describe('TariffBadge', () => {
  it('shows the rate and purchase provenance with a date', () => {
    const w = mount(TariffBadge, {
      props: { rate: 3.56, source: 'purchase', sourceDate: '2026-04-12' },
    })
    expect(w.text()).toContain('R3.56/kWh')
    expect(w.text()).toContain('12 Apr 2026')
  })

  it('explains the config fallback when there is no purchase history', () => {
    const w = mount(TariffBadge, {
      props: { rate: 3.56, source: 'config', sourceDate: null },
    })
    expect(w.text().toLowerCase()).toContain('config default')
  })

  it('falls back to the config message when a purchase source has no date', () => {
    const w = mount(TariffBadge, {
      props: { rate: 3.56, source: 'purchase', sourceDate: null },
    })
    expect(w.text().toLowerCase()).toContain('config default')
  })
})
