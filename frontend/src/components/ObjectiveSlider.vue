<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ modelValue: number }>()
defineEmits<{ 'update:modelValue': [value: number] }>()

const pct = computed(() => Math.round(props.modelValue * 100))
</script>

<template>
  <section class="slider" aria-label="Cost versus backup objective">
    <div class="slider__head">
      <h3 class="slider__title">Strategy</h3>
      <span class="slider__readout">
        <span class="slider__readout-num">{{ pct }}%</span> toward backup
      </span>
    </div>

    <input
      class="slider__input"
      type="range"
      min="0"
      max="1"
      step="0.05"
      :value="modelValue"
      :style="{ '--fill': pct + '%' }"
      aria-label="Cheapest bill to most backup"
      :aria-valuetext="`${pct} percent toward backup`"
      @input="
        $emit('update:modelValue', Number(($event.target as HTMLInputElement).value))
      "
    />

    <div class="slider__ends">
      <span class="slider__end">
        <strong>Cheapest bill</strong>
        <em>minimise cost</em>
      </span>
      <span class="slider__end slider__end--right">
        <strong>Most backup</strong>
        <em>maximise resilience</em>
      </span>
    </div>
  </section>
</template>

<style scoped>
.slider {
  padding: 1.25rem 1.35rem 1.4rem;
  border-radius: 16px;
  background: var(--sa-surface, #161c24);
  border: 1px solid var(--sa-line, #273140);
}

.slider__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}

.slider__title {
  margin: 0;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--sa-text-dim, #9aa6b6);
}

.slider__readout {
  font-size: 0.9rem;
  color: var(--sa-text-dim, #9aa6b6);
}

.slider__readout-num {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--sa-text, #eef2f7);
}

.slider__input {
  --fill: 50%;
  width: 100%;
  height: 8px;
  margin: 0;
  appearance: none;
  -webkit-appearance: none;
  border-radius: 999px;
  background: linear-gradient(
    to right,
    var(--sa-good, #34d399) 0%,
    var(--sa-solar, #f5b942) var(--fill),
    var(--sa-track, #0e131a) var(--fill)
  );
  cursor: pointer;
}

.slider__input:focus-visible {
  outline: 2px solid var(--sa-focus, #7aa2ff);
  outline-offset: 4px;
}

.slider__input::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--sa-text, #eef2f7);
  border: 3px solid var(--sa-surface, #161c24);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.5);
  cursor: pointer;
}

.slider__input::-moz-range-thumb {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--sa-text, #eef2f7);
  border: 3px solid var(--sa-surface, #161c24);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.5);
  cursor: pointer;
}

.slider__ends {
  display: flex;
  justify-content: space-between;
  margin-top: 0.8rem;
  gap: 1rem;
}

.slider__end {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.slider__end--right {
  text-align: right;
}

.slider__end strong {
  font-size: 0.84rem;
  color: var(--sa-text, #eef2f7);
}

.slider__end em {
  font-style: normal;
  font-size: 0.74rem;
  color: var(--sa-text-dim, #9aa6b6);
}
</style>
