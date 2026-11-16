"""Aajki backend (FastAPI) — serves the same API the frontend expects, from its own seed
data. No calls to any external service. Also serves the sentiment admin portal.

Run locally:   uvicorn main:app --reload --port 8000
Point the frontend at it with VITE_API_BASE=http://localhost:8000
"""
from __future__ import annotations

import base64
import hmac
import os
import secrets
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse

import seed
import sentiment as sent
from admin import render_admin

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

app = FastAPI(title="Aajki API", version="0.1.0")

# The frontend calls this backend cross-origin (different domain on Vercel), so allow it.
# Auth is a Bearer token in a header (no cookies), so a wildcard origin is safe here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)


def _not_found(msg="Not found."):
    return JSONResponse(
        {"code": "NOT_FOUND", "http_status": 404, "message": msg,
         "error": {"code": "NOT_FOUND", "message": msg}}, status_code=404)


# --- Health & config -----------------------------------------------------------------------

@app.get("/healthz")
def healthz():
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat(), "polls": len(seed.POLLS)}


@app.get("/v2/app-config")
def app_config():
    return seed.APP_CONFIG


# --- Polls ---------------------------------------------------------------------------------

@app.get("/v2/polls/home")
def polls_home():
    return {
        "topics": seed.TOPICS,
        "open_topic_ids": [t["id"] for t in seed.TOPICS],
        "daily_set": None,
        "onboarding": None,
        "balance": None,
        "daily_bonus_earned": False,
        "goal": {"label": "Vote on 10 polls today", "current": 3, "target": 10},
        "stories": [],
        "user_stories": [],
        "daily_remaining": 7,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/v2/polls/feed")
def polls_feed(cursor: str | None = None, category: str | None = None):
    ids = seed.ALL_POLL_IDS
    page_size = 12
    start = 0
    if cursor:
        try:
            start = int(base64.urlsafe_b64decode(cursor.encode()).decode())
        except Exception:
            start = 0
    page = ids[start:start + page_size]
    nxt = start + page_size
    next_cursor = base64.urlsafe_b64encode(str(nxt).encode()).decode() if nxt < len(ids) else None
    return {
        "items": [{"type": "poll", "poll": seed.POLLS[pid]} for pid in page],
        "next_cursor": next_cursor,
        "category": "trending",
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/v2/polls/topics")
def polls_topics():
    return {"items": seed.TOPICS}


@app.get("/v2/polls/topics/{topic_id}")
def polls_topic(topic_id: str):
    topic = next((t for t in seed.TOPICS if t["id"] == topic_id), None)
    if not topic:
        return _not_found("Topic not found.")
    poll_ids = seed._TOPIC_POLLS.get(topic_id, [])
    polls = [seed.POLLS[pid] for pid in poll_ids]
    return {**topic, "polls": polls, "answered_polls": [], "stories": [],
            "group_picks": [], "trivia": [], "sequence": [{"kind": "poll", "id": pid} for pid in poll_ids],
            "curated": None, "leaderboard": None}


@app.get("/v2/polls/{poll_id}")
def poll_detail(poll_id: str):
    poll = seed.POLLS.get(poll_id)
    if not poll:
        return _not_found("Poll not found.")
    return poll


@app.get("/v2/polls/{poll_id}/comments")
def poll_comments(poll_id: str):
    return {"items": seed.comments_for(poll_id), "next_cursor": None}


# --- Stories -------------------------------------------------------------------------------

@app.get("/v2/stories/daily")
def stories_daily(cursor: str | None = None):
    return {"edition": datetime.now(timezone.utc).date().isoformat(),
            "stories": seed.STORIES, "next_cursor": None}


# --- Leaderboards --------------------------------------------------------------------------

@app.get("/v2/leaderboards")
def leaderboards():
    return {
        "boards": seed.BOARDS,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "copy": {"subtitle": "Vote daily to climb the board and win gift cards."},
        "headline_monthly_paise": 4000000,
        "today_pool_paise": sum(b["campaign_pool_paise"] for b in seed.BOARDS) // 4,
    }


@app.get("/v2/leaderboards/{board_id}")
def leaderboard(board_id: str):
    board = next((b for b in seed.BOARDS if b["id"] == board_id), None)
    if not board:
        return _not_found("Board not found.")
    return {"board": board, "frequencies": board["frequencies"], "served": board["served"],
            "me_status": None, "server_time": datetime.now(timezone.utc).isoformat(),
            "recent_wins": board["recent_wins"]}


# --- Auth (mock: no real SMS; any 6-digit code works) --------------------------------------

_TOKENS: dict[str, dict] = {}


@app.post("/v2/auth/otp/send")
async def otp_send(req: Request):
    body = await _json(req)
    phone = (body or {}).get("phone", "")
    # No SMS is sent; this is a self-contained demo backend. Code is always "000000".
    return {"ok": True, "message": "Use code 000000 (demo backend).", "phone": phone}


@app.post("/v2/auth/otp/verify")
async def otp_verify(req: Request):
    body = await _json(req)
    phone = (body or {}).get("phone", "")
    code = str((body or {}).get("code", ""))
    if not code.isdigit() or len(code) < 4:
        return JSONResponse({"code": "VALIDATION", "http_status": 400,
                             "message": "Enter the 6-digit code (000000 in demo)."}, status_code=400)
    token = secrets.token_urlsafe(24)
    _TOKENS[token] = {"phone": phone or "+910000000000",
                      "id": "usr_" + token[:10], "created": datetime.now(timezone.utc).isoformat()}
    return {"token": token, "is_new": False}


def _auth_user(req: Request):
    h = req.headers.get("authorization", "")
    if h.startswith("Bearer "):
        return _TOKENS.get(h[7:])
    return None


@app.get("/v2/me")
def me(request: Request):
    u = _auth_user(request)
    if not u:
        return JSONResponse({"code": "UNAUTHORIZED", "http_status": 401,
                             "message": "Sign in to continue."}, status_code=401)
    return {"id": u["id"], "display_name": "Demo Player", "handle": "demo",
            "phone": u["phone"], "avatar": None}


@app.get("/v2/me/wallet")
def wallet(request: Request):
    u = _auth_user(request)
    if not u:
        return JSONResponse({"code": "UNAUTHORIZED", "http_status": 401,
                             "message": "Sign in to continue."}, status_code=401)
    return {"balance": 240, "entries": [
        {"title": "Daily bonus", "amount": 50, "kind": "bonus"},
        {"title": "Poll reward", "amount": 5, "kind": "reward"},
        {"title": "Welcome coins", "amount": 100, "kind": "signup"},
    ]}


# --- Sentiment admin (backend-only; Basic Auth) --------------------------------------------

def _check_admin(request: Request) -> Response | None:
    host = (request.headers.get("host") or "").split(":")[0]
    is_local = host in ("localhost", "127.0.0.1")
    if not ADMIN_PASSWORD:
        if is_local:
            return None
        return PlainTextResponse(
            "Admin portal disabled: set the ADMIN_PASSWORD environment variable to enable it.",
            status_code=503)
    header = request.headers.get("authorization", "")
    if header.startswith("Basic "):
        try:
            user, _, pw = base64.b64decode(header[6:]).decode().partition(":")
            if hmac.compare_digest(user, ADMIN_USER) and hmac.compare_digest(pw, ADMIN_PASSWORD):
                return None
        except Exception:
            pass
    return PlainTextResponse("Authentication required.", status_code=401,
                             headers={"WWW-Authenticate": 'Basic realm="Aajki Admin"'})


def _sentiment_model():
    return sent.analyze_set(list(seed.POLLS.values()))


@app.get("/api/admin/sentiment")
def admin_sentiment(request: Request):
    guard = _check_admin(request)
    if guard is not None:
        return guard
    return _sentiment_model()


@app.get("/admin", response_class=HTMLResponse)
def admin_portal(request: Request):
    guard = _check_admin(request)
    if guard is not None:
        return guard
    return render_admin(_sentiment_model())


async def _json(req: Request):
    try:
        return await req.json()
    except Exception:
        return {}
