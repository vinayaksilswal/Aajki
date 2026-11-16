import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// In dev the frontend (5180) proxies backend paths to the Express backend (8787),
// which then talks to the real Aajki API. This mirrors production on Vercel, where the
// same paths are served by the serverless function. `npm run dev` starts both.
const BACKEND = process.env.BACKEND_ORIGIN || 'http://127.0.0.1:8787';

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5180,
    strictPort: true,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      '/admin': { target: BACKEND, changeOrigin: true },
      '/healthz': { target: BACKEND, changeOrigin: true },
    },
  },
});
