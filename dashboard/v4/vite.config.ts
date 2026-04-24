import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Proxies /api/* to the existing v3 Python backend on :8790
// so v4 can consume the same FastAPI-style endpoints without CORS glue.
// Start the backend with:  python dashboard/v3/serve.py
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8790',
        changeOrigin: true,
      },
    },
  },
});
