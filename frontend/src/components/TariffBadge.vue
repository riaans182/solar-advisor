<script setup lang="ts">
import { computed } from 'vue'
import { formatDate, formatRatePerKwh } from '../lib/format'

const props = defineProps<{
  rate: number
  source: string
  sourceDate: string | null
}>()

const provenance = computed(() =>
  props.source === 'purchase' && props.sourceDate
    ? `from your purchase on ${formatDate(props.sourceDate)}`
    : 'config default — log a purchase to track the real rate',
)
</script>

<template>
  <section class="tb" :data-source="source" aria-label="Current tariff rate">
    <span class="tb__label">Tariff</span>
    <span class="tb__rate">{{ formatRatePerKwh(rate) }}</span>
    <span class="tb__prov">{{ provenance }}</span>
  </section>
</template>

<style scoped>
.tb {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding: 1rem 1.1rem;
  border-radius: 14px;
  background: var(--sa-surface, #161c24);
  border: 1px solid var(--sa-line, #273140);
}
.tb__label {
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
}
.tb__rate {
  font-size: 1.4rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--sa-solar, #f5b942);
}
.tb__prov {
  font-size: 0.78rem;
  color: var(--sa-text-dim, #9aa6b6);
}
.tb[data-source='config'] .tb__rate {
  color: var(--sa-text-dim, #9aa6b6);
}
</style>
