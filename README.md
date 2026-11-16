# Aajki clone — frontend + backend

A production-style clone of the **Aajki** app, in two parts:

- **Frontend** (`src/`, React + Vite) — polls, stories, topics, leaderboards, profile. Polls
  are interactive: results stay hidden until you pick an option.
- **Backend** (`server/`, Express) — a reverse proxy to the real Aajki API **and** a
  server-side **sentiment analysis** admin portal. All sentiment logic is backend-only; it
  never ships in the frontend bundle.

The backend proxy exists because the Aajki API sends **no CORS headers**, so a browser on a
Vercel domain can't call it directly. Everything goes through `/api/aajki/*` on our own origin.

See [`ENDPOINTS.md`](./ENDPOINTS.md) for the full reverse-engineered API reference.

## Two backend options

1. **Node proxy** (`server/`) — forwards to the real Kalki API. Default; good for live data.
2. **Python backend** (`backend-python/`) — a **standalone** FastAPI backend that serves the
   same API from its **own seed data**, with no Kalki dependency. This is the "our own
   backend" step. See [`backend-python/README.md`](./backend-python/README.md).

The frontend picks its backend from one env var: set **`VITE_API_BASE`** to the Python
backend's URL to run fully independent of Kalki; leave it unset to use the Node proxy.

## Architecture

```
browser ──/api/aajki/*──▶ backend proxy ──▶ https://app.getkalki.com   (polls, stories, …)
        ──/admin────────▶ backend ──▶ sentiment engine (server/sentiment.mjs)
        ──static─────────▶ dist/ (React app)
```

Same paths in dev and prod. In dev, Vite (5180) proxies `/api` and `/admin` to the Express
backend (8787). On Vercel, `api/index.js` runs the same Express app as a serverless function.

## Run locally

```bash
npm install
npm run dev
```

- App: http://127.0.0.1:5180
- Sentiment admin portal: http://127.0.0.1:5180/admin
- `npm run dev` starts both the frontend and the backend together.

Single-process production-style run (after a build):

```bash
npm run build
npm start          # serves dist/ + /api + /admin on http://127.0.0.1:8787
```

## Deploy to Vercel

1. Push this folder to a Git repo and “Import Project” in Vercel (or run `vercel`).
2. Vercel reads `vercel.json`: it builds the frontend (`npm run build` → `dist/`) and runs
   `api/index.js` as a serverless function for `/api/*` and `/admin`.
3. No environment variables are required. Optional overrides:

| Env var | Default | Purpose |
|---------|---------|---------|
| `ADMIN_PASSWORD` | _(none)_ | **Set this** to protect `/admin` (Basic Auth). See below. |
| `ADMIN_USER` | `admin` | Admin username. |
| `AAJKI_API` | `https://app.getkalki.com` | Upstream API (point at your own backend later). |
| `AAJKI_CLIENT` | `web` | Value sent as `x-kalki-client`. |
| `SENTIMENT_FEED_PAGES` | `6` | Feed pages aggregated for sentiment. |
| `SENTIMENT_TTL_MS` | `120000` | Sentiment cache lifetime. |

After deploy:
- App at `https://<your-app>.vercel.app`
- Admin portal at `https://<your-app>.vercel.app/admin`

### Admin portal security

`/admin` and `/api/admin/sentiment` are protected by HTTP Basic Auth:

- **Deployed:** if `ADMIN_PASSWORD` is **not** set, `/admin` returns **503 (closed)** — it is
  never left open on a public URL. Set `ADMIN_PASSWORD` (and optionally `ADMIN_USER`) in the
  Vercel project's Environment Variables, redeploy, then sign in at `/admin`.
- **Local dev:** with no password set, `/admin` is open on `localhost` only (convenience).
  Set `ADMIN_PASSWORD` in `.env`/your shell to require the login locally too.

The proxy (`/api/aajki/*`) stays public — only the admin routes are gated.

## Sentiment admin portal

`/admin` aggregates recent polls server-side and shows:
- Overall public **mood** and **crowd optimism** gauges.
- Per-category breakdown (mood, optimism, consensus, volume).
- Most positive / negative / divisive / engaged polls.

Sentiment = poll-wording tone (lexicon in `server/sentiment.mjs`) blended with the live
vote split. It's a derived signal, not an official Aajki metric.

## Pointing at your own backend

Set `AAJKI_API` to your backend's base URL. As long as it matches the shapes in
`ENDPOINTS.md`, both the frontend and the sentiment portal work unchanged.

## Notes

- Voting is recorded **locally** (localStorage) so results reveal after you answer.
  Submitting a vote to Aajki needs a signed-in session (see `ENDPOINTS.md`).
- OTP sign-in on the Account tab hits the real backend and sends a real SMS.
