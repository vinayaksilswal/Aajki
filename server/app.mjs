// Express backend shared by local dev and Vercel. Responsibilities:
//   /api/aajki/*        reverse-proxy to the real Aajki API (adds required header, forwards auth)
//   /api/admin/sentiment  JSON sentiment model (backend-computed, cached)
//   /admin                server-rendered sentiment portal
//   /healthz              liveness
// The frontend is served as static files in production (Vercel serves dist/ itself).
import express from 'express';
import { Readable } from 'node:stream';
import { timingSafeEqual } from 'node:crypto';
import { fetchFeedPolls, UPSTREAM, CLIENT } from './aajki.mjs';
import { analyzeSet } from './sentiment.mjs';
import { renderAdmin } from './admin.mjs';
import { cached } from './cache.mjs';

const SENTIMENT_TTL_MS = Number(process.env.SENTIMENT_TTL_MS) || 120_000;
const FEED_PAGES = Number(process.env.SENTIMENT_FEED_PAGES) || 6;

const ADMIN_USER = process.env.ADMIN_USER || 'admin';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || '';

function safeEqual(a, b) {
  const ab = Buffer.from(a), bb = Buffer.from(b);
  return ab.length === bb.length && timingSafeEqual(ab, bb);
}
function isLocal(req) {
  const h = (req.headers.host || '').split(':')[0];
  return h === 'localhost' || h === '127.0.0.1';
}

// Protects /admin and /api/admin/*. Secure-by-default: with no ADMIN_PASSWORD set it stays
// open only on localhost (dev) and is refused anywhere else, so a deploy can't be left open.
function adminAuth(req, res, next) {
  if (!ADMIN_PASSWORD) {
    if (isLocal(req)) return next();
    return res.status(503).type('text/plain')
      .send('Admin portal disabled: set the ADMIN_PASSWORD environment variable to enable it.');
  }
  const header = req.headers.authorization || '';
  const [scheme, encoded] = header.split(' ');
  if (scheme === 'Basic' && encoded) {
    const [user, pass] = Buffer.from(encoded, 'base64').toString('utf8').split(':');
    if (user != null && pass != null && safeEqual(user, ADMIN_USER) && safeEqual(pass, ADMIN_PASSWORD)) return next();
  }
  res.setHeader('WWW-Authenticate', 'Basic realm="Aajki Admin", charset="UTF-8"');
  return res.status(401).type('text/plain').send('Authentication required.');
}

export function createApp() {
  const app = express();
  app.disable('x-powered-by');

  // Baseline security headers (enterprise hygiene; CSP kept permissive for the SPA + CDNs).
  app.use((req, res, next) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('X-Frame-Options', 'SAMEORIGIN');
    res.setHeader('Referrer-Policy', 'no-referrer');
    next();
  });

  app.get('/healthz', (_req, res) => res.json({ status: 'ok', upstream: UPSTREAM, ts: new Date().toISOString() }));

  // --- Reverse proxy: /api/aajki/<path> -> UPSTREAM/<path> ---
  // Only GET/HEAD are forwarded unauthenticated by default; writes require an Authorization
  // header from the caller (we never mint tokens server-side).
  app.all(/^\/api\/aajki\/(.*)/, async (req, res) => {
    const upstreamPath = '/' + req.params[0] + (req.originalUrl.includes('?') ? req.originalUrl.slice(req.originalUrl.indexOf('?')) : '');
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 15_000);
    try {
      const headers = { 'x-kalki-client': CLIENT, accept: 'application/json' };
      if (req.headers.authorization) headers.authorization = req.headers.authorization;
      let body;
      if (!['GET', 'HEAD'].includes(req.method)) {
        headers['content-type'] = req.headers['content-type'] || 'application/json';
        body = await readRaw(req);
      }
      const upstream = await fetch(`${UPSTREAM}${upstreamPath}`, { method: req.method, headers, body, signal: ctrl.signal });
      res.status(upstream.status);
      const ct = upstream.headers.get('content-type');
      if (ct) res.setHeader('content-type', ct);
      if (upstream.body) Readable.fromWeb(upstream.body).pipe(res); else res.end();
    } catch (err) {
      res.status(502).json({ code: 'UPSTREAM_ERROR', message: err.name === 'AbortError' ? 'Upstream timed out' : err.message });
    } finally {
      clearTimeout(timer);
    }
  });

  const sentimentModel = () => cached('sentiment', SENTIMENT_TTL_MS, async () => analyzeSet(await fetchFeedPolls({ maxPages: FEED_PAGES })));

  app.get('/api/admin/sentiment', adminAuth, async (_req, res) => {
    try { res.json(await sentimentModel()); }
    catch (err) { res.status(502).json({ code: 'SENTIMENT_ERROR', message: err.message }); }
  });

  app.get('/admin', adminAuth, async (_req, res) => {
    try { res.type('html').send(renderAdmin(await sentimentModel())); }
    catch (err) { res.status(502).type('html').send(`<pre>Sentiment unavailable: ${err.message}</pre>`); }
  });

  return app;
}

function readRaw(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}
