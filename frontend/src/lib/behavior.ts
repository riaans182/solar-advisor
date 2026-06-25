// src/lib/behavior.ts
import type { SlotBehavior } from '../api/types'

export type Tone = 'good' | 'warn' | 'neutral'

const LABELS: Record<SlotBehavior, string> = {
  solar_charging: 'Solar-charging',
  grid_charging: 'Grid-charging',
  discharging: 'Discharging',
  holding: 'Holding',
}

const TONES: Record<SlotBehavior, Tone> = {
  solar_charging: 'good',
  grid_charging: 'warn', // pure cost under a flat tariff
  discharging: 'neutral',
  holding: 'neutral',
}

export const behaviorLabel = (b: SlotBehavior): string => LABELS[b]
export const behaviorTone = (b: SlotBehavior): Tone => TONES[b]
