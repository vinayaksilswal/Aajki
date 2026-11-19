# Bharat Foreseez

Forecasting app for India. Users spend **Forecast Points**, never money, to make calls on real
outcomes in elections, markets, sports, policy, world events and community questions. Phase 1
follows the client's *MVP Technical Specification (revised)*. It uses a closed-loop points model
with no purchase or cash-out path, status-only rewards and DPDP-aligned privacy.

| Part | Where | Stack |
|---|---|---|
| Consumer app (web, and the WebView inside the Android shell) | `index.html`, `src/app/` | Vite, vanilla JS |
| API and admin panel | `backend-python/` | FastAPI, SQLAlchemy, Alembic, Postgres |

## Local development

```bash
# 1. API on a local SQLite database (see backend-python/README.md)
cd backend-python
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
set DATABASE_URL=sqlite:///local.db
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m uvicorn main:app --port 8000

# 2. App (repo root), pointed at the API
copy .env.example .env.local      # VITE_API_BASE=http://localhost:8000
npm ci && npm run dev             # http://localhost:5180
```

Create and publish questions at <http://localhost:8000/admin>. Refresh headlines on the **News**
page to fill the in-app ticker.

The app has no offline or sample data. If the API can't be reached it shows an error with a
reference ID, which matches the server log's correlation ID.

## App behaviour

- **Onboarding:** built, but gated off for browser testing (`SHOW_ONBOARDING` in
  `src/app/main.js`). Turn it on for the packaged APK.
- **Theme:** the sun/moon button left of the notification bell switches light and dark. The
  choice persists on the device and is applied before first paint.
- **Phase 2 features** (prizes, Plus, sponsored and user-created polls, Spin-the-Wheel) are off.
  Their flags come from the API's `/v1/app-config`.
- **Calls:** until sign-in and the server-side ledger ship, calls and points are kept on the
  device as a labelled preview. They don't count toward the public chance.

## Deploy

- **App:** Vercel project at the repo root. Set `VITE_API_BASE` to the API URL. `vercel.json`
  adds the security headers.
- **API:** separate Vercel project with root `backend-python`. See `backend-python/README.md`
  for the environment and the one-time migration of the existing database.
