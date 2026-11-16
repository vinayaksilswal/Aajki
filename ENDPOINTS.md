# Aajki — Backend API Reference

Reverse-engineered from the Android app `com.getkalki.app` (React Native / Hermes
bytecode bundle `assets/index.android.bundle`, Hermes v96). Endpoint **paths** come from
the app's Hermes string table; request/response **shapes** were confirmed by read-only
`GET` calls to the live server. Anything not confirmed live is marked **(inferred)** and
should be verified before you rely on it.

> This document exists so the clone can call the real backend now, and so you can build
> your own compatible backend later. Treat it as a draft contract, not an official spec.

---

## Hosts

| Host | Role |
|------|------|
| `https://app.getkalki.com` | **Production API** (all `/v2/*` routes) **and** the web app (SPA served on unknown paths). This is the base URL the clone uses. |
| `https://staging.getkalki.com` | Staging API, same routes as production. |
| `https://api.getkalki.com` | A separate gateway. Only `/health` responded; `/v2/*` returns 404 here. Likely logging/metrics ingest (`/v1/logs`, `/v1/metrics`, `/v1/daily-stories` strings point here). Do **not** use for `/v2`. |
| `https://mock.getkalki.com` | Mock/fixture server used in development builds (avatars, media, slides). Not reliably up. |

**Base URL for the clone:** `https://app.getkalki.com`

## Conventions

- **Auth:** `Authorization: Bearer <token>`. The token comes from the OTP or social login
  flow. Unauthenticated calls to protected routes return **401** `UNAUTHORIZED` "Sign in to
  continue."
- **Client header:** every request sends `x-kalki-client` (e.g. `web`). Other observed
  headers: `x-kalki-signup-token` (during signup, before full auth), `x-kalki-store-spends`
  (Hubble store), `x-circle` (friends/circle context).
- **Content type:** `application/json` for bodies; `multipart/form-data` for avatar upload.
- **IDs are prefixed ULIDs:** `pl_` poll, `tpc_` topic, `dst_` daily story, `lb_` board,
  `lbr_` board round, `lbq_` board frequency, `usr_` user, etc.
- **Success envelope (varies by service):**
  - Most `/v2` routes return the resource object directly (e.g. `/v2/polls/feed` → `{items,…}`).
  - `api.getkalki.com` wraps responses: `{"isError":false,"message":"…","data":{…}}`.
- **Error envelope (`app.getkalki.com`):**
  ```json
  {
    "code": "UNAUTHORIZED",
    "http_status": 401,
    "message": "Sign in to continue.",
    "error": { "code": "UNAUTHORIZED", "message": "Sign in to continue." },
    "issues": [ { "path": "slug", "message": "Invalid…" } ],   // only on VALIDATION
    "request_id": "…"
  }
  ```
  Observed codes: `UNAUTHORIZED` (401), `NOT_FOUND` (404), `VALIDATION` (400).
- **Pagination:** cursor based. Responses include `next_cursor` (string or `null`); pass it
  back as `?cursor=`. Some lists also take `?limit=`.
- **Realtime:** Server-Sent Events (`EventSource`) for `/v2/markets/stream` and
  `/v2/hubble/session`.

Status legend: ✅ confirmed live · 🔒 route exists, needs auth (401) · ⚠️ route exists, no
data right now (404/400 with a *data* message) · ❓ inferred from the bundle only.

---

## 1. Config

### `GET /v2/app-config` ✅ public
App version gate and store links. No auth.
```json
{
  "min_supported_build": 11,
  "latest_build": 11,
  "store_urls": { "ios": "https://apps.apple.com/app/id6792832038",
                  "android": "https://play.google.com/store/apps/details?id=com.getkalki.app" },
  "app_icon": null,
  "reward_frame": { "enabled": true, "coin_target": 500, "progress_suffix": "/500 Coins", "title": "You hit 500 c…" },
  "phone_step_required": true|false
}
```

---

## 2. Auth  (`/v2/auth/*`)  — all **POST**, public

