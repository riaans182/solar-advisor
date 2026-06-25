<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ApiError, getDashboard, getHistory } from '../api/client'
import type { DashboardView, HistoryPoint } from '../api/types'
import DisclaimerBanner from '../components/DisclaimerBanner.vue'
import LiveTiles from '../components/LiveTiles.vue'
import ObjectiveSlider from '../components/ObjectiveSlider.vue'
import RecommendationPanel from '../components/RecommendationPanel.vue'
import ScheduleTable from '../components/ScheduleTable.vue'
import ExplainPanel from '../components/ExplainPanel.vue'
import TrendChart from '../components/TrendChart.vue'
import TariffBadge from '../components/TariffBadge.vue'

const POLL_MS = 10_000
const DEBOUNCE_MS = 300
const HISTORY_HOURS = 24

// The objective the user steers with the slider; the parent owns it so a change
// can debounce-then-refetch ("re-run the engine") while the components stay
// purely presentational.
const objective = ref(0.5)

const dashboard = ref<DashboardView | null>(null)
const history = ref<HistoryPoint[]>([])

const loading = ref(true) // true until the first dashboard response lands
const notReady = ref(false) // 503: live state not ready yet
const errorMsg = ref('')

let pollTimer: ReturnType<typeof setInterval> | undefined
let debounceTimer: ReturnType<typeof setTimeout> | undefined

// Monotonic token guarding against out-of-order dashboard responses: the poll
// and the slider re-fetch race, so a stale response (old objective) could
// resolve after a newer one and overwrite the rendered plan. Only the latest
// in-flight request is allowed to assign state.
let dashboardSeq = 0

async function fetchDashboard(): Promise<void> {
  const seq = ++dashboardSeq
  try {
    const view = await getDashboard(objective.value)
    if (seq !== dashboardSeq) return
    dashboard.value = view
    notReady.value = false
    errorMsg.value = ''
  } catch (e) {
    if (seq !== dashboardSeq) return
    if (e instanceof ApiError && e.status === 503) {
      // Live state not ready: keep any prior data, surface the waiting state.
      if (!dashboard.value) notReady.value = true
    } else {
      errorMsg.value = e instanceof Error ? e.message : 'Failed to reach the advisor service.'
    }
  } finally {
    if (seq === dashboardSeq) loading.value = false
  }
}

async function fetchHistory(): Promise<void> {
  try {
    const view = await getHistory(HISTORY_HOURS)
    history.value = view.points
  } catch {
    // History is non-critical; leave the last good series in place.
  }
}

function refreshAll(): void {
  void fetchDashboard()
  void fetchHistory()
}

// Slider change re-runs the engine: debounce so dragging doesn't spam the API.
watch(objective, () => {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    void fetchDashboard()
  }, DEBOUNCE_MS)
})

onMounted(() => {
  refreshAll()
  pollTimer = setInterval(refreshAll, POLL_MS)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (debounceTimer) clearTimeout(debounceTimer)
})
</script>

<template>
  <div class="dash">
    <div class="dash__inner">
      <header class="dash__masthead">
        <div class="dash__brand">
          <span class="dash__mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8">
              <circle cx="12" cy="12" r="4.2" />
              <path
                d="M12 2v2.4M12 19.6V22M4.2 4.2l1.7 1.7M18.1 18.1l1.7 1.7M2 12h2.4M19.6 12H22M4.2 19.8l1.7-1.7M18.1 5.9l1.7-1.7"
                stroke-linecap="round"
              />
            </svg>
          </span>
          <div class="dash__brand-text">
            <h1 class="dash__title">Solar Advisor</h1>
            <p class="dash__tagline">Deterministic engine · read-only · advisory</p>
          </div>
        </div>
        <span class="dash__live" :data-on="!loading && !notReady">
          <span class="dash__live-dot" aria-hidden="true" />
          {{ loading ? 'Connecting' : notReady ? 'Waiting' : 'Live' }}
        </span>
      </header>

      <!-- Disclaimer is always visible once we have a payload; before that, a
           static fallback keeps the read-only promise on screen at all times. -->
      <DisclaimerBanner
        :text="
          dashboard?.disclaimer ??
          'Advisory only. This dashboard is strictly read-only against your inverter.'
        "
      />

      <!-- First-load / not-ready state -->
      <div
        v-if="!dashboard"
        class="dash__wait"
        :data-error="!!errorMsg"
        role="status"
        aria-live="polite"
      >
        <span v-if="!errorMsg" class="dash__wait-spinner" aria-hidden="true" />
        <p class="dash__wait-title">
          {{ errorMsg ? 'Cannot reach the advisor' : 'Waiting for live data…' }}
        </p>
        <p class="dash__wait-body">
          {{
            errorMsg
              ? errorMsg
              : 'Reading the latest telemetry from your inverter. This panel fills in as soon as a live snapshot arrives.'
          }}
        </p>
      </div>

      <!-- Loaded dashboard -->
      <template v-else>
        <LiveTiles :dashboard="dashboard" />

        <div class="dash__columns">
          <div class="dash__col dash__col--main">
            <RecommendationPanel :recommendation="dashboard.recommendation" />
            <ScheduleTable :slots="dashboard.slots" />
            <ExplainPanel :objective="objective" />
          </div>

          <aside class="dash__col dash__col--side">
            <TariffBadge
              :rate="dashboard.tariff_rate"
              :source="dashboard.tariff_source"
              :source-date="dashboard.tariff_source_date"
            />
            <ObjectiveSlider v-model="objective" />

            <section class="dash__history" aria-label="Recent history">
              <h2 class="dash__history-title">Last 24 hours</h2>
              <div class="dash__charts">
                <TrendChart
                  :points="history"
                  metric="battery_soc"
                  label="Battery SOC"
                  unit="%"
                />
                <TrendChart :points="history" metric="pv_power" label="Solar" unit="W" />
                <TrendChart :points="history" metric="grid_power" label="Grid" unit="W" />
                <TrendChart :points="history" metric="load_power" label="Load" unit="W" />
              </div>
            </section>
          </aside>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.dash {
  width: 100%;
  padding: clamp(1rem, 3vw, 2.4rem) clamp(1rem, 3vw, 2.4rem) 3rem;
}

