<script setup lang="ts">
import { computed } from 'vue'
import type { DashboardView } from '../api/types'
import { formatKwh, formatPercent, formatPower } from '../lib/format'

const props = defineProps<{ dashboard: DashboardView }>()

const gridFlow = computed(() => {
  const p = props.dashboard.grid_power
  if (p > 0) return { label: 'importing', tone: 'warn' as const }
  if (p < 0) return { label: 'exporting', tone: 'good' as const }
  return { label: 'idle', tone: 'neutral' as const }
})

// SOC drives a subtle good→warn tone so a low battery reads as a caution.
const socTone = computed(() => {
  const soc = props.dashboard.battery_soc
  if (soc >= 50) return 'good' as const
  if (soc >= 20) return 'warn' as const
  return 'bad' as const
})

const batteryFlow = computed(() => {
  const p = props.dashboard.battery_power
  const capWh = props.dashboard.usable_kwh * 1000
  const rate = capWh > 0 ? (p / capWh) * 100 : 0 // %/h
  if (p > 1) return `charging ${Math.round(p)} W · +${rate.toFixed(1)}%/h`
  if (p < -1) return `discharging ${Math.round(-p)} W · ${rate.toFixed(1)}%/h`
  return 'idle'
})

const conversion = computed(() => Math.max(0, Math.round(props.dashboard.conversion_power)))
</script>

<template>
  <section class="tiles" aria-label="Live system readings">
    <article class="tile" :data-tone="socTone">
      <header class="tile__head">
        <span class="tile__icon" aria-hidden="true">
          <svg
            viewBox="0 0 24 24"
            width="18"
            height="18"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
          >
            <rect x="2" y="7" width="16" height="10" rx="2" />
            <path d="M20 10v4" stroke-linecap="round" />
            <rect x="4" y="9" width="10" height="6" rx="1" fill="currentColor" stroke="none" />
          </svg>
        </span>
        <span class="tile__label">Battery</span>
      </header>
      <p class="tile__value">{{ formatPercent(dashboard.battery_soc) }}</p>
      <p class="tile__sub">{{ batteryFlow }}</p>
      <div class="tile__bar" aria-hidden="true">
        <span :style="{ width: Math.min(100, Math.max(0, dashboard.battery_soc)) + '%' }" />
      </div>
    </article>

    <article class="tile" data-tone="solar">
      <header class="tile__head">
        <span class="tile__icon" aria-hidden="true">
          <svg
            viewBox="0 0 24 24"
            width="18"
            height="18"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
          >
            <circle cx="12" cy="12" r="4" />
            <path
              d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"
              stroke-linecap="round"
            />
          </svg>
        </span>
        <span class="tile__label">Solar</span>
      </header>
      <p class="tile__value">{{ formatPower(dashboard.pv_power) }}</p>
      <p class="tile__sub">generating now</p>
    </article>

    <article class="tile" :data-tone="gridFlow.tone">
      <header class="tile__head">
        <span class="tile__icon" aria-hidden="true">
          <svg
            viewBox="0 0 24 24"
            width="18"
            height="18"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
          >
            <path d="M9 2 4 12h5l-1 10 9-13h-6l2-7z" stroke-linejoin="round" />
          </svg>
        </span>
        <span class="tile__label">Grid</span>
      </header>
      <p class="tile__value">{{ formatPower(Math.abs(dashboard.grid_power)) }}</p>
      <p class="tile__sub">{{ gridFlow.label }}</p>
    </article>

    <article class="tile" data-tone="neutral">
      <header class="tile__head">
        <span class="tile__icon" aria-hidden="true">
          <svg
            viewBox="0 0 24 24"
            width="18"
            height="18"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
          >
            <path d="M3 21V8l9-5 9 5v13" stroke-linejoin="round" />
            <path d="M9 21v-7h6v7" stroke-linejoin="round" />
          </svg>
        </span>
        <span class="tile__label">Load</span>
      </header>
      <p class="tile__value">{{ formatPower(dashboard.load_power) }}</p>
      <p class="tile__sub">household demand</p>
    </article>

    <article class="tile" data-tone="neutral">
      <header class="tile__head">
        <span class="tile__icon" aria-hidden="true">
          <svg
            viewBox="0 0 24 24"
            width="18"
            height="18"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
          >
            <path d="M12 3v18M5 8l7-5 7 5M5 16l7 5 7-5" stroke-linejoin="round" />
          </svg>
        </span>
        <span class="tile__label">Conversion / idle</span>
      </header>
      <p class="tile__value">{{ formatPower(conversion) }}</p>
      <p class="tile__sub">inverter overhead + losses</p>
    </article>

    <article class="tile" data-tone="solar">
      <header class="tile__head">
        <span class="tile__icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8">
            <path d="M3 12h2M19 12h2M12 3v2M5.6 5.6l1.4 1.4M17 17l1.4 1.4" stroke-linecap="round" />
            <path d="M8 18a4 4 0 0 1 8 0" stroke-linecap="round" />
            <path d="M12 9a3 3 0 0 0-3 3h6a3 3 0 0 0-3-3Z" />
          </svg>
        </span>
        <span class="tile__label">Solar forecast</span>
      </header>
      <p class="tile__value">{{ formatKwh(dashboard.expected_pv_kwh_today) }}</p>
      <p class="tile__sub">{{ formatKwh(dashboard.expected_pv_kwh_tomorrow) }} tomorrow</p>
    </article>
  </section>
</template>

<style scoped>
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 0.9rem;
}

.tile {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  padding: 1.1rem 1.15rem 1.2rem;
  border-radius: 16px;
  background: var(--sa-surface, #161c24);
  border: 1px solid var(--sa-line, #273140);
  overflow: hidden;
}

.tile::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  background: var(--accent, #5b6678);
}

.tile[data-tone='good'] {
  --accent: var(--sa-good, #34d399);
}
.tile[data-tone='warn'] {
  --accent: var(--sa-warn, #d8a83a);
}
.tile[data-tone='bad'] {
  --accent: var(--sa-bad, #ef6b6b);
}
.tile[data-tone='solar'] {
  --accent: var(--sa-solar, #f5b942);
}
.tile[data-tone='neutral'] {
  --accent: var(--sa-muted, #6b7689);
}

.tile__head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--accent);
}

.tile__label {
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
}

.tile__icon {
  display: inline-flex;
}

.tile__value {
  margin: 0.35rem 0 0;
  font-size: clamp(1.7rem, 4vw, 2.1rem);
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--sa-text, #eef2f7);
  font-variant-numeric: tabular-nums;
}

.tile__sub {
  margin: 0;
  font-size: 0.8rem;
  color: var(--sa-text-dim, #9aa6b6);
}

.tile__bar {
  margin-top: 0.7rem;
  height: 5px;
  border-radius: 999px;
  background: var(--sa-track, #0e131a);
  overflow: hidden;
}

.tile__bar span {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: var(--accent);
  transition: width 0.4s ease;
}
</style>
