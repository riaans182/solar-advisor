<script setup lang="ts">
import { computed } from 'vue'
import type { RecommendationView } from '../api/types'
import { formatKwh, formatPercent, formatRand } from '../lib/format'

const props = defineProps<{ recommendation: RecommendationView }>()
const r = computed(() => props.recommendation)
</script>

<template>
  <section class="rec" aria-label="Recommendation">
    <header class="rec__head">
      <h3 class="rec__title">Recommendation</h3>
      <span class="rec__pill rec__pill--cost">Cost</span>
      <span class="rec__pill rec__pill--res">Resilience</span>
    </header>

    <div class="rec__grid">
      <div class="metric metric--res">
        <span class="metric__label">Reserve target</span>
        <span class="metric__value">{{ formatPercent(r.reserve_target_soc) }}</span>
        <span class="metric__note">floor held for backup</span>
      </div>

      <div class="metric metric--res">
        <span class="metric__label">Backup runtime</span>
        <span class="metric__value">{{ r.backup_hours.toFixed(1) }}<small> h</small></span>
        <span class="metric__note">if the grid drops now</span>
      </div>

      <div class="metric metric--cost">
        <span class="metric__label">Expected daily cost</span>
        <span class="metric__value">{{ formatRand(r.expected_daily_cost) }}</span>
        <span class="metric__note">
          {{ formatKwh(r.expected_daily_grid_import_kwh) }} grid import
        </span>
      </div>

      <div class="metric metric--cost">
        <span class="metric__label">Bill so far</span>
        <span class="metric__value">{{ formatRand(r.monthly_cost_so_far) }}</span>
        <span class="metric__note">month to date</span>
      </div>
    </div>

    <div
      class="rec__charge"
      :data-active="r.enable_overnight_grid_charge"
      role="status"
    >
      <span class="rec__charge-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.9">
          <path d="M13 2 4 14h6l-1 8 9-12h-6l1-8z" stroke-linejoin="round" />
        </svg>
      </span>
      <span v-if="r.enable_overnight_grid_charge" class="rec__charge-text">
        Overnight grid charge advised —
        <strong>{{ formatKwh(r.grid_charge_kwh) }}</strong> from the grid buys resilience at a cost.
      </span>
      <span v-else class="rec__charge-text">
        No overnight grid charge needed — solar should cover the reserve.
      </span>
    </div>
  </section>
</template>

<style scoped>
.rec {
  padding: 1.25rem 1.35rem 1.4rem;
  border-radius: 16px;
  background: var(--sa-surface, #161c24);
  border: 1px solid var(--sa-line, #273140);
}

.rec__head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1.1rem;
}

.rec__title {
  margin: 0 auto 0 0;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
}

.rec__pill {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.rec__pill::before {
  content: '';
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}

.rec__pill--cost {
  color: var(--sa-solar, #f5b942);
  background: var(--sa-solar-soft, #f5b94215);
}

.rec__pill--res {
  color: var(--sa-good, #34d399);
  background: var(--sa-good-soft, #34d39915);
}

.rec__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(135px, 1fr));
  gap: 0.85rem;
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 0.18rem;
  padding: 0.85rem 0.9rem;
  border-radius: 12px;
  background: var(--sa-track, #0e131a);
  border-left: 3px solid var(--mtone, #5b6678);
}

.metric--cost {
  --mtone: var(--sa-solar, #f5b942);
}

.metric--res {
  --mtone: var(--sa-good, #34d399);
}

.metric__label {
  font-size: 0.74rem;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
}

.metric__value {
  font-size: 1.5rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--sa-text, #eef2f7);
  font-variant-numeric: tabular-nums;
}

.metric__value small {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--sa-text-dim, #9aa6b6);
}

.metric__note {
  font-size: 0.76rem;
  color: var(--sa-text-dim, #9aa6b6);
}

.rec__charge {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  margin-top: 1rem;
  padding: 0.75rem 0.95rem;
  border-radius: 12px;
  font-size: 0.86rem;
  line-height: 1.45;
  background: var(--sa-good-soft, #34d39912);
  border: 1px solid var(--sa-good-line, #34d39930);
  color: var(--sa-text, #eef2f7);
}

.rec__charge[data-active='true'] {
  background: var(--sa-warn-soft, #d8a83a14);
  border-color: var(--sa-warn-line, #d8a83a3a);
}

.rec__charge-icon {
  display: inline-flex;
  flex-shrink: 0;
  color: var(--sa-good, #34d399);
}

.rec__charge[data-active='true'] .rec__charge-icon {
  color: var(--sa-warn, #d8a83a);
}

.rec__charge-text strong {
  color: var(--sa-warn, #d8a83a);
}
</style>
