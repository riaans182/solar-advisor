// src/api/client.ts
import type { DashboardView, ExplanationView, HistoryView } from './types'

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

async function getJson<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`)
  if (!resp.ok) {
    let detail = resp.statusText
    try {
      detail = ((await resp.json()) as { detail?: string }).detail ?? detail
    } catch {
      // non-JSON body; keep statusText
    }
    throw new ApiError(resp.status, detail)
  }
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
