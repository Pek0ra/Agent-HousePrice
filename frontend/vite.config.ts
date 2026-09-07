import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: { environment: 'jsdom', setupFiles: './src/test/setup.ts', css: true },
  server: {
    port: 5173,
    proxy: {
      '/api/agent': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/agent/, '/api/v1'),
      },
      '/api/java': {
        target: 'http://localhost:9900',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/java/, '/api'),
      },
    },
  },
})
