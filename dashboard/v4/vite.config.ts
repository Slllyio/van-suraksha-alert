import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Proxies /api/* to the existing v3 Python backend on :8790
// so v4 can consume the same FastAPI-style endpoints without CORS glue.
// Start the backend with:  python dashboard/v3/serve.py
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [
      // react-plotly.js imports `plotly.js/dist/plotly`. We installed the
      // pre-bundled dist-min package instead, whose entry is
      // `plotly.js-dist-min/plotly.min.js`. Redirect both the deep path and
      // the package root.
      {
        find: 'plotly.js/dist/plotly',
        replacement: 'plotly.js-dist-min/plotly.min.js',
      },
      { find: 'plotly.js', replacement: 'plotly.js-dist-min/plotly.min.js' },
    ],
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8790',
        changeOrigin: true,
      },
      // Proxy `/static/*` so the BitmapLayer can fetch the
      // MP-wide WC fuel-class PNG (Phase 2). v3 backend serves
      // these as static files via SimpleHTTPRequestHandler.
      '/static': {
        target: 'http://localhost:8790',
        changeOrigin: true,
      },
    },
  },
});
