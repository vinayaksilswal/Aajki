# Operations runbook (Phase 1)

## Admin accounts

1. **First Super Admin.** While no admin account exists, sign in at `/admin` with the bootstrap
   login `ADMIN_USER` / `ADMIN_PASSWORD` from the backend environment. The panel then makes you
   set up two-factor sign-in with an authenticator app. After this, the bootstrap values sign
   nobody in, and you can remove `ADMIN_PASSWORD` from the environment.
2. **Everyone else.** In **Admin accounts**, add each person with a temporary password and their
   roles. On first sign-in they must set up two-factor sign-in and choose a new password.

| Role | Can | Can't |
|---|---|---|
| Super Admin | Admin accounts, regions and feature switches, quiet periods, points economy, ranks and badges, operations, audit log | Settle questions |
| Forecast & Content Ops | Questions, news ticker, topics, daily quiz | Settle questions |
| Settlement Officer | Propose results with the source link, review disputes | Approve results |
| Settlement Approver | Approve or reject proposed results, review disputes | Propose results |
| Moderator | Moderation queue, warn, suspend and block users | Change questions or points |
| Compliance & Grievance Officer | Grievances, suspensions, audit export, operations | Change questions or points |

Nobody can hold both settlement roles, and nobody can approve a result they proposed. At least one
active Super Admin is always kept. If someone loses their phone, a Super Admin uses **Reset 2FA**.

## Settling a question

1. When a question closes it appears in **Settlement → Closed, awaiting a result**.
2. A Settlement Officer opens it, picks the result, links the official page used, and submits.
3. A Settlement Approver (a different person) checks the source and approves. Points are
   released at once: each correct call receives *points committed × total points ÷ points on the
   correct outcome*, rounded down.
4. The system voids the question and returns every point instead when nobody chose the correct
   outcome, when only one outcome had calls, or when the officer proposes **Void** for a
   cancelled or abandoned event.
5. Users can dispute the result for 48 hours (`DISPUTE_WINDOW_HOURS`). If a dispute is upheld, the
   officer proposes the corrected result and an approver approves it. The ledger reverses the
   earlier entries with new ones; nothing is edited or deleted.

## Moderation and grievances

- Three reports hold a comment out of view until a moderator decides. Target: act within
  24 hours. The queue marks overdue items, and **Operations** shows handling times.
- Every action needs a reason code. Use *Election-period restriction* for removals under an
  election quiet period.
- Grievances: acknowledge within 24 hours, resolve within 15 days (IT Rules 2021). A user's
  activity is visible to support only on a ticket where they ticked consent.

## Election quiet periods

**Regions & flags → Election quiet periods.** Choose the states and the period. While it's
active, election-sensitive questions tagged with those states (and any without a state) hide
their live chance, and drop out of the sentiment dashboard when that box is ticked.
`ELECTION_QUIET_PERIOD=true` in the backend environment is an emergency switch for every state.

## Backups and the restore drill

Targets (spec s.4): recovery point 15 minutes, recovery time 4 hours.

- **Neon** keeps point-in-time history (7 days on the Launch plan, 30 on Scale). Confirm the
  plan's retention covers at least 7 days before launch.
- **Drill, monthly and before launch:**
  1. In Neon, create a branch from a point in time about 1 hour ago (*Branches → Create branch →
     Past data*).
  2. Point a local backend at the branch's connection string (never commit it):
     `DATABASE_URL=<branch url> python -m alembic current` should print the head revision.
  3. Check the ledger balances: in **Points economy**, *Issued = available + committed + pools +
     rounding* must read **balanced**, or run `python -m pytest` style checks against a copy.
  4. Record the time taken and delete the branch.
- **Mumbai move:** restore the latest Neon backup into the Mumbai-region database with
  `pg_dump`/`pg_restore`, run `alembic upgrade head`, switch `DATABASE_URL`, and keep the old
  database read-only for a week.

## Load test

`loadtest/calls.k6.js` checks the spec's targets (50 calls/s by design, tested to 150 calls/s;
read p95 under 200 ms, write p95 under 400 ms). Run it against **staging** only; it creates device
accounts and calls. Vercel serverless with Neon in the US is not representative of the Mumbai
production setup: run it again after the move.

## Pre-launch checklist

- [ ] **Phone sign-in (M2):** OTP via an SMS provider with TRAI DLT templates, Google/Apple
      sign-in, the 18+ gate, purpose-wise consent and withdrawal. The app must not open to the
      public before this ships: device accounts collect calls without recorded consent.
- [ ] Counsel's written opinion on classification under the Promotion and Regulation of Online
      Gaming Act 2025, the RP Act s.126/126A question, and prize wording.
- [ ] Privacy notice and terms approved by counsel; set `PRIVACY_NOTICE_URL` and `TERMS_URL`.
- [ ] Grievance Officer name, email, phone and address in `GRIEVANCE_OFFICER_*`.
- [ ] Hosting and database in the Mumbai region (DPDP data residency in the spec).
- [ ] A licensed or editorial news source to replace Google News RSS.
- [ ] A moderation vendor and object storage, to open photo, video and voice-note attachments.
- [ ] `SENTRY_DSN` set; alerts routed to the on-call person.
- [ ] Android shell: Play Integrity check and the native update prompt (`VITE_APP_BUILD`).
- [ ] Load test passed on the Mumbai staging environment; restore drill done.
- [ ] Store listings reviewed against Google Play and App Store gambling and simulated-gambling
      policies, with the points-only design visible in the listing.
