<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { deletePurchase, getDashboard, getPurchases } from '../api/client'
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

async function onDelete(id: number): Promise<void> {
  try {
    await deletePurchase(id)
    await refresh()
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : 'Could not delete the purchase.'
  }
}

onMounted(refresh)
</script>

<template>
  <div class="pv">
    <div class="pv__inner">
      <TariffBadge :rate="rate" :source="source" :source-date="sourceDate" />
      <p v-if="errorMsg" class="pv__error" role="alert">{{ errorMsg }}</p>
      <PurchaseForm @created="refresh" />
      <PurchaseCharts :purchases="purchases" :current-rate="rate" />
      <PurchaseTable :purchases="purchases" @delete="onDelete" />
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
