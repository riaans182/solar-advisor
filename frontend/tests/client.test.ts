// tests/client.test.ts
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  getDashboard,
  getExplain,
  getHistory,
  getPurchases,
  createPurchase,
  deletePurchase,
  updatePurchase,
  ApiError,
} from '../src/api/client'

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response)
}

afterEach(() => vi.restoreAllMocks())

describe('api client', () => {
  it('getDashboard passes objective and returns parsed body', async () => {
    const fetchMock = mockFetch(200, { objective: 0.7, slots: [] })
    vi.stubGlobal('fetch', fetchMock)
    const data = await getDashboard(0.7)
    expect(data.objective).toBe(0.7)
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('objective=0.7'))
  })

  it('getHistory passes hours', async () => {
    const fetchMock = mockFetch(200, { points: [] })
    vi.stubGlobal('fetch', fetchMock)
    await getHistory(12)
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('hours=12'))
  })

  it('throws ApiError with status on non-2xx', async () => {
    vi.stubGlobal('fetch', mockFetch(503, { detail: 'not ready' }))
    await expect(getExplain(0.5)).rejects.toMatchObject({ status: 503 })
  })

  it('getPurchases returns the list', async () => {
    vi.stubGlobal('fetch', mockFetch(200, { purchases: [{ id: 1 }] }))
    const data = await getPurchases()
    expect(data.purchases).toHaveLength(1)
  })

  it('createPurchase POSTs the body and returns the created row', async () => {
    const fetchMock = mockFetch(201, { id: 7, effective_rate: 4.0 })
    vi.stubGlobal('fetch', fetchMock)
    const created = await createPurchase({
      purchased_at: '2026-06-01',
      rand: 1000,
      units_kwh: 250,
    })
    expect(created.id).toBe(7)
    const [, init] = fetchMock.mock.calls[0]
    expect(init).toMatchObject({ method: 'POST' })
    expect(JSON.parse((init as RequestInit).body as string)).toMatchObject({
      purchased_at: '2026-06-01',
      rand: 1000,
      units_kwh: 250,
    })
  })

  it('deletePurchase issues a DELETE', async () => {
    const fetchMock = mockFetch(204, {})
    vi.stubGlobal('fetch', fetchMock)
    await deletePurchase(7)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toContain('/api/purchases/7')
    expect(init).toMatchObject({ method: 'DELETE' })
  })

  it('updatePurchase PUTs the body to the id and returns the row', async () => {
    const fetchMock = mockFetch(200, { id: 5, rand: 900 })
    vi.stubGlobal('fetch', fetchMock)
    const updated = await updatePurchase(5, {
      purchased_at: '2026-06-02',
      rand: 900,
      units_kwh: 300,
    })
    expect(updated.id).toBe(5)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toContain('/api/purchases/5')
    expect(init).toMatchObject({ method: 'PUT' })
    expect(JSON.parse((init as RequestInit).body as string)).toMatchObject({ rand: 900 })
  })

  it('surfaces a FastAPI 422 array-detail message', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch(422, { detail: [{ msg: 'purchased_at cannot be in the future' }] }),
    )
    await expect(
      createPurchase({ purchased_at: '2999-01-01', rand: 1, units_kwh: 1 }),
    ).rejects.toMatchObject({ status: 422, message: 'purchased_at cannot be in the future' })
  })
})
