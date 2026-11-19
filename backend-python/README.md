# Bharat Foreseez API (FastAPI)

One deployable backend with internal modules, following spec section 5 of the MVP Technical
Specification:

| Module | Owns | Status |
|---|---|---|
| `forecasts` | questions (`polls`), topics, participation (`votes`) | M1 |
| `news` | ticker headlines (`news_items`) | M1 |
| `governance` | admin panel (interim Basic Auth) | M1. Roles, 2FA and the audit log come in M6 |
| `identity` | users | M1 admin view. Sign-in, OTP, consent and DPDP rights come in M2 |
| `debate` | comments | M1 admin view. Replies, attachments and moderation come in M4 |
| `sentiment` | admin mood signal | M1. The public dashboard comes in M5 |

A module never writes another module's tables. The schema is owned by Alembic migrations, and
the app never creates or alters tables at startup.

## Run locally

```bash
cd backend-python
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # macOS/Linux: .venv/bin/pip
set DATABASE_URL=sqlite:///local.db        # use a local DB, not the shared one in .env
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m uvicorn main:app --reload --port 8000
```

- API: <http://localhost:8000/v1/questions>. OpenAPI docs are at `/docs` in development only.
- Admin: <http://localhost:8000/admin>. It is open in development when `ADMIN_PASSWORD` is unset.
- The frontend (`npm run dev` in the repo root) reads `VITE_API_BASE=http://localhost:8000`.

## Tests

```bash
.venv/Scripts/python -m pytest
```

The tests build a throwaway SQLite database with the real migrations. They never use `.env`,
never touch a real database and never reach the network.

## Public API (v1)

| Route | Purpose |
|---|---|
| `GET /v1/questions?status=open\|closed\|settled&category=&q=&sort=closing\|trending&cursor=&limit=` | Question feed |
| `GET /v1/questions/{id}` | Question detail, with the chance per outcome and the resolution source and rule |
| `GET /v1/ticker` | Context-ticker headlines, with attribution |
| `GET /v1/app-config` | Feature flags (all Phase 2 flags off), categories, Grievance Officer, legal links |
| `GET /healthz` | Liveness and database check |

Every response carries `X-Correlation-ID`, and every error uses the same envelope:
`{"error": {"code", "message", "correlation_id", "details?"}}`.

## Question lifecycle

`draft` → publish → `scheduled` / `open` → `closed` (derived from the publish window). Admins can
also **pause**, **resume** or **void** a question. Publishing needs a closing time at least 5
minutes ahead, an **official https resolution source** and a **resolution rule**. Once a question
is published, its terms (question, outcomes, timing, resolution) are locked. Only drafts can be
deleted. The spec vocabulary is enforced on question copy: words like odds, bet, stake and payout
are rejected.

News headlines are **never** published automatically. The scheduled job only fills the ticker.
An admin drafts a question from a headline, rewrites it as a checkable question, then publishes it.

## Configuration

See `.env.example`. Staging and production refuse to start without `DATABASE_URL`,
`ADMIN_PASSWORD` and an explicit `ALLOWED_ORIGINS` list.

## Deploy (Vercel, separate project, root `backend-python`)

1. Set the environment variables from `.env.example` (`APP_ENV=production`).
2. **First time on the existing prototype database only:** the tables already exist, so mark
   the baseline and then apply the Phase 1 migration. Run this once from a machine with
   `DATABASE_URL` pointing at that database:
   ```bash
   python -m alembic stamp 0001_baseline
   python -m alembic upgrade head
   ```
   `0002` turns every existing question into a **draft**, because none has a resolution source
   yet. It also maps categories to the spec's six and strips the fabricated `base_votes`. Take a
   database branch or backup first. These data changes are one-way.
3. On a fresh database, run `python -m alembic upgrade head` instead.
4. The daily Vercel Cron (`vercel.json`) calls `/api/cron/news-import` with `CRON_SECRET`.

Before public launch the spec requires personal data to be hosted in the Mumbai region, and the
ticker to use a licensed or editorial news source. Google News RSS is for staging only.