| Endpoint | Body (inferred) | Purpose |
|----------|-----------------|---------|
| `POST /v2/auth/otp/send` ❓ | `{ "phone": "+91…" }` | Send a one-time code by SMS. **Sends a real SMS — do not call without a real number and consent.** |
| `POST /v2/auth/otp/verify` ❓ | `{ "phone": "+91…", "code": "123456" }` | Verify code → returns auth token (+ possibly `x-kalki-signup-token` for new users). |
| `POST /v2/auth/google` ❓ | `{ "id_token": "…" }` | Google sign-in. |
| `POST /v2/auth/apple` ❓ | `{ "authorization_code": "…", "id_token": "…" }` | Apple sign-in (supports Apple private relay email). |
| `POST /v2/auth/dob` ❓ | `{ "dob": "YYYY-MM-DD" }` + `x-kalki-signup-token` | Age-gate step during signup. |
| `POST /v2/auth/logout` ❓ | — | Invalidate the current session/token. |
| `POST /v2/link/exchange` ❓ | `{ "link": "https://app.getkalki.com/join/…" }` | Exchange a deep/invite link for its target + referral. |

Deep-link / invite pattern: `https://app.getkalki.com/join/<code>` (also short links at
`https://getkalki.com/s/…`).

---

## 3. Polls  (`/v2/polls/*`)  — the core feed

### `GET /v2/polls/home` ✅ public
Home screen payload: curated topics, daily set, user balance/goal (null when logged out),
stories.
```
{ topics[], open_topic_ids[], daily_set, onboarding, balance, daily_bonus_earned,
  goal, stories[], user_stories[], daily_remaining, as_of }
```
`topics[]` item: `{ id, slug, title, short_label, blurb, … }`.

### `GET /v2/polls/feed` ✅ public
Paginated poll feed. Query: `?category=<politics|movies|…>` (optional), `?cursor=<next_cursor>`.
```json
{ "items": [ { "type": "poll", "poll": { … } } ], "next_cursor": "…|null", "category": "…", "as_of": "ISO" }
```
`poll` object:
```json
{ "id":"pl_…", "slug":"…", "category":"politics", "beat":"politics",
  "subcategory_key":null, "path_key":null,
  "question":"…", "description":null, "image_url":"https://…",
  "display_kind":"binary", "layout":null,
  "options":[ {"id":"yes","label":"Yes","emoji":null,"votes":8},
              {"id":"no","label":"No","emoji":null,"votes":1} ],
  "total_votes":9, "my_vote":null, "like_count":0, "liked_by_me":false,
  "comment_count":0, "is_prediction":false, "show_friends":false,
  "trending":false, "tags":[], "primary_topic_id":"tpc_…" }
```

### `GET /v2/polls/{id}` ✅ public
Single poll (same `poll` shape as above).

### `GET /v2/polls/{id}/comments` ✅ public
`{ "items": [ … ], "next_cursor": null }`. Comment item (inferred): `{ id, author, body, created_at, like_count }`.

### Poll actions (auth) — **POST**, not called here to avoid mutating their data
| Endpoint | Body (inferred) | Purpose |
|----------|-----------------|---------|
| `POST /v2/polls/{id}/vote` ❓ | `{ "option_id": "yes" }` | Cast/edit a vote. Vote editing is budget-limited (`vote_edit_limit_reached`, `vote_undone`). |
| `POST /v2/polls/{id}/unvote` ❓ | — | Remove a vote. |
| `POST /v2/polls/{id}/like` ❓ / `POST /v2/polls/{id}/react` ❓ | `{ "reaction": "…" }` | Like / react. |
| `POST /v2/polls/{id}/comment` ❓ | `{ "body": "…" }` | Add a comment. |
| `POST /v2/polls/{id}/report` ❓ / `…/flag` ❓ | `{ "reason": "…" }` | Report content. |
| `POST /v2/polls/{id}/share` ❓ | — | Register a share. |
| `POST /v2/polls/impressions` ❓ | `{ "impressions": [ { "poll_id", "shown_at" } ] }` | Batch view tracking. |

