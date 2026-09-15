import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Dev server proxies /api to the FastAPI backend so the frontend can call
// relative /api/... URLs with zero CORS configuration needed on either side.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: `https://drishti-backend.onrender.com:${process.env.BACKEND_PORT || 8000}`,
        changeOrigin: true,
      },
    },
  },
})
