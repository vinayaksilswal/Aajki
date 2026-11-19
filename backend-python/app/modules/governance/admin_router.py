"""Admin panel routes (server-rendered). All routes sit behind admin_guard."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select

from app.db import SessionLocal, session_scope
from app.errors import AppError
from app.ids import new_id
from app.modules.debate import service as debate
from app.modules.forecasts import service as forecasts
from app.modules.forecasts.models import CATEGORIES, Question, Topic
from app.modules.governance import admin_views as views
from app.modules.governance.admin_auth import admin_guard
from app.modules.identity import service as identity
from app.modules.news import service as news
from app.modules.sentiment import service as sentiment

router = APIRouter(dependencies=[Depends(admin_guard)], include_in_schema=False)

# Fixed flash messages, selected by code (never reflect user-supplied text).
FLASH = {"created": "Draft saved. Complete the resolution terms, then publish.",
         "saved": "Changes saved.", "published": "Published.", "unpublished": "Moved back to draft.",
         "paused": "Paused. Calls are not accepted until you resume.", "resumed": "Resumed.",
         "voided": "Voided.", "deleted": "Draft deleted.", "refreshed": "Headlines refreshed.",
         "drafted": "Draft created from the headline. Rewrite it as a checkable question.",
         "updated": "Updated."}
EDITABLE_AFTER_PUBLISH = ("description", "image_url", "topic_id", "election_sensitive", "trending")


def _flash(request: Request) -> str:
    return FLASH.get(request.query_params.get("ok", ""), "")


def _go(path: str, code: str) -> RedirectResponse:
    return RedirectResponse(f"{path}?ok={code}", status_code=303)


# ------------------------------------------------------------------ form <-> values

def _parse_form(form, topic_ids: set[str]) -> tuple[dict, dict]:
    errors: dict[str, str] = {}
    opens = views.parse_local_input(form.get("opens_at"))
    closes = views.parse_local_input(form.get("closes_at"))
    if opens == "invalid":
        errors["opens_at"], opens = "Pick a date and time.", None
    if closes == "invalid":
        errors["closes_at"], closes = "Pick a date and time.", None

    def text(name):
        return (form.get(name) or "").strip() or None

    topic = form.get("topic_id") or None
    data = {
        "title": (form.get("title") or "").strip(),
        "category": form.get("category"),
        "outcomes": forecasts.binary_outcomes(form.get("outcome_yes"), form.get("outcome_no")),
        "description": text("description"), "image_url": text("image_url"),
        "topic_id": topic if topic in topic_ids else None,
        "opens_at": opens, "closes_at": closes,
        "resolution_source_url": text("resolution_source_url"),
        "resolution_rule": text("resolution_rule"),
        "election_sensitive": form.get("election_sensitive") == "1",
        "trending": form.get("trending") == "1",
    }
    return data, errors


def _values_from_form(form) -> dict:
    keys = ("title", "category", "outcome_yes", "outcome_no", "description", "image_url", "topic_id",
            "resolution_source_url", "resolution_rule")
    v = {k: form.get(k) or "" for k in keys}
    v.update(opens_at_input=form.get("opens_at") or "", closes_at_input=form.get("closes_at") or "",
             election_sensitive=form.get("election_sensitive") == "1",
             trending=form.get("trending") == "1")
    return v


def _values_from_question(q: Question) -> dict:
    outcomes = {o["key"]: o["label"] for o in q.outcomes or []}
    return {"title": q.title, "category": q.category, "outcome_yes": outcomes.get("yes", "Yes"),
            "outcome_no": outcomes.get("no", "No"), "description": q.description,
            "image_url": q.image_url, "topic_id": q.topic_id,
            "opens_at_input": views.to_local_input(q.opens_at),
            "closes_at_input": views.to_local_input(q.closes_at),
            "resolution_source_url": q.resolution_source_url, "resolution_rule": q.resolution_rule,
            "election_sensitive": q.election_sensitive, "trending": q.trending,
            "source_headline": q.source_headline, "source_link": q.source_link,
            "_submit": "Save draft" if q.status == "draft" else "Save changes"}


def _blank_values() -> dict:
    return {"category": "elections", "outcome_yes": "Yes", "outcome_no": "No", "_submit": "Save draft"}


# ------------------------------------------------------------------ pages

@router.get("/admin")
def admin_root():
    return RedirectResponse("/admin/dashboard", status_code=307)


@router.get("/admin/dashboard", response_class=HTMLResponse)
def dashboard():
    with SessionLocal() as s:
        k = {**forecasts.counts(s), **identity.counts(s), **debate.counts(s)}
        model = sentiment.model(s)
    return views.page_dashboard(k, model)


def _questions_page(s, values: dict, errors: dict, flash: str = "", status: int = 200) -> HTMLResponse:
    return HTMLResponse(views.page_questions(forecasts.admin_rows(s), forecasts.topics(s),
                                             values, errors, flash), status_code=status)


@router.get("/admin/questions", response_class=HTMLResponse)
def questions(request: Request):
    with SessionLocal() as s:
        return _questions_page(s, _blank_values(), {}, _flash(request))


@router.post("/admin/questions")
async def question_create(request: Request):
    form = await request.form()
    with SessionLocal() as s:
        topic_ids = {t.id for t in forecasts.topics(s)}
    data, errors = _parse_form(form, topic_ids)
    if not errors:
        try:
            with session_scope() as s:
                q = forecasts.create_draft(s, data)
                qid = q.id
            sentiment.clear_cache()
            return _go(f"/admin/questions/{qid}", "created")
        except AppError as exc:
            errors = exc.details if isinstance(exc.details, dict) else {"title": exc.message}
    with SessionLocal() as s:
        return _questions_page(s, {**_values_from_form(form), "_submit": "Save draft"}, errors,
                               "Fix the highlighted fields.", status=422)


def _question_page(s, q: Question, values: dict | None = None, errors: dict | None = None,
                   flash: str = "", status: int = 200) -> HTMLResponse:
    return HTMLResponse(views.page_question(q.id, forecasts.effective_status(q), forecasts.topics(s),
                                            values or _values_from_question(q), errors or {}, flash),
                        status_code=status)


@router.get("/admin/questions/{qid}", response_class=HTMLResponse)
def question_view(qid: str, request: Request):
    with SessionLocal() as s:
        return _question_page(s, forecasts.get(s, qid), flash=_flash(request))


@router.post("/admin/questions/{qid}")
async def question_update(qid: str, request: Request):
    form = await request.form()
    with SessionLocal() as s:
        topic_ids = {t.id for t in forecasts.topics(s)}
        current = forecasts.get(s, qid)
        is_draft = current.status == "draft"
    data, errors = _parse_form(form, topic_ids)
    if not is_draft:  # locked fields aren't (and can't be) changed from the form
        data = {k: v for k, v in data.items() if k in EDITABLE_AFTER_PUBLISH}
        errors = {}
    if not errors:
        try:
            with session_scope() as s:
                forecasts.update(s, forecasts.get(s, qid), data)
            sentiment.clear_cache()
            return _go(f"/admin/questions/{qid}", "saved")
        except AppError as exc:
            errors = exc.details if isinstance(exc.details, dict) else {"title": exc.message}
    with SessionLocal() as s:
        q = forecasts.get(s, qid)
        values = {**_values_from_question(q), **(_values_from_form(form) if is_draft else {})}
        return _question_page(s, q, values, errors, "Fix the highlighted fields.", status=422)


ACTION_FLASH = {"publish": "published", "unpublish": "unpublished", "pause": "paused",
                "resume": "resumed", "void": "voided"}


@router.post("/admin/questions/{qid}/transition")
async def question_transition(qid: str, request: Request):
    action = (await request.form()).get("action", "")
    try:
        with session_scope() as s:
            forecasts.transition(s, forecasts.get(s, qid), action)
        sentiment.clear_cache()
        return _go(f"/admin/questions/{qid}", ACTION_FLASH.get(action, "updated"))
    except AppError as exc:
        if exc.status == 404:
            raise
        with SessionLocal() as s:
            errors = exc.details if isinstance(exc.details, dict) else {}
            return _question_page(s, forecasts.get(s, qid), errors=errors, flash=exc.message,
                                  status=exc.status)


@router.post("/admin/questions/{qid}/delete")
def question_delete(qid: str):
    try:
        with session_scope() as s:
            forecasts.delete_draft(s, forecasts.get(s, qid))
    except AppError as exc:
        if exc.status == 404:
            raise
        with SessionLocal() as s:
            return _question_page(s, forecasts.get(s, qid), flash=exc.message, status=exc.status)
    return _go("/admin/questions", "deleted")


# ------------------------------------------------------------------ news

@router.get("/admin/news", response_class=HTMLResponse)
def news_page(request: Request):
    with SessionLocal() as s:
        return views.page_news(news.admin_recent(s), _flash(request))


@router.post("/admin/news/refresh")
def news_refresh():
    with session_scope() as s:
        result = news.refresh(s)
    if result["errors"] and not result["fetched"]:
        with SessionLocal() as s:
            return HTMLResponse(views.page_news(news.admin_recent(s), "Couldn't reach the news "
                                                "source right now. Try again in a minute."), status_code=502)
    return _go("/admin/news", "refreshed")


@router.post("/admin/news/{item_id}/draft")
def news_draft(item_id: str):
    with session_scope() as s:
        qid = news.draft_from_headline(s, item_id).id
    return _go(f"/admin/questions/{qid}", "drafted")


@router.post("/admin/news/{item_id}/hide")
async def news_hide(item_id: str, request: Request):
    hidden = (await request.form()).get("hidden") == "1"
    with session_scope() as s:
        news.set_hidden(s, item_id, hidden)
    return _go("/admin/news", "updated")


# ------------------------------------------------------------------ topics

@router.get("/admin/topics", response_class=HTMLResponse)
def topics_page(request: Request):
    with SessionLocal() as s:
        topics = forecasts.topics(s)
        counts = dict(s.execute(select(Question.topic_id, func.count())
                                .where(Question.topic_id.is_not(None)).group_by(Question.topic_id)).all())
        return views.page_topics(topics, counts, _flash(request))


@router.post("/admin/topics")
async def topic_create(request: Request):
    f = await request.form()
    title = (f.get("title") or "").strip()[:200]
    category = f.get("category") if f.get("category") in CATEGORIES else "community"
    if title:
        with session_scope() as s:
            tid = new_id("tpc")
            s.add(Topic(id=tid, slug=forecasts._slug(title, tid), title=title, category=category,
                        short_label=(f.get("short_label") or "").strip()[:120] or None,
                        blurb=(f.get("blurb") or "").strip() or None))
    return _go("/admin/topics", "updated")


@router.post("/admin/topics/{topic_id}/delete")
def topic_delete(topic_id: str):
    with session_scope() as s:
        t = s.get(Topic, topic_id)
        if t:
            for q in s.scalars(select(Question).where(Question.topic_id == topic_id)).all():
                q.topic_id = None
            s.delete(t)
    return _go("/admin/topics", "updated")


# ------------------------------------------------------------------ comments / audience

@router.get("/admin/comments", response_class=HTMLResponse)
def comments_page(request: Request):
    with SessionLocal() as s:
        ids = debate.question_ids(s)
        titles = dict(s.execute(select(Question.id, Question.title).where(Question.id.in_(ids))).all()) if ids else {}
        return views.page_comments(debate.admin_list(s, titles), _flash(request))


@router.post("/admin/comments/{comment_id}/hide")
async def comment_hide(comment_id: int, request: Request):
    hidden = (await request.form()).get("hidden") == "1"
    with session_scope() as s:
        debate.set_hidden(s, comment_id, hidden)
    return _go("/admin/comments", "updated")


@router.post("/admin/comments/{comment_id}/delete")
def comment_delete(comment_id: int):
    with session_scope() as s:
        debate.delete(s, comment_id)
    return _go("/admin/comments", "updated")


@router.get("/admin/audience", response_class=HTMLResponse)
def audience_page(request: Request):
    with SessionLocal() as s:
        users = identity.admin_list(s, forecasts.calls_by_user(s))
        return views.page_audience(users, identity.counts(s), _flash(request))


@router.post("/admin/audience/{user_id}/block")
async def user_block(user_id: str, request: Request):
    blocked = (await request.form()).get("blocked") == "1"
    with session_scope() as s:
        identity.set_blocked(s, user_id, blocked)
    return _go("/admin/audience", "updated")


# ------------------------------------------------------------------ sentiment

@router.get("/admin/sentiment", response_class=HTMLResponse)
def sentiment_page():
    with SessionLocal() as s:
        return views.page_sentiment(sentiment.model(s))


@router.get("/api/admin/sentiment")
def sentiment_json():
    with SessionLocal() as s:
        return sentiment.model(s)
