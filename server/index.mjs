// Local backend runner. In production on Vercel, api/index.js uses the same app instead.
import path from 'node:path';
import express from 'express';
import { fileURLToPath } from 'node:url';
import { createApp } from './app.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT) || 8787;
const app = createApp();

// Serve the built frontend if it exists (production-style single-process run).
const dist = path.resolve(__dirname, '..', 'dist');
import('node:fs').then(({ existsSync }) => {
  if (existsSync(dist)) {
    app.use(express.static(dist));
    app.get(/^\/(?!api\/|admin|healthz).*/, (_req, res) => res.sendFile(path.join(dist, 'index.html')));
  }
});

app.listen(PORT, () => console.log(`Aajki backend on http://127.0.0.1:${PORT}  (proxy /api/aajki, portal /admin)`));
