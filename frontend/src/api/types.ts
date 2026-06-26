// src/api/types.ts
export type SlotBehavior = 'solar_charging' | 'grid_charging' | 'discharging' | 'holding'

export interface SlotView {
  start: string
  end: string
  target_soc: number
  grid_charge: boolean
  behavior: SlotBehavior
  end_soc: number
  grid_import_kwh: number
  cost: number
}

export interface RecommendationView {
  reserve_target_soc: number
  enable_overnight_grid_charge: boolean
  grid_charge_kwh: number
  expected_daily_grid_import_kwh: number
  expected_daily_cost: number
  backup_hours: number
  monthly_cost_so_far: number
}

export interface DashboardView {
  objective: number
  battery_soc: number
  pv_power: number
  grid_power: number
  load_power: number
  battery_power: number
  conversion_power: number
  month_to_date_grid_import_kwh: number
  usable_kwh: number
  usable_kwh_confidence: number
  daily_consumption_kwh: number
  daily_consumption_confidence: number
  tariff_rate: number
  tariff_source: string
  tariff_source_date: string | null
  expected_pv_kwh_today: number
  expected_pv_kwh_tomorrow: number
  slots: SlotView[]
  recommendation: RecommendationView
  disclaimer: string
}

export interface ExplanationView {
  explanation: string
  generated: boolean
  guard_ok: boolean
  unverified_numbers: number[]
  disclaimer: string
}

export interface HistoryPoint {
  ts: string
  battery_soc: number
  pv_power: number
  grid_power: number
  load_power: number
  battery_power: number
}

export interface HistoryView {
  points: HistoryPoint[]
}

export interface PurchaseCreate {
  purchased_at: string // YYYY-MM-DD
  rand: number
  units_kwh: number
  note?: string | null
}

export interface PurchaseView {
  id: number
  purchased_at: string
  rand: number
  units_kwh: number
  note: string | null
  effective_rate: number
}

export interface PurchaseListView {
  purchases: PurchaseView[]
}
