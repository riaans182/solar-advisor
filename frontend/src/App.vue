<script setup lang="ts">
import { ref } from 'vue'
import Dashboard from './views/Dashboard.vue'
import Purchases from './views/Purchases.vue'

type Tab = 'dashboard' | 'purchases'
const tab = ref<Tab>('dashboard')
</script>

<template>
  <nav class="nav" aria-label="Primary">
    <button class="nav__tab" :data-active="tab === 'dashboard'" @click="tab = 'dashboard'">
      Dashboard
    </button>
    <button class="nav__tab" :data-active="tab === 'purchases'" @click="tab = 'purchases'">
      Purchases
    </button>
  </nav>
  <Dashboard v-if="tab === 'dashboard'" />
  <Purchases v-else />
</template>

<style scoped>
.nav {
  display: flex;
  gap: 0.4rem;
  padding: 0.8rem clamp(1rem, 3vw, 2.4rem) 0;
  max-width: 1280px;
  margin: 0 auto;
}
.nav__tab {
  padding: 0.5rem 1rem;
  border-radius: 10px 10px 0 0;
  border: 1px solid transparent;
  background: transparent;
  color: var(--sa-text-dim, #9aa6b6);
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
}
.nav__tab[data-active='true'] {
  color: var(--sa-text, #eef2f7);
  background: var(--sa-surface, #161c24);
  border-color: var(--sa-line, #273140);
  border-bottom-color: transparent;
}
</style>
