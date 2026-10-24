import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-query'],
          charts: ['recharts'],
        },
      },
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_BACKEND_URL || 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path, // Keep /api prefix as backend expects /api/v1/...
        // Dev only: if the backend has API_KEY set, export the same API_KEY
        // before `npm run dev`; the key is added by the proxy, never bundled.
        headers: process.env.API_KEY ? { 'X-API-Key': process.env.API_KEY } : {},
      },
    },
  },
})
