<script setup lang="ts">
defineProps<{ text: string }>()
</script>

<template>
  <div class="disclaimer" role="note" aria-label="Advisory notice">
    <span class="disclaimer__badge" aria-hidden="true">
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M12 9v4M12 17h.01" stroke-linecap="round" />
        <path d="M10.3 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.7 3.86a2 2 0 0 0-3.4 0Z" stroke-linejoin="round" />
      </svg>
      Read-only
    </span>
    <p class="disclaimer__text">{{ text }}</p>
  </div>
</template>

<style scoped>
.disclaimer {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  padding: 0.7rem 1.1rem;
  border-radius: 12px;
  background: var(--sa-warn-soft, #2a2310);
  border: 1px solid var(--sa-warn-line, #5a4a16);
  color: var(--sa-warn-text, #f5d98a);
  font-size: 0.9rem;
  line-height: 1.4;
}

.disclaimer__badge {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  flex-shrink: 0;
  padding: 0.28rem 0.6rem;
  border-radius: 999px;
  background: var(--sa-warn, #d8a83a);
  color: #1a1505;
  font-weight: 700;
  font-size: 0.72rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.disclaimer__text {
  margin: 0;
  font-weight: 500;
}
</style>
