<script setup lang="ts">
import { computed } from 'vue'
import type { HistoryPoint } from '../api/types'

type Metric = 'battery_soc' | 'pv_power' | 'grid_power' | 'load_power'

const props = defineProps<{
  points: HistoryPoint[]
  metric: Metric
  label: string
  unit: string
}>()

// Fixed viewBox; the polyline is scaled into this space.
const W = 320
const H = 96
const PAD = 6

const values = computed(() => props.points.map((p) => p[props.metric]))

const latest = computed(() =>
  values.value.length ? values.value[values.value.length - 1] : null,
)

const bounds = computed(() => {
  const v = values.value
  if (!v.length) return { min: 0, max: 1 }
  let min = Math.min(...v)
  let max = Math.max(...v)
  if (min === max) {
    // Flat series: pad so the line sits mid-height.
    min -= 1
    max += 1
  }
  return { min, max }
})

function project(i: number): { x: number; y: number } {
  const n = props.points.length
  const { min, max } = bounds.value
  const x = n === 1 ? W / 2 : PAD + (i / (n - 1)) * (W - PAD * 2)
  const t = (values.value[i] - min) / (max - min)
  const y = H - PAD - t * (H - PAD * 2)
  return { x, y }
}

const polyline = computed(() =>
  props.points.map((_, i) => project(i)).map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' '),
)

// Area under the line for a soft fill.
const areaPath = computed(() => {
  if (!props.points.length) return ''
  const pts = props.points.map((_, i) => project(i))
  const start = `M ${pts[0].x.toFixed(1)} ${(H - PAD).toFixed(1)}`
  const line = pts.map((p) => `L ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')
  const end = `L ${pts[pts.length - 1].x.toFixed(1)} ${(H - PAD).toFixed(1)} Z`
  return `${start} ${line} ${end}`
})

const lastPoint = computed(() =>
  props.points.length ? project(props.points.length - 1) : null,
)

const gradientId = computed(() => `tc-grad-${props.metric}`)

function fmtLatest(v: number): string {
  const rounded = Math.abs(v) >= 100 ? Math.round(v) : Math.round(v * 10) / 10
  return `${rounded}${props.unit ? ` ${props.unit}` : ''}`
}
</script>

<template>
  <figure class="chart" :class="`chart--${metric}`">
    <figcaption class="chart__head">
      <span class="chart__label">{{ label }}</span>
      <span v-if="latest !== null" class="chart__latest">{{ fmtLatest(latest) }}</span>
    </figcaption>

    <div v-if="!points.length" class="chart__empty">
      <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
        <path d="M3 3v18h18" stroke-linecap="round" />
        <path d="M7 14l3-3 3 3 4-5" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="2 2" />
      </svg>
      <span>No data yet</span>
    </div>

    <svg
      v-else
      class="chart__svg"
      :viewBox="`0 0 ${W} ${H}`"
      preserveAspectRatio="none"
      role="img"
      :aria-label="`${label} trend over time`"
    >
      <defs>
        <linearGradient :id="gradientId" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="var(--line, #5aa9ff)" stop-opacity="0.28" />
          <stop offset="100%" stop-color="var(--line, #5aa9ff)" stop-opacity="0" />
        </linearGradient>
      </defs>
      <path :d="areaPath" :fill="`url(#${gradientId})`" stroke="none" />
      <polyline
        :points="polyline"
        fill="none"
        :stroke="`var(--line, #5aa9ff)`"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        vector-effect="non-scaling-stroke"
      />
      <circle
        v-if="lastPoint"
        :cx="lastPoint.x"
        :cy="lastPoint.y"
        r="3"
        :fill="`var(--line, #5aa9ff)`"
      />
    </svg>
  </figure>
</template>

<style scoped>
.chart {
  margin: 0;
  padding: 1rem 1.1rem 1.05rem;
  border-radius: 14px;
  background: var(--sa-surface, #161c24);
  border: 1px solid var(--sa-line, #273140);
  --line: var(--sa-accent, #5aa9ff);
}

.chart--battery_soc {
  --line: var(--sa-good, #34d399);
}
.chart--pv_power {
  --line: var(--sa-solar, #f5b942);
}
.chart--grid_power {
  --line: var(--sa-warn, #d8a83a);
}
.chart--load_power {
  --line: var(--sa-accent, #6aa6ff);
}

.chart__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.55rem;
}

.chart__label {
  font-size: 0.74rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
}

.chart__latest {
  font-size: 1.05rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--line);
}

.chart__svg {
  display: block;
  width: 100%;
  height: 72px;
}

.chart__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  height: 72px;
  color: var(--sa-text-dim, #6b7689);
  font-size: 0.82rem;
}
</style>