.dash__inner {
  max-width: 1280px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 1.1rem;
}

/* Masthead */
.dash__masthead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 0.2rem;
}

.dash__brand {
  display: flex;
  align-items: center;
  gap: 0.85rem;
}

.dash__mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 13px;
  color: var(--sa-solar, #f5b942);
  background: var(--sa-solar-soft, #f5b94215);
  border: 1px solid var(--sa-warn-line, #d8a83a44);
  box-shadow: 0 0 26px -10px var(--sa-solar, #f5b942);
}

.dash__title {
  margin: 0;
  font-size: clamp(1.3rem, 3vw, 1.65rem);
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--sa-text, #eef2f7);
}

.dash__tagline {
  margin: 0.1rem 0 0;
  font-size: 0.78rem;
  letter-spacing: 0.02em;
  color: var(--sa-text-dim, #9aa6b6);
}

.dash__live {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0.85rem;
  border-radius: 999px;
  font-size: 0.76rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
  background: var(--sa-surface, #161c24);
  border: 1px solid var(--sa-line, #273140);
}

.dash__live[data-on='true'] {
  color: var(--sa-good, #34d399);
  border-color: var(--sa-good-line, #34d39933);
}

.dash__live-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--sa-muted, #6b7689);
}

.dash__live[data-on='true'] .dash__live-dot {
  background: var(--sa-good, #34d399);
  box-shadow: 0 0 0 0 var(--sa-good, #34d399);
  animation: pulse 2.2s ease-out infinite;
}

@keyframes pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(52, 211, 153, 0.5);
  }
  70% {
    box-shadow: 0 0 0 7px rgba(52, 211, 153, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(52, 211, 153, 0);
  }
}

/* Waiting / error state */
.dash__wait {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.55rem;
  padding: 3.2rem 1.5rem;
  text-align: center;
  border-radius: 18px;
  background: var(--sa-surface, #161c24);
  border: 1px solid var(--sa-line, #273140);
}

.dash__wait[data-error='true'] {
  border-color: var(--sa-bad-line, #ef6b6b3a);
}

.dash__wait-spinner {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  border: 3px solid var(--sa-line, #273140);
  border-top-color: var(--sa-solar, #f5b942);
  animation: spin 0.9s linear infinite;
  margin-bottom: 0.3rem;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.dash__wait-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--sa-text, #eef2f7);
}

.dash__wait[data-error='true'] .dash__wait-title {
  color: var(--sa-bad, #ef6b6b);
}

.dash__wait-body {
  margin: 0;
  max-width: 42ch;
  font-size: 0.9rem;
  line-height: 1.55;
  color: var(--sa-text-dim, #9aa6b6);
}

/* Two-column composition: plan on the left, controls + trends on the right */
.dash__columns {
  display: grid;
  grid-template-columns: minmax(0, 1.65fr) minmax(0, 1fr);
  gap: 1.1rem;
  align-items: start;
}

.dash__col {
  display: flex;
  flex-direction: column;
  gap: 1.1rem;
  min-width: 0;
}

.dash__col--side {
  position: sticky;
  top: 1rem;
}

/* History */
.dash__history {
  padding: 1.25rem 1.35rem 1.4rem;
  border-radius: 16px;
  background: var(--sa-surface, #161c24);
  border: 1px solid var(--sa-line, #273140);
}

.dash__history-title {
  margin: 0 0 0.9rem;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
}

.dash__charts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 0.85rem;
}

@media (max-width: 900px) {
  .dash__columns {
    grid-template-columns: 1fr;
  }
  .dash__col--side {
    position: static;
  }
}
</style>
