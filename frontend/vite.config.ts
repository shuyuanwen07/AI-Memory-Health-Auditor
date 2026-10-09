import { defineConfig } from 'vite'; import react from '@vitejs/plugin-react';
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    watch: { usePolling: true, interval: 250 },
  },
  test: { environment: 'jsdom', globals: true, maxWorkers: 1, testTimeout: 60000, setupFiles: ['./src/testSetup.ts'] },
});
