import { defineConfig } from 'vitest/config'

export default defineConfig({
  esbuild: { jsx: 'automatic' },
  test: { environment: 'jsdom', setupFiles: ['./src/test/setupVitest.ts'] },
})
