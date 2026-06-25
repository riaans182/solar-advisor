// tests/client.test.ts
import { afterEach, describe, expect, it, vi } from 'vitest'
import { getDashboard, getExplain, getHistory, ApiError } from '../src/api/client'

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
})
