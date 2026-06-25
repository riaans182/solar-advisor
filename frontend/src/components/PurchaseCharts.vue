<script setup lang="ts">
import { computed } from 'vue'
import type { PurchaseView } from '../api/types'
import { formatRatePerKwh } from '../lib/format'

const props = defineProps<{
  purchases: PurchaseView[]
  currentRate: number
}>()

const W = 320
const H = 110
const PAD = 10

// Newest-first from the API; charts read left→right oldest→newest.
const chrono = computed(() => [...props.purchases].reverse())

const rates = computed(() => chrono.value.map((p) => p.effective_rate))
const spend = computed(() => chrono.value.map((p) => p.rand))
const units = computed(() => chrono.value.map((p) => p.units_kwh))

function xFor(i: number, n: number): number {
  if (n <= 1) return W / 2
  return PAD + (i / (n - 1)) * (W - PAD * 2)
}

// Line projection for the rate series; includes currentRate so the reference
// line sits inside the same vertical scale.
const rateGeom = computed(() => {
  const vals = rates.value
  const n = vals.length
  const all = [...vals, props.currentRate]
  let min = Math.min(...all)
  let max = Math.max(...all)
  if (min === max) {
    min -= 0.5
    max += 0.5
  }
  const y = (v: number): number => H - PAD - ((v - min) / (max - min)) * (H - PAD * 2)
  const line = vals.map((v, i) => `${xFor(i, n).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  return { line, refY: y(props.currentRate).toFixed(1) }
})

// Bar geometry for a non-negative series.
function bars(values: number[]): { x: number; y: number; w: number; h: number }[] {
  const n = values.length
  if (!n) return []
  const max = Math.max(...values, 0) || 1
  const slot = (W - PAD * 2) / n
  const bw = Math.max(2, slot * 0.6)
  return values.map((v, i) => {
    const h = (v / max) * (H - PAD * 2)
    return {
      x: PAD + i * slot + (slot - bw) / 2,
      y: H - PAD - h,
      w: bw,
      h,
    }
  })
}

const spendBars = computed(() => bars(spend.value))
const unitsBars = computed(() => bars(units.value))
const hasData = computed(() => props.purchases.length > 0)
</script>

<template>
  <section class="pc" aria-label="Purchase history charts">
    <h2 class="pc__title">Trends</h2>
    <p v-if="!hasData" class="pc__empty">No purchases to chart yet.</p>
    <div v-else class="pc__grid">
      <figure class="pc__chart">
        <figcaption class="pc__cap">
          Effective rate
          <span class="pc__cap-now">now {{ formatRatePerKwh(currentRate) }}</span>
        </figcaption>
        <svg
          :viewBox="`0 0 ${W} ${H}`"
          class="pc__svg"
          role="img"
          aria-label="Effective rate over time"
        >
          <line
            data-test="rate-ref"
            :x1="PAD"
            :x2="W - PAD"
            :y1="rateGeom.refY"
            :y2="rateGeom.refY"
            stroke="var(--sa-text-dim, #9aa6b6)"
            stroke-width="1"
            stroke-dasharray="4 3"
            vector-effect="non-scaling-stroke"
          />
          <polyline
            data-test="rate-line"
            :points="rateGeom.line"
            fill="none"
            stroke="var(--sa-solar, #f5b942)"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            vector-effect="non-scaling-stroke"
          />
        </svg>
      </figure>

      <figure class="pc__chart">
        <figcaption class="pc__cap">Rand spent</figcaption>
        <svg
          :viewBox="`0 0 ${W} ${H}`"
          class="pc__svg"
          role="img"
          aria-label="Rand spent per purchase"
        >
          <rect
            v-for="(b, i) in spendBars"
            :key="i"
            data-test="spend-bar"
            :x="b.x"
            :y="b.y"
            :width="b.w"
            :height="b.h"
            rx="1.5"
            fill="var(--sa-accent, #5aa9ff)"
          />
        </svg>
      </figure>

      <figure class="pc__chart">
        <figcaption class="pc__cap">Units received</figcaption>
        <svg
          :viewBox="`0 0 ${W} ${H}`"
          class="pc__svg"
          role="img"
          aria-label="Units received per purchase"
        >
          <rect
            v-for="(b, i) in unitsBars"
            :key="i"
            data-test="units-bar"
            :x="b.x"
            :y="b.y"
            :width="b.w"
            :height="b.h"
            rx="1.5"
            fill="var(--sa-good, #34d399)"
          />
        </svg>
      </figure>
    </div>
  </section>
</template>

<style scoped>
.pc {
  padding: 1.25rem 1.35rem 1.4rem;
  border-radius: 16px;
  background: var(--sa-surface, #161c24);
  border: 1px solid var(--sa-line, #273140);
}
.pc__title {
  margin: 0 0 0.9rem;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
}
.pc__empty {
  margin: 0;
  color: var(--sa-text-dim, #6b7689);
  font-size: 0.9rem;
}
.pc__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0.9rem;
}
.pc__chart {
  margin: 0;
}
.pc__cap {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
  font-size: 0.74rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
  margin-bottom: 0.5rem;
}
.pc__cap-now {
  color: var(--sa-solar, #f5b942);
}
.pc__svg {
  display: block;
  width: 100%;
  height: 96px;
}
</style>
