// src/api/client.ts
import type {
  DashboardView,
  ExplanationView,
  HistoryView,
  PurchaseCreate,
  PurchaseListView,
  PurchaseView,
} from './types'

const BASE = import.meta.env.VITE_API_BASE ?? ''

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

// FastAPI returns `detail` as a string for HTTPException and as an array of
// {msg,...} for 422 validation errors. Surface a useful message for both.
async function failure(resp: Response): Promise<ApiError> {
  let detail = resp.statusText
  try {
    const body = (await resp.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') {
      detail = body.detail
    } else if (Array.isArray(body.detail) && body.detail.length > 0) {
      const first = body.detail[0] as { msg?: string }
      if (first.msg) detail = first.msg
    }
  } catch {
    // non-JSON body; keep statusText
  }
  return new ApiError(resp.status, detail)
}

async function getJson<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`)
  if (!resp.ok) throw await failure(resp)
  return (await resp.json()) as T
}

export function getDashboard(objective: number): Promise<DashboardView> {
  return getJson<DashboardView>(`/api/dashboard?objective=${objective}`)
}

export function getExplain(objective: number): Promise<ExplanationView> {
  return getJson<ExplanationView>(`/api/explain?objective=${objective}`)
}

export function getHistory(hours: number): Promise<HistoryView> {
  return getJson<HistoryView>(`/api/history?hours=${hours}`)
}

export function getPurchases(): Promise<PurchaseListView> {
  return getJson<PurchaseListView>('/api/purchases')
}

export async function createPurchase(body: PurchaseCreate): Promise<PurchaseView> {
  const resp = await fetch(`${BASE}/api/purchases`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!resp.ok) throw await failure(resp)
  return (await resp.json()) as PurchaseView
}

export async function deletePurchase(id: number): Promise<void> {
  const resp = await fetch(`${BASE}/api/purchases/${id}`, { method: 'DELETE' })
  if (!resp.ok) throw await failure(resp)
}
