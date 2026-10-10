import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In dev, the browser talks only to Vite; /api is proxied to the FastAPI backend.
// That keeps the refresh cookie same-origin. BACKEND_URL is set by docker-compose.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': { target: process.env.BACKEND_URL ?? 'http://localhost:8000', changeOrigin: false },
    },
  },
})
