<script setup lang="ts">
import { ref } from 'vue'
import { ApiError, getExplain } from '../api/client'
import type { ExplanationView } from '../api/types'

const props = defineProps<{ objective: number }>()

const loading = ref(false)
const result = ref<ExplanationView | null>(null)
const notReady = ref(false)
const errorMsg = ref('')

async function explain() {
  loading.value = true
  result.value = null
  notReady.value = false
  errorMsg.value = ''
  try {
    result.value = await getExplain(props.objective)
  } catch (e) {
    if (e instanceof ApiError && e.status === 503) {
      notReady.value = true
    } else {
      errorMsg.value =
        e instanceof Error ? e.message : 'Something went wrong fetching the explanation.'
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="explain" aria-label="Explain and suggest">
    <header class="explain__head">
      <div>
        <h3 class="explain__title">Explain &amp; suggest</h3>
        <p class="explain__sub">A plain-language read of the plan above.</p>
      </div>
      <button class="explain__btn" :disabled="loading" type="button" @click="explain">
        <span v-if="loading" class="explain__spinner" aria-hidden="true" />
        {{ loading ? 'Thinking…' : 'Explain my schedule' }}
      </button>
    </header>

    <!-- Not-ready (503) -->
    <p v-if="notReady" class="explain__state explain__state--wait" role="status">
      Live data isn't ready yet — give the system a moment to read your inverter, then try again.
    </p>

    <!-- Unexpected error -->
    <p v-else-if="errorMsg" class="explain__state explain__state--error" role="alert">
      {{ errorMsg }}
    </p>

    <!-- Result -->
    <template v-else-if="result">
      <!-- Provenance guard tripped: explanation withheld -->
      <div v-if="!result.guard_ok" class="explain__withheld" role="alert">
        <span class="explain__withheld-head">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M12 9v4M12 17h.01" stroke-linecap="round" />
            <path d="M10.3 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.7 3.86a2 2 0 0 0-3.4 0Z" stroke-linejoin="round" />
          </svg>
          Explanation withheld
        </span>
        <p class="explain__withheld-body">
          The generated text cited numbers we couldn't verify against the engine, so it was
          withheld to avoid showing you unverified figures.
        </p>
        <p
          v-if="result.unverified_numbers.length"
          class="explain__withheld-nums"
        >
          Unverified numbers:
          <code
            v-for="n in result.unverified_numbers"
            :key="n"
            class="explain__num"
            >{{ n }}</code
          >
        </p>
      </div>

      <!-- Not generated: informational note (AI off / rate-limited / unavailable) -->
      <div v-else-if="!result.generated" class="explain__note" role="status">
        <span class="explain__note-tag">Note</span>
        <p class="explain__note-body">{{ result.explanation }}</p>
      </div>

      <!-- Generated and verified -->
      <p v-else class="explain__body">{{ result.explanation }}</p>

      <p class="explain__disclaimer">{{ result.disclaimer }}</p>
    </template>

    <!-- Idle -->
    <p v-else class="explain__idle">
      No explanation yet. The schedule and recommendation are produced by the deterministic engine;
      this just narrates them.
    </p>
  </section>
</template>

<style scoped>
.explain {
  padding: 1.25rem 1.35rem 1.4rem;
  border-radius: 16px;
  background: var(--sa-surface, #161c24);
  border: 1px solid var(--sa-line, #273140);
}

.explain__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}

.explain__title {
  margin: 0;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
}

.explain__sub {
  margin: 0.2rem 0 0;
  font-size: 0.82rem;
  color: var(--sa-text-dim, #9aa6b6);
}

.explain__btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.55rem 1.05rem;
  border-radius: 10px;
  border: 1px solid var(--sa-accent-line, #3a6df0);
  background: var(--sa-accent, #2c5cf0);
  color: #fff;
  font-size: 0.88rem;
  font-weight: 600;
  cursor: pointer;
  transition:
    background 0.15s ease,
    transform 0.05s ease;
}

.explain__btn:hover:not(:disabled) {
  background: var(--sa-accent-hover, #3a6df0);
}

.explain__btn:active:not(:disabled) {
  transform: translateY(1px);
}

.explain__btn:disabled {
  opacity: 0.65;
  cursor: progress;
}

.explain__btn:focus-visible {
  outline: 2px solid var(--sa-focus, #7aa2ff);
  outline-offset: 2px;
}

.explain__spinner {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #fff;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.explain__body {
  margin: 0;
  font-size: 0.95rem;
  line-height: 1.6;
  color: var(--sa-text, #eef2f7);
  white-space: pre-line;
}

.explain__idle {
  margin: 0;
  font-size: 0.88rem;
  line-height: 1.55;
  color: var(--sa-text-dim, #9aa6b6);
}

.explain__state {
  margin: 0;
  padding: 0.85rem 1rem;
  border-radius: 12px;
  font-size: 0.9rem;
  line-height: 1.5;
}

.explain__state--wait {
  background: var(--sa-neutral-soft, #6b768914);
  border: 1px solid var(--sa-line, #273140);
  color: var(--sa-text-dim, #9aa6b6);
}

.explain__state--error {
  background: var(--sa-bad-soft, #ef6b6b15);
  border: 1px solid var(--sa-bad-line, #ef6b6b3a);
  color: var(--sa-bad, #ef6b6b);
}

.explain__withheld {
  padding: 0.95rem 1.1rem;
  border-radius: 12px;
  background: var(--sa-warn-soft, #d8a83a14);
  border: 1px solid var(--sa-warn-line, #d8a83a44);
}

.explain__withheld-head {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  font-weight: 700;
  font-size: 0.92rem;
  color: var(--sa-warn, #e0b54a);
}

.explain__withheld-body {
  margin: 0.5rem 0 0;
  font-size: 0.9rem;
  line-height: 1.55;
  color: var(--sa-text, #eef2f7);
}

.explain__withheld-nums {
  margin: 0.6rem 0 0;
  font-size: 0.84rem;
  color: var(--sa-text-dim, #9aa6b6);
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.explain__num {
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  padding: 0.12rem 0.4rem;
  border-radius: 6px;
  background: var(--sa-warn-soft, #d8a83a22);
  color: var(--sa-warn, #e0b54a);
  font-weight: 600;
}

.explain__note {
  display: flex;
  gap: 0.7rem;
  padding: 0.9rem 1.05rem;
  border-radius: 12px;
  background: var(--sa-neutral-soft, #6b768914);
  border: 1px solid var(--sa-line, #273140);
}

.explain__note-tag {
  flex-shrink: 0;
  align-self: flex-start;
  padding: 0.16rem 0.5rem;
  border-radius: 999px;
  background: var(--sa-muted, #6b7689);
  color: #0e131a;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.explain__note-body {
  margin: 0;
  font-size: 0.9rem;
  line-height: 1.55;
  color: var(--sa-text-dim, #c2ccda);
  white-space: pre-line;
}

.explain__disclaimer {
  margin: 1rem 0 0;
  padding-top: 0.85rem;
  border-top: 1px solid var(--sa-line, #273140);
  font-size: 0.78rem;
  color: var(--sa-text-dim, #9aa6b6);
}
</style>
