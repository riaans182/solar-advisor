import pluginVue from 'eslint-plugin-vue'
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'

// Flat config (ESLint 10). Mirrors the plan's intent: vue3-recommended +
// TypeScript + Prettier-compat (formatting is handled by `npm run format`).
export default defineConfigWithVueTs(
  {
    name: 'app/files-to-lint',
    files: ['**/*.{ts,mts,tsx,vue}'],
  },
  {
    name: 'app/files-to-ignore',
    ignores: ['dist/**', 'coverage/**'],
  },
  pluginVue.configs['flat/recommended'],
  vueTsConfigs.recommended,
  skipFormatting,
  {
    name: 'app/single-word-views',
    // App.vue and the top-level Dashboard route view are intentionally
    // single-word, matching the plan's file names.
    rules: {
      'vue/multi-word-component-names': ['error', { ignores: ['App', 'Dashboard'] }],
    },
  },
)
