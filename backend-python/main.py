"""Aajki backend (FastAPI) — DB-backed API + an admin management console.

Reads/writes a real database (DATABASE_URL). The public API serves the app; the admin
console (/admin, Basic Auth) manages questions, topics, comments and the audience.

Run locally:   uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

import base64
import hmac
import os
import os.path as _osp
import secrets
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import time

import store
import sentiment as sent
import admin_console as console
import news

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

app = FastAPI(title="Aajki API", version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])

# Initialise schema + seed once (idempotent). Guarded so a transient DB blip is visible,
# not a silent import crash.
try:
    store.init_db()
except Exception as exc:  # pragma: no cover
    print("DB init warning:", exc)


@app.middleware("http")
async def _strip_proxy_prefix(request: Request, call_next):
    p = request.scope.get("path", "")
    if p.startswith("/api/aajki/"):
        request.scope["path"] = p[len("/api/aajki"):]
    return await call_next(request)


def _nf(msg="Not found."):
    return JSONResponse({"code": "NOT_FOUND", "http_status": 404, "message": msg,
                         "error": {"code": "NOT_FOUND", "message": msg}}, status_code=404)


# ============================ Public API ============================

@app.get("/healthz")
def healthz():
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat(), **store.admin_stats()}


@app.get("/v2/app-config")
def app_config():
    return {"min_supported_build": 1, "latest_build": 1, "store_urls": {"ios": "", "android": ""},
            "app_icon": None, "phone_step_required": True,
            "reward_frame": {"enabled": True, "coin_target": 500, "progress_suffix": "/500 Coins",
                             "title": "You hit 500 coins!"}}


@app.get("/v2/polls/home")
def polls_home():
    return store.home()


@app.get("/v2/polls/feed")
def polls_feed(cursor: str | None = None, category: str | None = None):
    return store.feed(cursor)


@app.get("/v2/polls/topics")
def polls_topics():
    return store.topics()


@app.get("/v2/polls/topics/{topic_id}")
def polls_topic(topic_id: str):
    return store.topic(topic_id) or _nf("Topic not found.")


@app.get("/v2/polls/{poll_id}")
def poll_detail(poll_id: str):
    return store.get_poll(poll_id) or _nf("Poll not found.")


@app.get("/v2/polls/{poll_id}/comments")
def poll_comments(poll_id: str):
    return store.poll_comments(poll_id)


@app.post("/v2/polls/{poll_id}/comments")
async def poll_comment_add(poll_id: str, request: Request):
    body = await _json(request)
    text = (body or {}).get("body") or (body or {}).get("text") or ""
    user = _auth_user(request)
    author = (body or {}).get("author") or "Guest"
    result = store.add_comment(poll_id, text, user_id=(user["id"] if user else None), author_name=author)
    if result is False:
        return JSONResponse({"code": "FORBIDDEN", "http_status": 403, "message": "Account blocked."}, status_code=403)
    if not result:
        return _nf("Poll not found or empty comment.")
    return result


@app.post("/v2/polls/{poll_id}/vote")
async def poll_vote(poll_id: str, request: Request):
    body = await _json(request)
    option = (body or {}).get("option_id") or (body or {}).get("option")
    user = _auth_user(request)
    if user and store.is_blocked(user["id"]):
        return JSONResponse({"code": "FORBIDDEN", "http_status": 403, "message": "Account blocked."}, status_code=403)
    if not option or not store.record_vote(poll_id, option, user["id"] if user else None):
        return _nf("Poll or option not found.")
    return store.get_poll(poll_id)


@app.get("/v2/stories/daily")
def stories_daily():
    return store.stories_daily()


@app.get("/v2/leaderboards")
def leaderboards():
    return store.leaderboards()


@app.get("/v2/leaderboards/{board_id}")
def leaderboard(board_id: str):
    return store.board(board_id) or _nf("Board not found.")


# --- auth (mock OTP; creates a real user row so the audience is real) ---
_TOKENS: dict[str, dict] = {}


@app.post("/v2/auth/otp/send")
async def otp_send(request: Request):
    body = await _json(request)
    return {"ok": True, "message": "Use code 000000 (demo backend).", "phone": (body or {}).get("phone", "")}


@app.post("/v2/auth/otp/verify")
async def otp_verify(request: Request):
    body = await _json(request)
    phone = (body or {}).get("phone", "") or "+910000000000"
    code = str((body or {}).get("code", ""))
    if not code.isdigit() or len(code) < 4:
        return JSONResponse({"code": "VALIDATION", "http_status": 400,
                             "message": "Enter the 6-digit code (000000 in demo)."}, status_code=400)
    token = secrets.token_urlsafe(24)
    uid = "usr_" + token[:12]
    store.ensure_user(uid, phone)
    _TOKENS[token] = {"id": uid, "phone": phone}
    return {"token": token, "is_new": False}


def _auth_user(request: Request):
    h = request.headers.get("authorization", "")
    return _TOKENS.get(h[7:]) if h.startswith("Bearer ") else None


@app.get("/v2/me")
def me(request: Request):
    u = _auth_user(request)
    if not u:
        return JSONResponse({"code": "UNAUTHORIZED", "http_status": 401, "message": "Sign in to continue."}, status_code=401)
    full = store.ensure_user(u["id"], u["phone"])
    return {"id": full["id"], "display_name": full["display_name"], "handle": full["handle"],
            "phone": full["phone"], "avatar": None}


@app.get("/v2/me/wallet")
def wallet(request: Request):
    u = _auth_user(request)
    if not u:
        return JSONResponse({"code": "UNAUTHORIZED", "http_status": 401, "message": "Sign in to continue."}, status_code=401)
    return store.wallet(u["id"])


# ============================ Admin console ============================

def admin_guard(request: Request):
    host = (request.headers.get("host") or "").split(":")[0]
    is_local = host in ("localhost", "127.0.0.1")
    if not ADMIN_PASSWORD:
        if is_local:
            return
        raise HTTPException(status_code=503, detail="Admin disabled: set ADMIN_PASSWORD.")
    header = request.headers.get("authorization", "")
    if header.startswith("Basic "):
        try:
            user, _, pw = base64.b64decode(header[6:]).decode().partition(":")
            if hmac.compare_digest(user, ADMIN_USER) and hmac.compare_digest(pw, ADMIN_PASSWORD):
                return
        except Exception:
            pass
    raise HTTPException(status_code=401, detail="Authentication required.",
                        headers={"WWW-Authenticate": 'Basic realm="Aajki Admin"'})


A = [Depends(admin_guard)]

# Cache the sentiment model briefly so repeated admin loads / real traffic don't re-scan
# every poll and vote on each request. Per-instance cache; fine for serverless.
_SENT_CACHE = {"at": 0.0, "model": None}
_SENT_TTL = float(os.environ.get("SENTIMENT_TTL_S", "60"))


def _sentiment_model():
    import time
    now = time.time()
    if _SENT_CACHE["model"] is None or now - _SENT_CACHE["at"] > _SENT_TTL:
        _SENT_CACHE["model"] = sent.analyze_set(store.all_polls_for_sentiment())
        _SENT_CACHE["at"] = now
    return _SENT_CACHE["model"]


@app.get("/admin", dependencies=A)
def admin_root():
    return RedirectResponse("/admin/dashboard", status_code=307)


@app.get("/admin/dashboard", response_class=HTMLResponse, dependencies=A)
def admin_dashboard():
    return console.page_dashboard(store.admin_stats(), _sentiment_model())


@app.get("/admin/questions", response_class=HTMLResponse, dependencies=A)
def admin_questions():
    return console.page_questions(store.admin_list_polls(), store.admin_list_topics(), store.admin_stats())


def _parse_options(form) -> tuple[str, list]:
    kind = form.get("display_kind", "binary")
    if kind == "multi":
        lines = [l.strip() for l in (form.get("options_text") or "").splitlines() if l.strip()]
        opts = [{"key": f"opt{i+1}", "label": lab, "emoji": None, "base_votes": 0} for i, lab in enumerate(lines)]
        if not opts:
            opts = [{"key": "opt1", "label": "Option 1", "emoji": None, "base_votes": 0}]
    else:
        opts = [{"key": "yes", "label": "Yes", "emoji": None, "base_votes": 0},
                {"key": "no", "label": "No", "emoji": None, "base_votes": 0}]
    return kind, opts


@app.post("/admin/questions/new", dependencies=A)
async def admin_question_new(request: Request):
    f = await request.form()
    kind, opts = _parse_options(f)
    store.admin_create_poll(
        question=f.get("question", "").strip(), category=f.get("category", "politics"),
        options=opts, image_url=(f.get("image_url") or None), topic_id=(f.get("topic_id") or None),
        display_kind=kind, trending=f.get("trending") == "1", is_prediction=f.get("is_prediction") == "1",
        reward_coins=int(f.get("reward_coins") or 5))
    return RedirectResponse("/admin/questions", status_code=303)


@app.get("/admin/questions/{poll_id}", response_class=HTMLResponse, dependencies=A)
def admin_question_edit(poll_id: str):
    p = store.admin_get_poll(poll_id)
    if not p:
        raise HTTPException(404, "Question not found")
    return console.page_edit_question(p, store.admin_list_topics(), store.admin_stats())


@app.post("/admin/questions/{poll_id}", dependencies=A)
async def admin_question_update(poll_id: str, request: Request):
    f = await request.form()
    kind, opts = _parse_options(f)
    store.admin_update_poll(
        poll_id, question=f.get("question", "").strip(), category=f.get("category"),
        image_url=(f.get("image_url") or None), topic_id=(f.get("topic_id") or None),
        display_kind=kind, options=opts, trending=f.get("trending") == "1",
        is_prediction=f.get("is_prediction") == "1", reward_coins=int(f.get("reward_coins") or 5))
    return RedirectResponse("/admin/questions", status_code=303)


@app.post("/admin/questions/{poll_id}/status", dependencies=A)
async def admin_question_status(poll_id: str, request: Request):
    f = await request.form()
    store.admin_set_status(poll_id, f.get("status", "open"))
    return RedirectResponse("/admin/questions", status_code=303)


@app.post("/admin/questions/{poll_id}/delete", dependencies=A)
def admin_question_delete(poll_id: str):
    store.admin_delete_poll(poll_id)
    return RedirectResponse("/admin/questions", status_code=303)


@app.get("/admin/topics", response_class=HTMLResponse, dependencies=A)
def admin_topics():
    return console.page_topics(store.admin_list_topics(), store.admin_stats())


@app.post("/admin/topics/new", dependencies=A)
async def admin_topic_new(request: Request):
    f = await request.form()
    store.admin_create_topic(title=f.get("title", "").strip(), category=f.get("category", "politics"),
                             short_label=(f.get("short_label") or None), blurb=(f.get("blurb") or None),
                             image_url=(f.get("image_url") or None))
    return RedirectResponse("/admin/topics", status_code=303)


@app.post("/admin/topics/{topic_id}/delete", dependencies=A)
def admin_topic_delete(topic_id: str):
    store.admin_delete_topic(topic_id)
    return RedirectResponse("/admin/topics", status_code=303)


@app.get("/admin/comments", response_class=HTMLResponse, dependencies=A)
def admin_comments():
    return console.page_comments(store.admin_list_comments(), store.admin_stats())


@app.post("/admin/comments/{comment_id}/hide", dependencies=A)
async def admin_comment_hide(comment_id: int, request: Request):
    f = await request.form()
    store.admin_set_comment_hidden(comment_id, f.get("hidden") == "1")
    return RedirectResponse("/admin/comments", status_code=303)


@app.post("/admin/comments/{comment_id}/delete", dependencies=A)
def admin_comment_delete(comment_id: int):
    store.admin_delete_comment(comment_id)
    return RedirectResponse("/admin/comments", status_code=303)


@app.get("/admin/audience", response_class=HTMLResponse, dependencies=A)
def admin_audience():
    return console.page_audience(store.admin_list_users(), store.admin_stats())


@app.post("/admin/audience/{user_id}/block", dependencies=A)
async def admin_user_block(user_id: str, request: Request):
    f = await request.form()
    store.admin_set_user_blocked(user_id, f.get("blocked") == "1")
    return RedirectResponse("/admin/audience", status_code=303)


@app.get("/admin/sentiment", response_class=HTMLResponse, dependencies=A)
def admin_sentiment_page():
    return console.page_sentiment(_sentiment_model(), store.admin_stats())


@app.get("/api/admin/sentiment", dependencies=A)
def admin_sentiment_json():
    return _sentiment_model()


# --- News ingestion (Google News -> reaction polls) ---
_NEWS_CACHE = {"at": 0.0, "data": None}
_NEWS_TTL = float(os.environ.get("NEWS_TTL_S", "300"))


def _fetch_news():
    now = time.time()
    if _NEWS_CACHE["data"] is None or now - _NEWS_CACHE["at"] > _NEWS_TTL:
        _NEWS_CACHE["data"] = news.fetch_all(limit_per_category=8)
        _NEWS_CACHE["at"] = now
    return _NEWS_CACHE["data"]


@app.get("/admin/news", response_class=HTMLResponse, dependencies=A)
def admin_news():
    data = _fetch_news()
    titles = [it["title"] for items in data.values() for it in items]
    imported = store.existing_questions(titles)
    return console.page_news(data, imported, store.admin_stats())


@app.post("/admin/news/publish", dependencies=A)
async def admin_news_publish(request: Request):
    f = await request.form()
    item = {"title": f.get("title", ""), "category": f.get("category", "politics"),
            "source": f.get("source", "Google News"), "link": f.get("link", "")}
    if item["title"]:
        store.create_poll_if_new(news.to_poll(item))
    return RedirectResponse("/admin/news", status_code=303)


def _import_latest() -> int:
    data = news.fetch_all(limit_per_category=8)
    _NEWS_CACHE["data"], _NEWS_CACHE["at"] = data, time.time()
    created = 0
    for items in data.values():
        for it in items:
            if store.create_poll_if_new(news.to_poll(it)):
                created += 1
    return created


@app.post("/admin/news/import", dependencies=A)
async def admin_news_import(request: Request):
    f = await request.form()
    cat = f.get("category", "all")
    if cat == "all":
        _import_latest()
    else:
        data = _fetch_news()
        for it in data.get(cat, []):
            store.create_poll_if_new(news.to_poll(it))
    return RedirectResponse("/admin/news", status_code=303)


# Hands-off auto-import for a scheduler (e.g. Vercel Cron). Protected by CRON_SECRET:
# Vercel sends `Authorization: Bearer $CRON_SECRET` with scheduled requests.
@app.get("/api/cron/news-import")
def cron_news_import(request: Request):
    secret = os.environ.get("CRON_SECRET", "")
    if not secret or request.headers.get("authorization") != f"Bearer {secret}":
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    created = _import_latest()
    return {"ok": True, "created": created, "at": datetime.now(timezone.utc).isoformat()}


async def _json(req: Request):
    try:
        return await req.json()
    except Exception:
        return {}


# Serve the built frontend from the same origin when ../dist exists (local single-server).
_DIST = _osp.join(_osp.dirname(__file__), "..", "dist")
if _osp.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
