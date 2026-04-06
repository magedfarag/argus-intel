import { defineConfig } from 'vitest/config'
import { loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load all env vars (not just VITE_-prefixed) so we can inject API_KEY into
  // the dev proxy — keeps the key out of the browser bundle entirely.
  const env = loadEnv(mode, process.cwd(), '')
  const apiKey = env.API_KEY ?? ''
  // Explicit type annotation avoids the `{ Authorization?: undefined }` union
  // that breaks Vite's ProxyOptions header signature.
  const proxyHeaders: Record<string, string> = apiKey ? { Authorization: `Bearer ${apiKey}` } : {}

  return {
    plugins: [react()],
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test-setup.ts'],
      include: ['src/**/*.{test,spec}.{ts,tsx}'],
      exclude: ['e2e/**', 'node_modules/**'],
    },
    server: {
      port: 5173,
      proxy: {
        '/api': { target: 'http://localhost:8000', changeOrigin: true, headers: proxyHeaders },
        '/healthz': { target: 'http://localhost:8000', changeOrigin: true },
        '/readyz': { target: 'http://localhost:8000', changeOrigin: true },
      },
    },
  }
})
