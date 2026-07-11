import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        // Backend API origin. Default :8001 (the app server); :8000 is reserved
        // for a local vLLM endpoint. Override with API_URL=http://localhost:<port>.
        target: process.env.API_URL || 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
})
