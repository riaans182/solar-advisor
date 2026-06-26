// tests/purchases-view.test.ts
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import Purchases from '../src/views/Purchases.vue'

const getPurchases = vi.fn()
const getDashboard = vi.fn()
const deletePurchase = vi.fn().mockResolvedValue(undefined)
const updatePurchase = vi.fn().mockResolvedValue({})

vi.mock('../src/api/client', () => ({
  getPurchases: () => getPurchases(),
  getDashboard: () => getDashboard(),
  deletePurchase: (id: number) => deletePurchase(id),
  updatePurchase: (id: number, body: unknown) => updatePurchase(id, body),
  createPurchase: vi.fn(),
  ApiError: class ApiError extends Error {},
}))

function listOf(rate: number) {
  return {
    purchases: [
      { id: 1, purchased_at: '2026-06-01', rand: 1000, units_kwh: 250, note: null, effective_rate: rate },
    ],
  }
}

afterEach(() => vi.clearAllMocks())

describe('Purchases view', () => {
  it('loads purchases and the derived tariff on mount', async () => {
    getPurchases.mockResolvedValue(listOf(4.0))
    getDashboard.mockResolvedValue({ tariff_rate: 3.56, tariff_source: 'purchase', tariff_source_date: '2026-06-01' })
    const w = mount(Purchases)
    await flushPromises()
    expect(w.text()).toContain('R4.00/kWh') // table row
    expect(w.text()).toContain('R3.56/kWh') // tariff badge
  })

  it('refetches after a delete', async () => {
    getPurchases.mockResolvedValue(listOf(4.0))
    getDashboard.mockResolvedValue({ tariff_rate: 3.56, tariff_source: 'config', tariff_source_date: null })
    const w = mount(Purchases)
    await flushPromises()
    getPurchases.mockClear()
    await w.get('[data-test="del-1"]').trigger('click')
    await w.get('[data-test="confirm-1"]').trigger('click')
    await flushPromises()
    expect(deletePurchase).toHaveBeenCalledWith(1)
    expect(getPurchases).toHaveBeenCalled() // list refreshed
  })

  it('keeps the log form collapsed until the button is clicked', async () => {
    getPurchases.mockResolvedValue({ purchases: [] })
    getDashboard.mockResolvedValue({ tariff_rate: 3.56, tariff_source: 'config', tariff_source_date: null })
    const w = mount(Purchases)
    await flushPromises()
    expect(w.find('form.pf').exists()).toBe(false)
    await w.get('[data-test="toggle-form"]').trigger('click')
    expect(w.find('form.pf').exists()).toBe(true)
  })

  it('calls updatePurchase and refreshes on row update', async () => {
    getPurchases.mockResolvedValue({
      purchases: [
        { id: 1, purchased_at: '2026-06-01', rand: 1000, units_kwh: 250, note: null, effective_rate: 4 },
      ],
    })
    getDashboard.mockResolvedValue({ tariff_rate: 3.56, tariff_source: 'config', tariff_source_date: null })
    const w = mount(Purchases)
    await flushPromises()
    getPurchases.mockClear()
    await w.get('[data-test="edit-1"]').trigger('click')
    await w.get('[data-test="save-1"]').trigger('click')
    await flushPromises()
    expect(updatePurchase).toHaveBeenCalled()
    expect(getPurchases).toHaveBeenCalled()
  })
})
