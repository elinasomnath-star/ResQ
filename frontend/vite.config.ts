import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '127.0.0.1',
    proxy: {
      '/auth': 'http://127.0.0.1:8000',
      '/events': 'http://127.0.0.1:8000',
      '/zones': 'http://127.0.0.1:8000',
      '/simulate': 'http://127.0.0.1:8000',
      '/closures': 'http://127.0.0.1:8000',
      '/facilities': 'http://127.0.0.1:8000',
      '/scenarios': 'http://127.0.0.1:8000',
      '/sweep': 'http://127.0.0.1:8000',
      '/stock': 'http://127.0.0.1:8000',
      '/admin': 'http://127.0.0.1:8000',
      '/allocation': 'http://127.0.0.1:8000',
      '/routes': 'http://127.0.0.1:8000',
      '/escalations': 'http://127.0.0.1:8000',
      '/data/gauge-readings': 'http://127.0.0.1:8000',
    },
  },
})
