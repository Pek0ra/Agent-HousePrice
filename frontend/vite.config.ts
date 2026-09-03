import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
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
