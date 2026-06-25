<script setup lang="ts">
import { ref } from 'vue'
import type { PurchaseView } from '../api/types'
import { formatDate, formatRand, formatRatePerKwh, formatUnits } from '../lib/format'

defineProps<{ purchases: PurchaseView[] }>()
const emit = defineEmits<{ delete: [id: number] }>()

const confirmingId = ref<number | null>(null)

function arm(id: number): void {
  confirmingId.value = id
}
function cancel(): void {
  confirmingId.value = null
}
function confirm(id: number): void {
  emit('delete', id)
  confirmingId.value = null
}
</script>

<template>
  <section class="pt" aria-label="Logged purchases">
    <h2 class="pt__title">Purchases</h2>
    <p v-if="!purchases.length" class="pt__empty">No purchases logged yet.</p>
    <table v-else class="pt__table">
      <thead>
        <tr>
          <th>Date</th>
          <th>Paid</th>
          <th>Units</th>
          <th>Rate</th>
          <th>Note</th>
          <th aria-label="actions" />
        </tr>
      </thead>
      <tbody>
        <tr v-for="p in purchases" :key="p.id">
          <td>{{ formatDate(p.purchased_at) }}</td>
          <td class="pt__num">{{ formatRand(p.rand) }}</td>
          <td class="pt__num">{{ formatUnits(p.units_kwh) }}</td>
          <td class="pt__num pt__rate">{{ formatRatePerKwh(p.effective_rate) }}</td>
          <td class="pt__note">{{ p.note ?? '' }}</td>
          <td class="pt__actions">
            <template v-if="confirmingId === p.id">
              <button
                class="pt__btn pt__btn--danger"
                :data-test="`confirm-${p.id}`"
                @click="confirm(p.id)"
              >
                Confirm
              </button>
              <button class="pt__btn" @click="cancel">Cancel</button>
            </template>
            <button v-else class="pt__btn" :data-test="`del-${p.id}`" @click="arm(p.id)">
              Delete
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.pt {
  padding: 1.25rem 1.35rem 1.4rem;
  border-radius: 16px;
  background: var(--sa-surface, #161c24);
  border: 1px solid var(--sa-line, #273140);
}
.pt__title {
  margin: 0 0 0.9rem;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
}
.pt__empty {
  margin: 0;
  color: var(--sa-text-dim, #6b7689);
  font-size: 0.9rem;
}
.pt__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}
.pt__table th {
  text-align: left;
  padding: 0.4rem 0.6rem;
  font-size: 0.7rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
  border-bottom: 1px solid var(--sa-line, #273140);
}
.pt__table td {
  padding: 0.55rem 0.6rem;
  border-bottom: 1px solid var(--sa-line, #1f2733);
  color: var(--sa-text, #eef2f7);
}
.pt__num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.pt__rate {
  color: var(--sa-solar, #f5b942);
  font-weight: 600;
}
.pt__note {
  color: var(--sa-text-dim, #9aa6b6);
}
.pt__actions {
  text-align: right;
  white-space: nowrap;
}
.pt__btn {
  padding: 0.3rem 0.6rem;
  margin-left: 0.3rem;
  border-radius: 8px;
  border: 1px solid var(--sa-line, #273140);
  background: transparent;
  color: var(--sa-text-dim, #9aa6b6);
  font-size: 0.8rem;
  cursor: pointer;
}
.pt__btn--danger {
  border-color: var(--sa-bad-line, #ef6b6b3a);
  color: var(--sa-bad, #ef6b6b);
}
</style>