### Other poll reads
| Endpoint | Status | Purpose |
|----------|--------|---------|
| `GET /v2/polls/topics` | ✅ public | All topics: `{ items: [ {id,slug,title,short_label,blurb,…} ] }`. |
| `GET /v2/polls/topics/{id}` | ❓ | Topic detail + its polls. |
| `GET /v2/polls/series` · `GET /v2/polls/series/{id}` | ❓ | Poll series. |
| `GET /v2/polls/sets/daily` | ⚠️ (404 "No daily set today") | Today's daily poll set. |
| `GET /v2/polls/stories/{id}` | ❓ | Poll-attached story. |
| `GET /v2/polls/trivia/{id}` | ❓ | Trivia poll. |
| `GET /v2/polls/group-picks/{id}` | ❓ | Group-pick game. |
| `GET /v2/polls/accounts/{id}` | ❓ | Public account's polls. |
| `GET /v2/polls/config` | ❓ | Poll client config. |
| `GET /v2/polls/me/calls` | 🔒 | My predictions ("calls"). |
| `GET /v2/polls/me/history` | 🔒 | My voting history. |
| `GET /v2/polls/me/notifications` | 🔒 | My notifications. |
| `GET /v2/polls/saves` · `GET/POST/DELETE /v2/polls/saves/{id}` | 🔒 | Saved polls. |

---

## 4. Stories  (`/v2/stories/*`)  — daily editorial

### `GET /v2/stories/daily` ✅ public
```
{ "edition": "2026-11-16", "stories": [ … ], "next_cursor": "…|null" }
```
`stories[]` item keys: `id (dst_…)`, `path`, `desk`, `shelf`, `subcategory_key`,
`edition_day`, `published_at`, `cover`, `context`, `questions[]`, `share_url`,
`relevance`, `share_hint`. (Supports `?cursor=`.)

| Endpoint | Status | Purpose |
|----------|--------|---------|
| `GET /v2/stories` · `GET /v2/stories/{id}` | ❓ | Story index / single story. |
| `GET /v2/stories/slides/image/{…}` | ❓ | Slide image asset. |

---

## 5. Leaderboards  (`/v2/leaderboards/*`)

### `GET /v2/leaderboards` ✅ public
```
{ boards[], server_time, copy, headline_monthly_paise, today_pool_paise }
```
`boards[]` item:
```json
{ "id":"lb_…", "title":"New Draw",
  "scope":{"kind":"app","label":"Entire app"},
  "status":"live", "accent":null, "prize_art":"prize:gift",
  "served":{ "frequency_id":"lbq_…","frequency":"daily","label":"Daily draw",
             "round_id":"lbr_…","round_label":"Day 3","state":"live",
             "opens_at":"ISO","closes_at":"ISO",
             "pitch":"Gift cards worth up to ₹500 each","players":115,
             "cancellation":null,"draw_at":"ISO" } }
```
Money fields are in **paise** (₹1 = 100 paise).

| Endpoint | Status | Purpose |
|----------|--------|---------|
| `GET /v2/leaderboards/{id}` | ❓ | Single board + standings. |
| `GET /v2/leaderboards/wins/{…}` | ❓ | Winners list. |

---

