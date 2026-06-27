<script setup lang="ts">
import { computed } from 'vue'
import type { SlotView } from '../api/types'
import { formatPercent, formatRand } from '../lib/format'
import ScheduleTable from './ScheduleTable.vue'
import ScheduleSettings from './ScheduleSettings.vue'

const props = defineProps<{
  current: SlotView[]
  recommended: SlotView[]
  dailySaving: number
  currentCost: number
  recommendedCost: number
  reserveTargetSoc: number
  backupHours: number
}>()

const changedSlots = computed(() =>
  props.current
    .map((s, i) => {
      const r = props.recommended[i]
      const changed = !r || s.grid_charge !== r.grid_charge || s.target_soc !== r.target_soc
      return { n: i + 1, changed }
    })
    .filter((x) => x.changed)
    .map((x) => x.n),
)

const matches = computed(() => changedSlots.value.length === 0)
</script>

<template>
  <section class="cmp" aria-label="Schedule recommendation">
    <p v-if="matches" class="cmp__ok" role="status">
      Your inverter schedule already matches the advice — nothing to change.
    </p>
    <p v-else class="cmp__action" role="status">
      <strong>Save ≈ {{ formatRand(dailySaving) }}/day</strong> — switch to the recommended schedule
      (today {{ formatRand(currentCost) }} → {{ formatRand(recommendedCost) }}). Changes in
      slot{{ changedSlots.length > 1 ? 's' : '' }} {{ changedSlots.join(', ') }}.
      <span class="cmp__tradeoff">
        You'd still keep ~{{ backupHours.toFixed(1) }} h of essential backup (your
        {{ formatPercent(reserveTargetSoc) }} reserve) — solar refills the battery and the inverter
        won't discharge below that floor. Want a bigger buffer for unexpected outages? Raise the
        resilience slider — it keeps grid-charging to a higher SOC (the saving shrinks to pay for it).
      </span>
    </p>

    <div class="cmp__tables">
      <ScheduleTable :slots="current" title="Today's plan" />
      <ScheduleSettings v-if="!matches" :current="current" :recommended="recommended" />
    </div>
  </section>
</template>

<style scoped>
.cmp {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.cmp__action,
.cmp__ok {
  margin: 0;
  padding: 0.85rem 1.05rem;
  border-radius: 12px;
  font-size: 0.92rem;
  line-height: 1.5;
}
.cmp__action {
  background: var(--sa-warn-soft, #d8a83a14);
  border: 1px solid var(--sa-warn-line, #d8a83a44);
  color: var(--sa-text, #eef2f7);
}
.cmp__action strong {
  color: var(--sa-warn, #e0b54a);
}
.cmp__tradeoff {
  display: block;
  margin-top: 0.5rem;
  font-size: 0.86rem;
  line-height: 1.5;
  color: var(--sa-text-dim, #c2ccda);
}
.cmp__ok {
  background: var(--sa-good-soft, #34d39912);
  border: 1px solid var(--sa-good-line, #34d39930);
  color: var(--sa-text, #eef2f7);
}
.cmp__tables {
  display: grid;
  gap: 1rem;
}
</style>
