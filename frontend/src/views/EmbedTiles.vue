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

/* Flow the tiles: as many across as fit, wrapping to more rows when the host
   frame is narrow. One clean row of six when there's room; 3×2 / 2×3 etc. when
   not — so the strip drops beside other cards without squashing. */
.embed :deep(.tiles) {
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
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
</style>
