<script setup lang="ts">
import type { SlotView } from '../api/types'
import { behaviorLabel, behaviorTone } from '../lib/behavior'
import { formatKwh, formatPercent, formatRand } from '../lib/format'

const props = withDefaults(defineProps<{ slots: SlotView[]; title?: string }>(), {
  title: "Today's plan",
})
</script>

<template>
  <section class="schedule" aria-label="Planned battery schedule">
    <header class="schedule__head">
      <h3 class="schedule__title">{{ props.title }}</h3>
      <p class="schedule__hint">{{ slots.length }} slots · per-slot cost &amp; behaviour</p>
    </header>

    <div v-if="!slots.length" class="schedule__empty">No schedule loaded yet</div>

    <div v-else class="schedule__scroll" role="region" aria-label="Schedule slots" tabindex="0">
      <table class="schedule__table">
        <thead>
          <tr>
            <th scope="col">Window</th>
            <th scope="col">Behaviour</th>
            <th scope="col" class="num">Target</th>
            <th scope="col" class="num">End SOC</th>
            <th scope="col" class="num">Grid in</th>
            <th scope="col" class="num">Cost</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(slot, i) in slots"
            :key="i"
            :class="{ 'is-cost': slot.grid_charge }"
          >
            <td class="window">
              <span class="window__time">{{ slot.start }}–{{ slot.end }}</span>
            </td>
            <td>
              <span class="badge" :data-tone="behaviorTone(slot.behavior)">
                <span class="badge__dot" aria-hidden="true" />
                {{ behaviorLabel(slot.behavior) }}
              </span>
            </td>
            <td class="num">{{ formatPercent(slot.target_soc) }}</td>
            <td class="num">{{ formatPercent(slot.end_soc) }}</td>
            <td class="num" :class="{ 'num--accent': slot.grid_import_kwh > 0 }">
              {{ formatKwh(slot.grid_import_kwh) }}
            </td>
            <td class="num">
              <span :class="{ 'cost--charged': slot.cost > 0 }">{{ formatRand(slot.cost) }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.schedule {
  padding: 1.25rem 1.35rem 1.4rem;
  border-radius: 16px;
  background: var(--sa-surface, #161c24);
  border: 1px solid var(--sa-line, #273140);
}

.schedule__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.9rem;
}

.schedule__title {
  margin: 0;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
}

.schedule__hint {
  margin: 0;
  font-size: 0.78rem;
  color: var(--sa-text-dim, #9aa6b6);
}

.schedule__scroll {
  overflow-x: auto;
}

.schedule__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.4rem 1rem;
  color: var(--sa-text-dim, #6b7689);
  font-size: 0.86rem;
}

.schedule__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.88rem;
}

thead th {
  text-align: left;
  padding: 0.4rem 0.7rem 0.6rem;
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
  border-bottom: 1px solid var(--sa-line, #273140);
  white-space: nowrap;
}

tbody td {
  padding: 0.65rem 0.7rem;
  border-bottom: 1px solid var(--sa-line-soft, #1e2733);
  color: var(--sa-text, #eef2f7);
  white-space: nowrap;
}

tbody tr:last-child td {
  border-bottom: none;
}

tbody tr.is-cost {
  background: var(--sa-warn-soft, #2a23100f);
}

.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.num--accent {
  color: var(--sa-warn, #d8a83a);
}

.cost--charged {
  font-weight: 600;
  color: var(--sa-warn, #d8a83a);
}

.window__time {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 0.42rem;
  padding: 0.22rem 0.6rem 0.22rem 0.5rem;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 600;
  border: 1px solid transparent;
}

.badge__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}

.badge[data-tone='good'] {
  color: var(--sa-good, #34d399);
  background: var(--sa-good-soft, #34d39915);
  border-color: var(--sa-good-line, #34d39933);
}

.badge[data-tone='warn'] {
  color: var(--sa-warn, #d8a83a);
  background: var(--sa-warn-soft, #d8a83a18);
  border-color: var(--sa-warn-line, #d8a83a3a);
}

.badge[data-tone='neutral'] {
  color: var(--sa-text-dim, #9aa6b6);
  background: var(--sa-neutral-soft, #6b768915);
  border-color: var(--sa-line, #273140);
}
</style>
