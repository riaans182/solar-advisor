<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { getDashboard } from '../api/client'
import type { DashboardView } from '../api/types'
import LiveTiles from '../components/LiveTiles.vue'

// A chrome-free build of just the live tiles, meant to be embedded (e.g. in a
// Home Assistant dashboard) via /?embed=tiles. It polls the same /api/dashboard
// endpoint as the main view but renders nothing else, on a transparent page.
const POLL_MS = 10_000
const OBJECTIVE = 0.5 // fixed; the strip has no slider

const dashboard = ref<DashboardView | null>(null)
let pollTimer: ReturnType<typeof setInterval> | undefined

async function refresh(): Promise<void> {
  try {
    dashboard.value = await getDashboard(OBJECTIVE)
  } catch {
    // Keep the last good readings on the strip; a transient failure shouldn't blank it.
  }
}

onMounted(() => {
  void refresh()
  pollTimer = setInterval(() => void refresh(), POLL_MS)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div class="embed">
    <LiveTiles v-if="dashboard" :dashboard="dashboard" />
    <p v-else class="embed__wait">Waiting for live data…</p>
  </div>
</template>

<style scoped>
.embed {
  padding: 8px;
}

/* Force a single full-width row of tiles so the strip reads as one clean band,
   regardless of how wide the host frame is. */
.embed :deep(.tiles) {
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 0.6rem;
}

/* Compact the tiles a touch for a slim band. */
.embed :deep(.tile) {
  padding: 0.7rem 0.8rem 0.8rem;
}
.embed :deep(.tile__value) {
  font-size: clamp(1.2rem, 2.4vw, 1.6rem);
}
.embed :deep(.tile__bar) {
  margin-top: 0.45rem;
}

.embed__wait {
  margin: 0;
  padding: 1.4rem;
  text-align: center;
  color: var(--sa-text-dim, #9aa6b6);
  font-size: 0.9rem;
}

/* A narrow host (portrait) wraps the band into two rows rather than squashing. */
@media (max-width: 760px) {
  .embed :deep(.tiles) {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
