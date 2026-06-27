<script setup lang="ts">
import { computed } from 'vue'
import type { SlotView } from '../api/types'
import { formatPercent } from '../lib/format'

const props = defineProps<{ current: SlotView[]; recommended: SlotView[] }>()

interface Row {
  time: string
  soc: number
  socChanged: boolean
  socWas: number
  charge: boolean
  chargeChanged: boolean
  chargeWas: boolean
}

const rows = computed<Row[]>(() =>
  props.recommended.map((r, i) => {
    const c = props.current[i]
    return {
      time: `${r.start}–${r.end}`,
      soc: r.target_soc,
      socChanged: !!c && c.target_soc !== r.target_soc,
      socWas: c ? c.target_soc : r.target_soc,
      charge: r.grid_charge,
      chargeChanged: !!c && c.grid_charge !== r.grid_charge,
      chargeWas: c ? c.grid_charge : r.grid_charge,
    }
  }),
)

function onOff(v: boolean): string {
  return v ? 'On' : 'Off'
}
</script>

<template>
  <section class="set" aria-label="Recommended inverter settings">
    <header class="set__head">
      <h3 class="set__title">Recommended inverter settings</h3>
      <p class="set__hint">Set these per time slot on your inverter</p>
    </header>

    <div class="set__scroll" role="region" aria-label="Settings per slot" tabindex="0">
      <table class="set__table">
        <thead>
          <tr>
            <th scope="col">Time</th>
            <th scope="col" class="num">State of charge</th>
            <th scope="col">Charge <span class="set__qual">(grid)</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in rows" :key="i">
            <td class="set__time">{{ row.time }}</td>
            <td class="num" :class="{ 'is-changed': row.socChanged }" :data-test="`soc-${i}`">
              {{ formatPercent(row.soc) }}
              <span v-if="row.socChanged" class="set__was">(was {{ formatPercent(row.socWas) }})</span>
            </td>
            <td :class="{ 'is-changed': row.chargeChanged }" :data-test="`charge-${i}`">
              {{ onOff(row.charge) }}
              <span v-if="row.chargeChanged" class="set__was">(was {{ onOff(row.chargeWas) }})</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p class="set__foot">
      Only State of charge and Charge change. Leave Power as-is; Sell stays off (zero-export).
    </p>
  </section>
</template>

<style scoped>
.set {
  padding: 1.25rem 1.35rem 1.4rem;
  border-radius: 16px;
  background: var(--sa-surface, #161c24);
  border: 1px solid var(--sa-line, #273140);
}
.set__head {
  margin-bottom: 0.9rem;
}
.set__title {
  margin: 0;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
}
.set__hint {
  margin: 0.2rem 0 0;
  font-size: 0.82rem;
  color: var(--sa-text-dim, #9aa6b6);
}
.set__scroll {
  overflow-x: auto;
}
.set__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}
.set__table th {
  text-align: left;
  padding: 0.4rem 0.6rem;
  font-size: 0.7rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
  border-bottom: 1px solid var(--sa-line, #273140);
}
.set__table th.num,
.set__table td.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.set__table td {
  padding: 0.55rem 0.6rem;
  border-bottom: 1px solid var(--sa-line, #1f2733);
  color: var(--sa-text, #eef2f7);
}
.set__qual {
  font-weight: 400;
  text-transform: none;
  letter-spacing: 0;
  color: var(--sa-text-dim, #6b7689);
}
.is-changed {
  background: var(--sa-warn-soft, #d8a83a14);
  color: var(--sa-warn, #e0b54a);
  font-weight: 600;
}
.set__was {
  font-size: 0.76rem;
  font-weight: 400;
  color: var(--sa-text-dim, #9aa6b6);
}
.set__foot {
  margin: 0.85rem 0 0;
  font-size: 0.78rem;
  color: var(--sa-text-dim, #9aa6b6);
}
</style>
