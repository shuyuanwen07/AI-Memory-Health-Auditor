import { defineConfig } from 'vitest/config'; import react from '@vitejs/plugin-react';
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    proxy: {
      '^/api/v1(?:/|$)': {
        target: process.env.AUDITOR_PROXY_TARGET || 'http://127.0.0.1:8000',
        // Keep browser Origin, session cookies and CSRF headers intact.
        changeOrigin: false,
      },
    },
    watch: { usePolling: true, interval: 250 },
  },
  test: { environment: 'jsdom', globals: true, maxWorkers: 1, testTimeout: 60000, setupFiles: ['./src/testSetup.ts'] },
});