## 6. Me / Profile  (`/v2/me/*`)  — all 🔒 auth

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v2/me` | GET | Current user profile. |
| `/v2/me/profile` | PATCH ❓ | Edit display name / photo / bio. |
| `/v2/me/avatar` | GET / POST ❓ (multipart) | Get / upload avatar. |
| `/v2/me/wallet` | GET (`?cursor=`) | Coin wallet + ledger. |
| `/v2/me/stats` | GET | Play stats. |
| `/v2/me/activity` · `/v2/me/activity/seen` | GET · POST ❓ | Activity feed / mark seen. |
| `/v2/me/blocks` | GET | Blocked users. |
| `/v2/me/delete` | POST ❓ | Delete account (signs out everywhere). |
| `/v2/me/leaderboard-wins` | GET | My leaderboard wins. |
| `/v2/me/onboarding` | POST ❓ | Save onboarding progress (`onboarding_gate_accepted`). |
| `/v2/me/partner-import` | POST ❓ | Import from a partner app. |
| `/v2/me/prize-wallet` · `/v2/me/prize-wallet/entries` | GET | Prize balance + entries. |
| `/v2/me/skill-events` | GET (`?limit=`) | Skill-rating events. |
| `/v2/me/stories` · `/v2/me/story` · `/v2/me/story/answers` | GET | My stories / answers. |
| `/v2/me/story/complete` · `/v2/me/story/dismiss` | POST ❓ | Complete / dismiss a story. |
| `/v2/users/{id}` | GET ❓ | Another user's public profile. |

---

## 7. Prediction Markets  (`/v2/markets/*`)

| Endpoint | Status | Purpose |
|----------|--------|---------|
| `GET /v2/markets/rounds/current?instrument=<BTC|…>` | ⚠️ (404 "Not found" now) | Current market round for an instrument. |
| `GET /v2/markets/rounds/{id}` | ❓ | A round by id. |
| `GET /v2/markets/rounds/on/{YYYY-MM-DD}` | ❓ | Rounds on a date. |
| `GET /v2/markets/stream` | ❓ **SSE** | Live price/round stream (`EventSource`). |

---

## 8. Battles  (`/v2/battle/*`)  — realtime quiz

| Endpoint | Status | Purpose |
|----------|--------|---------|
| `GET /v2/battle/history` | ❓ | Past battles. |
| `GET /v2/battle/packs` | ❓ | Question packs. |
| `POST /v2/battle/queue` | ❓ | Enter matchmaking (`TEST_BATTLE_CLOCK`, `queueMicrotask`). |
| `GET /v2/room/{id}` · `POST /v2/room/join` | ❓ | Battle/watch rooms (e.g. `rooms/bigg-boss-20`). |

---

## 9. Rewards & Hubble store

| Endpoint | Status | Purpose |
|----------|--------|---------|
| `GET /v2/rewards/catalogue` | 🔒 | Gift-card / reward catalogue. |
| `GET /v2/rewards/claims?cursor=` · `POST /v2/rewards/claims` | 🔒 | List / create reward claims. |
| `GET /v2/hubble/session` | 🔒 **SSE** | Opens a session with **Hubble (Gullak Technologies)**, the third-party gift-card store. Uses `x-kalki-store-spends`. Aajki keeps the prize balance; Hubble runs the store/orders. |

---

## 10. Shows, Push, Feedback, Misc

| Endpoint | Status | Purpose |
|----------|--------|---------|
| `GET /v2/shows/{slug}` | ⚠️ (400 needs valid `slug`) | Show pages (e.g. Bigg Boss). |
| `POST /v2/push/subscribe` · `POST /v2/push/permission` | ❓ | Push subscription / permission state. |
| `POST /v2/push/updateDeviceToken` (also seen as `/api/v2/push/updateDeviceToken`) | ❓ | Update FCM device token. |
| `POST /v2/feedback` | ❓ | Submit feedback (from stories). |
| `GET/POST /api/kv-store` | ❓ | Client key-value store (on `api.getkalki.com`). |
| `GET /api/surveys/?token=…` | ❓ | Surveys (opened in a WebView). |
| `GET /v1/daily-stories` · `POST /v1/logs` · `POST /v1/metrics` | ❓ | Legacy/telemetry on `api.getkalki.com`. |

---

## 11. Third-party services (not Aajki's backend)

- **PostHog** — product analytics. Headers `X-POSTHOG-DISTINCT-ID`, `X-POSTHOG-SESSION-ID`.
- **AppsFlyer** — ad attribution.
- **Firebase (FCM)** — push notifications.
- **Hubble / Gullak Technologies** — gift-card store (see §9).

---

## Notes for building your own backend

1. **Response style:** return the resource directly on `/v2/*`; keep the `{code,http_status,
   message,error,issues?,request_id}` error envelope so the existing client parses failures.
2. **Auth:** issue a Bearer token from `otp/verify` (and the social routes); gate every `/me/*`,
   `/rewards/*`, `/polls/me/*`, `/polls/saves`, `/hubble/*` route on it. New users get a
   short-lived `x-kalki-signup-token` until the DOB step completes.
3. **Money in paise**, **IDs are prefixed ULIDs**, **lists are cursor-paginated** with `next_cursor`.
4. **Realtime** (`markets/stream`, `hubble/session`) is SSE, not WebSocket.
5. The **vote/like/comment** request bodies above are inferred — capture a real request (or
   decompile the Hermes functions) before finalizing them.
