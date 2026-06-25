// src/lib/format.ts
export const formatRand = (v: number): string => `R${v.toFixed(2)}`
export const formatKwh = (v: number): string => `${v.toFixed(1)} kWh`
export const formatPercent = (v: number): string => `${Math.round(v)}%`
export const formatPower = (watts: number): string => `${Math.round(watts)} W`
export const formatRatePerKwh = (v: number): string => `R${v.toFixed(2)}/kWh`
export const formatUnits = (v: number): string => `${v.toFixed(1)} units`

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// Parse a 'YYYY-MM-DD' string without timezone shifts and render '12 Apr 2026'.
export const formatDate = (iso: string): string => {
  const [y, m, d] = iso.split('-').map(Number)
  return `${d} ${MONTHS[m - 1]} ${y}`
}
