# Bharat Foreseez API (FastAPI)

One deployable backend with internal modules, following spec section 5 of the MVP Technical
Specification:

| Module | Owns |
|---|---|
| `identity` | users, app sessions, daily activity; profile, self-exclusion, data export and account deletion |
| `ledger` | the double-entry points ledger (transactions, entries, balances). The only code that moves points. No payout or transfer path |
| `forecasts` | topics, questions, calls, settlements, disputes |
| `debate` | comments and replies, reports, blocks, moderation actions |
| `engagement` | daily check-in and daily quiz |
| `standing` | badge catalogue; ranks and leaderboards (read from the ledger) |
| `compliance` | election quiet periods, grievances |
| `policy` | admin-set feature switches per state, daily reward cap, rank thresholds |
| `sentiment` | public sentiment dashboard (aggregates only, minimum group 50); admin mood signal |
| `news` | ticker headlines |
| `governance` | admin accounts with two-factor sign-in, roles, audit log, operations reports, the admin panel |

Sign-in with phone OTP, Google/Apple, the 18+ gate and consent records are milestone M2 and are
not built yet. Until then the app gets a pseudonymous **device account** from `POST /v1/session`.

A module never writes another module's tables. The schema is owned by Alembic migrations, and
the app never creates or alters tables at startup.

## Run locally

```bash
cd backend-python
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # macOS/Linux: .venv/bin/pip
set APP_ENV=development
set DATABASE_URL=sqlite:///local.db        # use a local DB, not the shared one in .env
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m uvicorn main:app --reload --port 8000
```

- API: <http://localhost:8000/v1/questions>. OpenAPI docs are at `/docs` in development only.
- Admin: <http://localhost:8000/admin>. Set `ADMIN_USER` and `ADMIN_PASSWORD` to bootstrap the first
  Super Admin, then set up two-factor sign-in.
- The frontend (`npm run dev` in the repo root) reads `VITE_API_BASE=http://localhost:8000`.

## Tests

```bash
.venv/Scripts/python -m pytest
```

The tests build a throwaway SQLite database with the real migrations. They never use `.env`,
never touch a real database and never reach the network.

## Public API (v1)

Reads that need no session: `GET /v1/questions`, `/v1/questions/{id}`, `/v1/ticker`, `/v1/sentiment`,
`/v1/app-config?region=`, `/v1/badges`, `/healthz`.

With `Authorization: Bearer <token>` (from `POST /v1/session`):

| Route | Purpose |
|---|---|
| `GET /v1/me`, `PATCH /v1/me` | Profile, points, rank, stats, badges, check-in status, restrictions, regional switches |
| `POST /v1/questions/{id}/calls` | Commit points to an outcome. **`Idempotency-Key` header required**; a retry returns the first call |
| `GET /v1/me/calls`, `GET /v1/me/ledger` | My calls; the points ledger |
| `POST /v1/questions/{id}/disputes` | Dispute a settled result inside its window |
| `GET/POST /v1/questions/{id}/comments`, `DELETE /v1/comments/{id}`, `POST /v1/comments/{id}/report`, `POST /v1/comments/{id}/block-author` | Debate |
| `POST /v1/me/checkin`, `GET /v1/quiz/today`, `POST /v1/quiz/{id}/answer` | Daily rewards |
| `GET /v1/leaderboards?period=daily\|weekly\|all` | Leaderboards |
| `POST /v1/me/self-exclusion` | Take a break (1, 7, 30 or 90 days) |
| `POST /v1/grievances`, `GET /v1/me/grievances` | Grievance portal |
| `GET /v1/me/export`, `DELETE /v1/me` | DPDP data copy and erasure |

Every response carries `X-Correlation-ID`, and every error uses the same envelope:
`{"error": {"code", "message", "correlation_id", "details?"}}`. Abuse limits (sign-ups per
network, calls, comments, reports, admin sign-in) are kept in the database so every instance
shares them.

## Admin panel

`/admin`. Accounts with argon2 passwords and mandatory TOTP two-factor sign-in, six roles from
the spec, and an append-only audit log (Postgres triggers reject UPDATE and DELETE on the audit
log and the ledger). See `../docs/operations.md` for the first sign-in, settlement, moderation,
quiet periods, the restore drill and the pre-launch checklist.

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

See `.env.example`. Staging and production refuse to start without `DATABASE_URL` and an
explicit `ALLOWED_ORIGINS` list.

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
