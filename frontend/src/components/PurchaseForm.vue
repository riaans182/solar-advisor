<script setup lang="ts">
import { computed, ref } from 'vue'
import { createPurchase } from '../api/client'
import { formatRatePerKwh } from '../lib/format'

const emit = defineEmits<{ created: [] }>()

const purchasedAt = ref('')
const randStr = ref('')
const unitsStr = ref('')
const note = ref('')
const submitting = ref(false)
const errorMsg = ref('')

const rand = computed(() => Number(randStr.value))
const units = computed(() => Number(unitsStr.value))

const preview = computed(() =>
  randStr.value !== '' && unitsStr.value !== '' && rand.value > 0 && units.value > 0
    ? rand.value / units.value
    : null,
)

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

const validationError = computed<string | null>(() => {
  if (!purchasedAt.value) return 'Pick the purchase date.'
  if (purchasedAt.value > todayIso()) return 'Date cannot be in the future.'
  if (!(rand.value > 0)) return 'Rand amount must be greater than 0.'
  if (!(units.value > 0)) return 'Units must be greater than 0.'
  return null
})

async function onSubmit(): Promise<void> {
  if (validationError.value) {
    errorMsg.value = validationError.value
    return
  }
  submitting.value = true
  errorMsg.value = ''
  try {
    await createPurchase({
      purchased_at: purchasedAt.value,
      rand: rand.value,
      units_kwh: units.value,
      note: note.value.trim() || null,
    })
    emit('created')
    randStr.value = ''
    unitsStr.value = ''
    note.value = ''
    // Keep the date for quick consecutive entries.
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : 'Could not save the purchase.'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <form class="pf" @submit.prevent="onSubmit">
    <h2 class="pf__title">Log a purchase</h2>
    <div class="pf__grid">
      <label class="pf__field">
        <span class="pf__label">Date</span>
        <input name="purchased_at" type="date" v-model="purchasedAt" :max="todayIso()" />
      </label>
      <label class="pf__field">
        <span class="pf__label">Rand paid</span>
        <input
          name="rand"
          type="number"
          min="0"
          step="0.01"
          inputmode="decimal"
          v-model="randStr"
          placeholder="1000"
        />
      </label>
      <label class="pf__field">
        <span class="pf__label">Units received</span>
        <input
          name="units_kwh"
          type="number"
          min="0"
          step="0.01"
          inputmode="decimal"
          v-model="unitsStr"
          placeholder="280.9"
        />
      </label>
      <label class="pf__field pf__field--wide">
        <span class="pf__label">Note (optional)</span>
        <input name="note" type="text" v-model="note" placeholder="e.g. City of Cape Town" />
      </label>
    </div>

    <div class="pf__foot">
      <p class="pf__preview" :data-active="preview !== null">
        <span class="pf__preview-label">Effective rate</span>
        <span class="pf__preview-value">{{
          preview !== null ? formatRatePerKwh(preview) : '—'
        }}</span>
      </p>
      <button class="pf__submit" type="submit" :disabled="submitting">
        {{ submitting ? 'Saving…' : 'Save purchase' }}
      </button>
    </div>

    <p v-if="errorMsg" class="pf__error" role="alert">{{ errorMsg }}</p>
  </form>
</template>

<style scoped>
.pf {
  padding: 1.25rem 1.35rem 1.4rem;
  border-radius: 16px;
  background: var(--sa-surface, #161c24);
  border: 1px solid var(--sa-line, #273140);
}
.pf__title {
  margin: 0 0 0.9rem;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
}
.pf__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 0.85rem;
}
.pf__field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  min-width: 0;
}
.pf__field--wide {
  grid-column: 1 / -1;
}
.pf__label {
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
}
.pf__field input {
  padding: 0.55rem 0.65rem;
  border-radius: 10px;
  border: 1px solid var(--sa-line, #273140);
  background: var(--sa-bg, #0f141b);
  color: var(--sa-text, #eef2f7);
  font-size: 0.95rem;
  font-variant-numeric: tabular-nums;
}
.pf__field input:focus {
  outline: none;
  border-color: var(--sa-accent, #5aa9ff);
}
.pf__foot {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
  margin-top: 1.05rem;
  flex-wrap: wrap;
}
.pf__preview {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.pf__preview-label {
  font-size: 0.72rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
}
.pf__preview-value {
  font-size: 1.25rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--sa-text-dim, #6b7689);
}
.pf__preview[data-active='true'] .pf__preview-value {
  color: var(--sa-solar, #f5b942);
}
.pf__submit {
  padding: 0.6rem 1.1rem;
  border-radius: 10px;
  border: 1px solid var(--sa-accent, #5aa9ff);
  background: var(--sa-accent, #5aa9ff);
  color: #06101c;
  font-size: 0.92rem;
  font-weight: 700;
  cursor: pointer;
}
.pf__submit:disabled {
  opacity: 0.6;
  cursor: progress;
}
.pf__error {
  margin: 0.85rem 0 0;
  font-size: 0.86rem;
  color: var(--sa-bad, #ef6b6b);
}
</style>
