// src/lib/format.ts
export const formatRand = (v: number): string => `R${v.toFixed(2)}`
export const formatKwh = (v: number): string => `${v.toFixed(1)} kWh`
export const formatPercent = (v: number): string => `${Math.round(v)}%`
export const formatPower = (watts: number): string => `${Math.round(watts)} W`
export const formatRatePerKwh = (v: number): string => `R${v.toFixed(2)}/kWh`
export const formatUnits = (v: number): string => `${v.toFixed(1)} units`

// A duration in hours as 'Xh Ym' (or 'Ym' under an hour). '—' for non-positive
// or non-finite inputs (e.g. an idle battery giving an infinite ETA).
export const formatDuration = (hours: number): string => {
  if (!Number.isFinite(hours) || hours <= 0) return '—'
  const totalMin = Math.round(hours * 60)
  const h = Math.floor(totalMin / 60)
  const m = totalMin % 60
  return h === 0 ? `${m}m` : `${h}h ${m}m`
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// Parse a 'YYYY-MM-DD' string without timezone shifts and render '12 Apr 2026'.
export const formatDate = (iso: string): string => {
  const [y, m, d] = iso.split('-').map(Number)
  return `${d} ${MONTHS[m - 1]} ${y}`
}
