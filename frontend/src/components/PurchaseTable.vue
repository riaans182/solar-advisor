<script setup lang="ts">
import { ref } from 'vue'
import type { PurchaseView } from '../api/types'
import { formatDate, formatRand, formatRatePerKwh, formatUnits } from '../lib/format'

defineProps<{ purchases: PurchaseView[] }>()
const emit = defineEmits<{
  delete: [id: number]
  update: [
    payload: {
      id: number
      body: { purchased_at: string; rand: number; units_kwh: number; note: string | null }
    },
  ]
}>()

const confirmingId = ref<number | null>(null)
const editingId = ref<number | null>(null)
const editDate = ref('')
const editRand = ref('')
const editUnits = ref('')
const editNote = ref('')
const editError = ref('')

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

function startEdit(p: PurchaseView): void {
  editingId.value = p.id
  editDate.value = p.purchased_at
  editRand.value = String(p.rand)
  editUnits.value = String(p.units_kwh)
  editNote.value = p.note ?? ''
  editError.value = ''
}
function cancelEdit(): void {
  editingId.value = null
  editError.value = ''
}
function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}
function saveEdit(id: number): void {
  const rand = Number(editRand.value)
  const units = Number(editUnits.value)
  if (!editDate.value || editDate.value > todayIso()) {
    editError.value = 'Date cannot be in the future.'
    return
  }
  if (!(rand > 0) || !(units > 0)) {
    editError.value = 'Rand and units must be greater than 0.'
    return
  }
  emit('update', {
    id,
    body: { purchased_at: editDate.value, rand, units_kwh: units, note: editNote.value.trim() || null },
  })
  editingId.value = null
  editError.value = ''
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
          <th class="pt__th-num">Paid</th>
          <th class="pt__th-num">Units</th>
          <th class="pt__th-num">Rate</th>
          <th>Note</th>
          <th aria-label="actions" />
        </tr>
      </thead>
      <tbody>
        <tr v-for="p in purchases" :key="p.id">
          <template v-if="editingId === p.id">
            <td><input v-model="editDate" type="date" :max="todayIso()" :data-test="`edit-date-${p.id}`" /></td>
            <td><input v-model="editRand" type="number" min="0" step="0.01" :data-test="`edit-rand-${p.id}`" /></td>
            <td><input v-model="editUnits" type="number" min="0" step="0.01" :data-test="`edit-units-${p.id}`" /></td>
            <td class="pt__num pt__rate">—</td>
            <td><input v-model="editNote" type="text" :data-test="`edit-note-${p.id}`" /></td>
            <td class="pt__actions">
              <button class="pt__btn" :data-test="`save-${p.id}`" @click="saveEdit(p.id)">Save</button>
              <button class="pt__btn" :data-test="`cancel-edit-${p.id}`" @click="cancelEdit">Cancel</button>
            </td>
          </template>
          <template v-else>
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
              <template v-else>
                <button class="pt__btn" :data-test="`edit-${p.id}`" @click="startEdit(p)">Edit</button>
                <button class="pt__btn" :data-test="`del-${p.id}`" @click="arm(p.id)">Delete</button>
              </template>
            </td>
          </template>
        </tr>
      </tbody>
    </table>
    <p v-if="editError" class="pt__error" role="alert">{{ editError }}</p>
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
.pt__th-num {
  text-align: right;
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
.pt__table input {
  width: 100%;
  min-width: 0;
  padding: 0.3rem 0.4rem;
  border-radius: 6px;
  border: 1px solid var(--sa-line, #273140);
  background: var(--sa-bg, #0f141b);
  color: var(--sa-text, #eef2f7);
  font-size: 0.85rem;
}
.pt__error {
  margin: 0.6rem 0 0;
  font-size: 0.84rem;
  color: var(--sa-bad, #ef6b6b);
}
</style>
