// tests/explain-panel.test.ts
import { describe, expect, it, vi, afterEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ExplainPanel from '../src/components/ExplainPanel.vue'

function stubFetch(body: unknown, status = 200) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: status < 300, status, json: async () => body } as Response),
  )
}
afterEach(() => vi.restoreAllMocks())

it('shows a withheld warning when guard_ok is false', async () => {
  stubFetch({
    explanation: 'An explanation could not be verified...',
    generated: true,
    guard_ok: false,
    unverified_numbers: [777],
    disclaimer: 'Advisory only.',
  })
  const w = mount(ExplainPanel, { props: { objective: 0.5 } })
  await w.get('button').trigger('click')
  await flushPromises()
  expect(w.text().toLowerCase()).toContain('withheld')
  expect(w.text()).toContain('777')
})

it('renders a generated explanation', async () => {
  stubFetch({
    explanation: 'Your battery grid-charges overnight.',
    generated: true,
    guard_ok: true,
    unverified_numbers: [],
    disclaimer: 'Advisory only.',
  })
  const w = mount(ExplainPanel, { props: { objective: 1 } })
  await w.get('button').trigger('click')
  await flushPromises()
  expect(w.text()).toContain('grid-charges overnight')
})
