// tests/purchase-form.test.ts
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import PurchaseForm from '../src/components/PurchaseForm.vue'

vi.mock('../src/api/client', () => ({
  createPurchase: vi.fn().mockResolvedValue({ id: 1 }),
}))
import { createPurchase } from '../src/api/client'

afterEach(() => vi.clearAllMocks())

function fill(w: ReturnType<typeof mount>, rand: string, units: string) {
  return Promise.all([
    w.get('input[name="purchased_at"]').setValue('2026-06-01'),
    w.get('input[name="rand"]').setValue(rand),
    w.get('input[name="units_kwh"]').setValue(units),
  ])
}

describe('PurchaseForm', () => {
  it('shows a live effective-rate preview', async () => {
    const w = mount(PurchaseForm)
    await fill(w, '1000', '250')
    expect(w.text()).toContain('R4.00/kWh')
  })

  it('blocks submit and shows an error when units are zero', async () => {
    const w = mount(PurchaseForm)
    await fill(w, '1000', '0')
    await w.get('form').trigger('submit.prevent')
    await flushPromises()
    expect(createPurchase).not.toHaveBeenCalled()
    expect(w.text().toLowerCase()).toContain('greater than 0')
  })

  it('submits a valid purchase and emits created', async () => {
    const w = mount(PurchaseForm)
    await fill(w, '1000', '250')
    await w.get('form').trigger('submit.prevent')
    await flushPromises()
    expect(createPurchase).toHaveBeenCalledWith({
      purchased_at: '2026-06-01',
      rand: 1000,
      units_kwh: 250,
      note: null,
    })
    expect(w.emitted('created')).toBeTruthy()
  })

  it('clears the rand and units fields after a successful submit', async () => {
    const w = mount(PurchaseForm)
    await fill(w, '1000', '250')
    await w.get('form').trigger('submit.prevent')
    await flushPromises()
    expect((w.get('input[name="rand"]').element as HTMLInputElement).value).toBe('')
    expect((w.get('input[name="units_kwh"]').element as HTMLInputElement).value).toBe('')
  })
})
