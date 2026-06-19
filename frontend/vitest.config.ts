/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

/**
 * Vitest configuration for the DnD LLM Game frontend.
 *
 * Kept as a separate file from `vite.config.ts` so the production build
 * config stays untouched — vitest reads this file in preference to
 * vite.config.ts when both are present. The React plugin is re-declared here
 * because vitest does not merge the two configs.
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    css: false,
    clearMocks: true,
  },
})
