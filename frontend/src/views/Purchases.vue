<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { deletePurchase, getDashboard, getPurchases, updatePurchase } from '../api/client'
import type { PurchaseView } from '../api/types'
import PurchaseForm from '../components/PurchaseForm.vue'
import PurchaseTable from '../components/PurchaseTable.vue'
import PurchaseCharts from '../components/PurchaseCharts.vue'
import TariffBadge from '../components/TariffBadge.vue'

const purchases = ref<PurchaseView[]>([])
const rate = ref(0)
const source = ref('config')
const sourceDate = ref<string | null>(null)
const errorMsg = ref('')
const showForm = ref(false)

async function loadPurchases(): Promise<void> {
  try {
    purchases.value = (await getPurchases()).purchases
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : 'Could not load purchases.'
  }
}

async function loadTariff(): Promise<void> {
  try {
    const d = await getDashboard(0.5)
    rate.value = d.tariff_rate
    source.value = d.tariff_source
    sourceDate.value = d.tariff_source_date
  } catch {
    // Tariff badge is non-critical; the page still works without it.
  }
}

async function refresh(): Promise<void> {
  await Promise.all([loadPurchases(), loadTariff()])
}

async function onCreated(): Promise<void> {
  showForm.value = false
  await refresh()
}

async function onDelete(id: number): Promise<void> {
  try {
    await deletePurchase(id)
    await refresh()
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : 'Could not delete the purchase.'
  }
}

async function onUpdate(payload: {
  id: number
  body: { purchased_at: string; rand: number; units_kwh: number; note: string | null }
}): Promise<void> {
  try {
    await updatePurchase(payload.id, payload.body)
    await refresh()
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : 'Could not update the purchase.'
  }
}

onMounted(refresh)
</script>

<template>
  <div class="pv">
    <div class="pv__inner">
      <TariffBadge :rate="rate" :source="source" :source-date="sourceDate" />
      <p v-if="errorMsg" class="pv__error" role="alert">{{ errorMsg }}</p>
      <div class="pv__formbar">
        <button class="pv__toggle" data-test="toggle-form" @click="showForm = !showForm">
          {{ showForm ? '× Close' : '+ Log a purchase' }}
        </button>
      </div>
      <PurchaseForm v-if="showForm" @created="onCreated" />
      <PurchaseCharts :purchases="purchases" :current-rate="rate" />
      <PurchaseTable :purchases="purchases" @delete="onDelete" @update="onUpdate" />
    </div>
  </div>
</template>

<style scoped>
.pv {
  width: 100%;
  padding: clamp(1rem, 3vw, 2.4rem) clamp(1rem, 3vw, 2.4rem) 3rem;
}
.pv__inner {
  max-width: 1024px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 1.1rem;
}
.pv__formbar {
  display: flex;
}
.pv__toggle {
  padding: 0.5rem 0.9rem;
  border-radius: 10px;
  border: 1px solid var(--sa-accent, #5aa9ff);
  background: transparent;
  color: var(--sa-accent, #5aa9ff);
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
}
.pv__error {
  margin: 0;
  padding: 0.75rem 1rem;
  border-radius: 12px;
  background: var(--sa-surface, #161c24);
  border: 1px solid var(--sa-bad-line, #ef6b6b3a);
  color: var(--sa-bad, #ef6b6b);
  font-size: 0.88rem;
}
</style>
