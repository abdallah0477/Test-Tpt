import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// /api is proxied to the backend. In docker compose BACKEND_URL=http://backend:8000.
const backend = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': { target: backend, changeOrigin: true } },
  },
})
