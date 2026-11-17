# Aajki backend (Python / FastAPI)

A **standalone**, database-backed backend that serves the app's API **and** a full
**admin management console**. No calls to Kalki or any external service.

- **Database:** set `DATABASE_URL` (Postgres/MySQL/SQLite). Tables are created and seeded
  automatically on first run. With no `DATABASE_URL` it uses a local SQLite file for dev.
- **Admin console** at `/admin` (Basic Auth): dashboard, create/edit/close/delete
  **questions**, manage **topics**, moderate **comments**, view the **audience** (users),
  **block/unblock** users, and a **sentiment** analytics page. Changes are live immediately
  in the app.

Modules: `db.py` (engine), `models.py` (ORM), `store.py` (queries + serialization),
`admin_console.py` (admin UI), `main.py` (routes), `seed.py` (initial sample content).

## What it serves

| Route | Purpose |
|-------|---------|
| `GET /healthz` | health check |
| `GET /v2/app-config` | app/version config |
| `GET /v2/polls/feed?cursor=` | paginated poll feed |
| `GET /v2/polls/home` | topics + daily info |
| `GET /v2/polls/topics` · `/v2/polls/topics/{id}` | topics + a topic's polls |
| `GET /v2/polls/{id}` · `/v2/polls/{id}/comments` | poll detail + comments |
| `GET /v2/stories/daily` | daily stories (sections + questions) |
| `GET /v2/leaderboards` · `/v2/leaderboards/{id}` | boards + winners |
| `POST /v2/auth/otp/send` · `/v2/auth/otp/verify` | **mock** auth (demo code `000000`, no SMS) |
| `GET /v2/me` · `/v2/me/wallet` | profile + wallet (needs the token from verify) |
| `GET /admin` · `GET /api/admin/sentiment` | sentiment portal (Basic Auth) |

Data lives in `seed.py` — swap it for a real database when ready. Sentiment logic is in
`sentiment.py` (backend-only). Shapes match [`../ENDPOINTS.md`](../ENDPOINTS.md).

## Run locally

```bash
cd backend-python
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

- API at http://127.0.0.1:8000
- Admin portal at http://127.0.0.1:8000/admin

Then run the frontend pointed at it:

```bash
# from the project root
VITE_API_BASE=http://localhost:8000 npm run dev:web
```

(Or add `VITE_API_BASE=http://localhost:8000` to a `.env.local` in the project root.)

## Deploy

### Option A — Render (simplest for FastAPI)
1. New → **Web Service** → connect the `Aajki` repo.
2. **Root Directory:** `backend-python`
3. **Build command:** `pip install -r requirements.txt`
4. **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add env var `ADMIN_PASSWORD` (to open `/admin`). Deploy → you get a URL like
   `https://aajki-api.onrender.com`.

### Option B — Vercel (separate project)
1. Import the same repo as a **new** Vercel project.
2. Set **Root Directory** to `backend-python` (this folder's `vercel.json` uses the Python runtime).
3. Add env var `ADMIN_PASSWORD`. Deploy.

### Point the frontend at it
In your **frontend** Vercel project → Settings → Environment Variables, add:

```
VITE_API_BASE = https://<your-backend-url>
```

Redeploy the frontend. It now runs entirely on this backend — no Kalki.

## Config

| Env var | Default | Purpose |
|---------|---------|---------|
| `ADMIN_PASSWORD` | _(none)_ | protects `/admin` (Basic Auth). Unset = `/admin` open on localhost only, 503 when deployed. |
| `ADMIN_USER` | `admin` | admin username |

## Notes

- Auth is a **mock** for a self-contained demo: `otp/send` sends no SMS, and any 4–6 digit
  code (use `000000`) verifies and returns a token. Replace with real auth for production.
- Seed IDs are deterministic, so links stay valid across restarts.
