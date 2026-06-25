// src/lib/format.ts
export const formatRand = (v: number): string => `R${v.toFixed(2)}`
export const formatKwh = (v: number): string => `${v.toFixed(1)} kWh`
export const formatPercent = (v: number): string => `${Math.round(v)}%`
export const formatPower = (watts: number): string => `${Math.round(watts)} W`
