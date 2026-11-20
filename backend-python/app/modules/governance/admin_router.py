"""Admin panel routes (server-rendered).

Every page needs a signed-in admin who completed two-factor sign-in (admin_context), and each
action checks the admin's role (auth.require). Every change writes an audit record in the
same transaction as the change.
"""
from __future__ import annotations

import base64
import csv
import io
import json
from datetime import datetime, timedelta

import segno
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy import func, select

from app.clock import now_utc
from app.config import get_settings
from app.db import SessionLocal, session_scope
from app.errors import AppError
from app.ids import new_id
from app.modules.compliance import service as compliance
from app.modules.debate import service as debate
from app.modules.engagement import service as engagement
from app.modules.forecasts import participation
from app.modules.forecasts import service as forecasts
from app.modules.forecasts.models import CATEGORIES, Question, Topic
from app.modules.governance import admin_views as views
from app.modules.governance import auth, ops
from app.modules.governance.auth import AdminContext, admin_context, audit, require
from app.modules.governance.models import AdminUser
from app.modules.identity import service as identity
from app.modules.ledger import service as ledger
from app.modules.news import service as news
from app.modules.policy import service as policy
from app.modules.sentiment import public as public_sentiment
from app.modules.sentiment import service as sentiment
from app.modules.standing import service as standing
from app.modules.standing.models import BADGE_RULES
from app.ratelimit import client_ip, hit

router = APIRouter(include_in_schema=False)

# Fixed flash messages, selected by code (never reflect user-supplied text).
FLASH = {"created": "Draft saved. Complete the resolution terms, then publish.",
         "saved": "Changes saved.", "published": "Published.", "unpublished": "Moved back to draft.",
         "paused": "Paused. Calls are not accepted until you resume.", "resumed": "Resumed.",
         "voided": "Voided. Every committed point was returned.", "deleted": "Draft deleted.",
         "refreshed": "Headlines refreshed.",
         "drafted": "Draft created from the headline. Rewrite it as a checkable question.",
         "updated": "Updated.", "proposed": "Result submitted. A different admin must approve it.",
         "approved": "Result approved. Points were released.", "rejected": "Proposal rejected.",
         "approved_void": "Approved. The rules required a void, so every committed point was returned.",
         "password": "Password changed.", "enrolled": "Two-factor sign-in is on.",
         "added": "Added."}
EDITABLE_AFTER_PUBLISH = ("description", "image_url", "topic_id", "election_sensitive",
                          "election_state", "trending")


def _flash(request: Request) -> str:
    return FLASH.get(request.query_params.get("ok", ""), "")


def _go(path: str, code: str) -> RedirectResponse:
    sep = "&" if "?" in path else "?"
    return RedirectResponse(f"{path}{sep}ok={code}", status_code=303)


def _details(exc: AppError) -> dict:
    return exc.details if isinstance(exc.details, dict) else {}


def _admin_names(s) -> dict[str, str]:
    return dict(s.execute(select(AdminUser.id, AdminUser.name)).all())


def _titles(s, ids: list[str]) -> dict[str, str]:
    if not ids:
        return {}
    return dict(s.execute(select(Question.id, Question.title).where(Question.id.in_(ids))).all())


def _cookie(response, token: str) -> None:
    response.set_cookie(auth.COOKIE, token, httponly=True, samesite="strict", path="/admin",
                        secure=not get_settings().is_dev,
                        max_age=get_settings().admin_session_hours * 3600)


# ================================================================== sign-in

@router.get("/admin/login", response_class=HTMLResponse)
def login_page(request: Request):
    with SessionLocal() as s:
        bootstrap = auth.admin_count(s) == 0
    return views.page_login(_flash(request), bootstrap)


@router.post("/admin/login")
async def login(request: Request):
    if not auth._same_origin(request):
        return HTMLResponse(views.page_login("Blocked: sign in from the admin panel."), status_code=403)
    form = await request.form()
    ip = client_ip(request)
    try:
        hit("admin-login", ip, 20, 900, "Too many sign-in attempts. Wait 15 minutes.")
        with session_scope() as s:
            admin = auth.authenticate_password(s, form.get("email", ""), form.get("password", ""), ip)
            token = auth.start_session(s, admin, ip)
            target = "/admin/2fa" if admin.totp_enabled else "/admin/2fa/setup"
    except AppError as exc:
        with SessionLocal() as s:
            return HTMLResponse(views.page_login(exc.message, auth.admin_count(s) == 0), status_code=exc.status)
    resp = RedirectResponse(target, status_code=303)
    _cookie(resp, token)
    return resp


def _pending(request: Request):
    """The signed-in but not yet two-factor-verified session."""
    with SessionLocal() as s:
        found = auth.session_for(s, request.cookies.get(auth.COOKIE))
        if found:
            s.expunge(found[0])
            s.expunge(found[1])
        return found


def _qr(uri: str) -> str:
    buf = io.BytesIO()
    segno.make(uri, error="m").save(buf, kind="svg", scale=5, border=2)
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()


@router.get("/admin/2fa/setup", response_class=HTMLResponse)
def totp_setup_page(request: Request):
    found = _pending(request)
    if not found:
        return RedirectResponse("/admin/login", status_code=303)
    sess, admin = found
    if admin.totp_enabled:
        return RedirectResponse("/admin/2fa", status_code=303)
    with session_scope() as s:
        a = s.get(AdminUser, admin.id)
        if not a.totp_secret:
            a.totp_secret = auth.new_totp_secret()
        secret = a.totp_secret
        uri = auth.totp_uri(a, secret)
    return views.page_totp_setup(secret, _qr(uri))


@router.post("/admin/2fa/setup", response_class=HTMLResponse)
async def totp_setup(request: Request):
    found = _pending(request)
    if not found or not auth._same_origin(request):
        return RedirectResponse("/admin/login", status_code=303)
    sess, admin = found
    code = (await request.form()).get("code", "")
    hit("admin-2fa", admin.id, 10, 900, "Too many attempts. Wait 15 minutes.")
    with session_scope() as s:
        a = s.get(AdminUser, admin.id)
        if a.totp_enabled or not a.totp_secret or not auth.verify_totp(a, a.totp_secret, code):
            secret, uri = a.totp_secret, auth.totp_uri(a, a.totp_secret or "")
            ok = False
        else:
            a.totp_enabled, a.last_login_at = True, now_utc()
            row = auth.session_for(s, request.cookies.get(auth.COOKIE))
            row[0].verified = True
            audit(s, None, "admin.2fa_enrolled", "admin", a.id, None, None, ip=client_ip(request), actor=a)
            ok = True
    if not ok:
        return HTMLResponse(views.page_totp_setup(secret, _qr(uri), "That code didn't match. Try the newest code."),
                            status_code=422)
    return _go("/admin/dashboard", "enrolled")


@router.get("/admin/2fa", response_class=HTMLResponse)
def totp_page(request: Request):
    found = _pending(request)
    if not found:
        return RedirectResponse("/admin/login", status_code=303)
    if not found[1].totp_enabled:
        return RedirectResponse("/admin/2fa/setup", status_code=303)
    return views.page_totp()


@router.post("/admin/2fa", response_class=HTMLResponse)
async def totp_verify(request: Request):
    found = _pending(request)
    if not found or not auth._same_origin(request):
        return RedirectResponse("/admin/login", status_code=303)
    _, admin = found
    code = (await request.form()).get("code", "")
    try:
        hit("admin-2fa", admin.id, 10, 900, "Too many attempts. Wait 15 minutes.")
    except AppError as exc:
        return HTMLResponse(views.page_totp(exc.message), status_code=429)
    with session_scope() as s:
        a = s.get(AdminUser, admin.id)
        ok = a.totp_enabled and auth.verify_totp(a, a.totp_secret, code)
        if ok:
            row = auth.session_for(s, request.cookies.get(auth.COOKIE))
            row[0].verified = True
            a.last_login_at = now_utc()
            audit(s, None, "admin.sign_in", "admin", a.id, None, None, ip=client_ip(request), actor=a)
    if not ok:
        return HTMLResponse(views.page_totp("That code didn't match. Try the newest code."), status_code=422)
    return RedirectResponse("/admin/dashboard", status_code=303)


@router.post("/admin/logout")
def logout(request: Request):
    if auth._same_origin(request):
        with session_scope() as s:
            auth.revoke(s, request.cookies.get(auth.COOKIE))
    resp = RedirectResponse("/admin/login", status_code=303)
    resp.delete_cookie(auth.COOKIE, path="/admin")
    return resp


@router.get("/admin/password", response_class=HTMLResponse)
def password_page(request: Request, ctx: AdminContext = Depends(admin_context)):
    return views.page_password(ctx, ctx.admin.must_change_password, {}, _flash(request))


@router.post("/admin/password", response_class=HTMLResponse)
async def password_change(request: Request, ctx: AdminContext = Depends(admin_context)):
    form = await request.form()
    errors = {}
    with session_scope() as s:
        a = s.get(AdminUser, ctx.admin.id)
        try:
            auth._hasher.verify(a.password_hash, form.get("current", ""))
        except Exception:
            errors["current"] = "That isn't your current password."
        problem = auth.password_problem(form.get("new", ""))
        if problem:
            errors["new"] = problem
        if not errors:
            a.password_hash, a.must_change_password = auth.hash_password(form["new"]), False
            audit(s, ctx, "admin.password_changed", "admin", a.id, None, None)
    if errors:
        return HTMLResponse(views.page_password(ctx, ctx.admin.must_change_password, errors), status_code=422)
    return _go("/admin/dashboard", "password")


# ================================================================== dashboard

@router.get("/admin")
def admin_root():
    return RedirectResponse("/admin/dashboard", status_code=307)


@router.get("/admin/dashboard", response_class=HTMLResponse)
def dashboard(ctx: AdminContext = Depends(admin_context)):
    with SessionLocal() as s:
        k = {**forecasts.counts(s), **identity.counts(s), **debate.counts(s), **compliance.counts(s),
             "dau": identity.activity(s)["dau"],
             "pending_settlements": len([p for p in participation.history(s) if p.status == "proposed"]),
             "open_disputes": len(participation.disputes(s, "open"))}
        model = sentiment.model(s)
    return views.page_dashboard(ctx, k, model.get("overall_mood", 0) or 0, model.get("total_polls", 0))


# ================================================================== questions

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
    state = form.get("election_state") or None
    from app.regions import STATES
    data = {
        "title": (form.get("title") or "").strip(), "category": form.get("category"),
        "outcomes": forecasts.binary_outcomes(form.get("outcome_yes"), form.get("outcome_no")),
        "description": text("description"), "image_url": text("image_url"),
        "topic_id": topic if topic in topic_ids else None, "opens_at": opens, "closes_at": closes,
        "resolution_source_url": text("resolution_source_url"), "resolution_rule": text("resolution_rule"),
        "election_sensitive": form.get("election_sensitive") == "1",
        "election_state": state if state in STATES else None,
        "trending": form.get("trending") == "1",
    }
    return data, errors


def _values_from_form(form) -> dict:
    keys = ("title", "category", "outcome_yes", "outcome_no", "description", "image_url", "topic_id",
            "resolution_source_url", "resolution_rule", "election_state")
    v = {k: form.get(k) or "" for k in keys}
    v.update(opens_at_input=form.get("opens_at") or "", closes_at_input=form.get("closes_at") or "",
             election_sensitive=form.get("election_sensitive") == "1", trending=form.get("trending") == "1")
    return v


def _values_from_question(q: Question) -> dict:
    outcomes = {o["key"]: o["label"] for o in q.outcomes or []}
    return {"title": q.title, "category": q.category, "outcome_yes": outcomes.get("yes", "Yes"),
            "outcome_no": outcomes.get("no", "No"), "description": q.description, "image_url": q.image_url,
            "topic_id": q.topic_id, "opens_at_input": views.to_local_input(q.opens_at),
            "closes_at_input": views.to_local_input(q.closes_at),
            "resolution_source_url": q.resolution_source_url, "resolution_rule": q.resolution_rule,
            "election_sensitive": q.election_sensitive, "election_state": q.election_state,
            "trending": q.trending, "source_headline": q.source_headline, "source_link": q.source_link,
            "_submit": "Save draft" if q.status == "draft" else "Save changes"}


def q_snapshot(q: Question) -> dict:
    return {"title": q.title, "category": q.category, "status": q.status, "outcomes": q.outcomes,
            "opens_at": forecasts.iso(q.opens_at), "closes_at": forecasts.iso(q.closes_at),
            "resolution_source_url": q.resolution_source_url, "resolution_rule": q.resolution_rule,
            "election_sensitive": q.election_sensitive, "election_state": q.election_state,
            "trending": q.trending, "description": q.description}


def _blank_values() -> dict:
    return {"category": "elections", "outcome_yes": "Yes", "outcome_no": "No", "_submit": "Save draft"}


def _questions_page(ctx, s, values, errors, flash="", status=200):
    return HTMLResponse(views.page_questions(ctx, forecasts.admin_rows(s), forecasts.topics(s), values, errors, flash),
                        status_code=status)


@router.get("/admin/questions", response_class=HTMLResponse)
def questions(request: Request, ctx: AdminContext = Depends(admin_context)):
    with SessionLocal() as s:
        return _questions_page(ctx, s, _blank_values(), {}, _flash(request))


@router.post("/admin/questions")
async def question_create(request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "questions.write")
    form = await request.form()
    with SessionLocal() as s:
        topic_ids = {t.id for t in forecasts.topics(s)}
    data, errors = _parse_form(form, topic_ids)
    if not errors:
        try:
            with session_scope() as s:
                q = forecasts.create_draft(s, data)
                audit(s, ctx, "question.create", "question", q.id, None, q_snapshot(q))
                qid = q.id
            sentiment.clear_cache()
            return _go(f"/admin/questions/{qid}", "created")
        except AppError as exc:
            errors = _details(exc) or {"title": exc.message}
    with SessionLocal() as s:
        return _questions_page(ctx, s, {**_values_from_form(form), "_submit": "Save draft"}, errors,
                               "Fix the highlighted fields.", status=422)


def _question_page(ctx, s, q: Question, values=None, errors=None, flash="", status=200) -> HTMLResponse:
    st = forecasts.effective_status(q)
    panel = ""
    if st != "draft":
        history = participation.history(s, q.id)
        disputes = [d for d in participation.disputes(s, None) if d.question_id == q.id]
        panel = views.settlement_panel(ctx, q.id, st, q.outcomes or [], participation.outcome_totals(s, q.id),
                                       history, disputes, _admin_names(s), errors or {})
    return HTMLResponse(views.page_question(ctx, q.id, st, forecasts.topics(s), values or _values_from_question(q),
                                            errors or {}, panel, flash), status_code=status)


@router.get("/admin/questions/{qid}", response_class=HTMLResponse)
def question_view(qid: str, request: Request, ctx: AdminContext = Depends(admin_context)):
    with SessionLocal() as s:
        return _question_page(ctx, s, forecasts.get(s, qid), flash=_flash(request))


@router.post("/admin/questions/{qid}")
async def question_update(qid: str, request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "questions.write")
    form = await request.form()
    with SessionLocal() as s:
        topic_ids = {t.id for t in forecasts.topics(s)}
        is_draft = forecasts.get(s, qid).status == "draft"
    data, errors = _parse_form(form, topic_ids)
    if not is_draft:  # locked fields aren't (and can't be) changed from the form
        data = {k: v for k, v in data.items() if k in EDITABLE_AFTER_PUBLISH}
        errors = {}
    if not errors:
        try:
            with session_scope() as s:
                q = forecasts.get(s, qid)
                before = q_snapshot(q)
                forecasts.update(s, q, data)
                audit(s, ctx, "question.update", "question", qid, before, q_snapshot(q))
            sentiment.clear_cache()
            return _go(f"/admin/questions/{qid}", "saved")
        except AppError as exc:
            errors = _details(exc) or {"title": exc.message}
    with SessionLocal() as s:
        q = forecasts.get(s, qid)
        values = {**_values_from_question(q), **(_values_from_form(form) if is_draft else {})}
        return _question_page(ctx, s, q, values, errors, "Fix the highlighted fields.", status=422)


ACTION_FLASH = {"publish": "published", "unpublish": "unpublished", "pause": "paused",
                "resume": "resumed", "void": "voided"}


@router.post("/admin/questions/{qid}/transition")
async def question_transition(qid: str, request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "questions.write")
    action = (await request.form()).get("action", "")
    try:
        with session_scope() as s:
            q = forecasts.get(s, qid)
            before = q_snapshot(q)
            forecasts.transition(s, q, action)
            audit(s, ctx, f"question.{action}", "question", qid, before, q_snapshot(q))
        sentiment.clear_cache()
        public_sentiment.clear_cache()
        return _go(f"/admin/questions/{qid}", ACTION_FLASH.get(action, "updated"))
    except AppError as exc:
        if exc.status == 404:
            raise
        with SessionLocal() as s:
            return _question_page(ctx, s, forecasts.get(s, qid), errors=_details(exc), flash=exc.message,
                                  status=exc.status)


@router.post("/admin/questions/{qid}/delete")
def question_delete(qid: str, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "questions.write")
    try:
        with session_scope() as s:
            q = forecasts.get(s, qid)
            before = q_snapshot(q)
            forecasts.delete_draft(s, q)
            audit(s, ctx, "question.delete", "question", qid, before, None)
    except AppError as exc:
        if exc.status == 404:
            raise
        with SessionLocal() as s:
            return _question_page(ctx, s, forecasts.get(s, qid), flash=exc.message, status=exc.status)
    return _go("/admin/questions", "deleted")


# ================================================================== settlement and disputes

def s_snapshot(p) -> dict:
    return {"question_id": p.question_id, "result": p.result, "status": p.status,
            "source_url": p.source_url, "note": p.note, "applied_result": p.applied_result,
            "applied_reason": p.applied_reason, "corrects_id": p.corrects_id}


@router.post("/admin/questions/{qid}/settlement")
async def settlement_propose(qid: str, request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "settlement.propose")
    form = await request.form()
    try:
        with session_scope() as s:
            p = participation.propose(s, forecasts.get(s, qid), form.get("result", ""),
                                      (form.get("source_url") or "").strip() or None, form.get("note"), ctx.admin.id)
            audit(s, ctx, "settlement.propose", "settlement", p.id, None, s_snapshot(p))
        return _go(f"/admin/questions/{qid}", "proposed")
    except AppError as exc:
        if exc.status == 404:
            raise
        with SessionLocal() as s:
            return _question_page(ctx, s, forecasts.get(s, qid), errors=_details(exc), flash=exc.message,
                                  status=exc.status)


async def _decide(sid: str, request: Request, ctx: AdminContext, approve: bool):
    require(ctx, "settlement.approve")
    note = (await request.form()).get("note", "")
    try:
        with session_scope() as s:
            p = participation.get_settlement(s, sid)
            qid, before = p.question_id, s_snapshot(p)
            if approve:
                participation.approve(s, p, ctx.admin.id, note)
            else:
                participation.reject(s, p, ctx.admin.id, note)
            audit(s, ctx, "settlement.approve" if approve else "settlement.reject", "settlement", sid,
                  before, s_snapshot(p))
        sentiment.clear_cache()
        public_sentiment.clear_cache()
        code = "rejected" if not approve else ("approved_void" if p.applied_result == "void" else "approved")
        return _go(f"/admin/questions/{qid}", code)
    except AppError as exc:
        if exc.status == 404:
            raise
        with SessionLocal() as s:
            p = participation.get_settlement(s, sid)
            return _question_page(ctx, s, forecasts.get(s, p.question_id), flash=exc.message, status=exc.status)


@router.post("/admin/settlements/{sid}/approve")
async def settlement_approve(sid: str, request: Request, ctx: AdminContext = Depends(admin_context)):
    return await _decide(sid, request, ctx, True)


@router.post("/admin/settlements/{sid}/reject")
async def settlement_reject(sid: str, request: Request, ctx: AdminContext = Depends(admin_context)):
    return await _decide(sid, request, ctx, False)


@router.get("/admin/settlements", response_class=HTMLResponse)
def settlements_page(request: Request, ctx: AdminContext = Depends(admin_context)):
    with SessionLocal() as s:
        now = now_utc()
        awaiting_qs = s.scalars(select(Question).where(Question.status.in_(("published", "paused")),
                                                       Question.closes_at <= now)
                                .order_by(Question.closes_at)).all()
        totals = forecasts.participation(s, [q.id for q in awaiting_qs])
        awaiting = [(q, sum(v["calls"] for v in totals.get(q.id, {}).values())) for q in awaiting_qs]
        history = participation.history(s)
        pending = [p for p in history if p.status == "proposed"]
        recent = [p for p in history if p.status != "proposed"][:50]
        titles = _titles(s, list({p.question_id for p in history}))
        return views.page_settlements(ctx, awaiting, pending, recent, titles, _admin_names(s), _flash(request))


@router.get("/admin/disputes", response_class=HTMLResponse)
def disputes_page(request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "disputes.review")
    with SessionLocal() as s:
        rows = participation.disputes(s, None)
        rows.sort(key=lambda d: (d.status != "open", d.created_at))
        return views.page_disputes(ctx, rows[:200], _titles(s, list({d.question_id for d in rows})), _flash(request))


@router.post("/admin/disputes/{did}")
async def dispute_decide(did: str, request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "disputes.review")
    form = await request.form()
    try:
        with session_scope() as s:
            d = participation.get_dispute(s, did)
            participation.decide_dispute(s, d, ctx.admin.id, form.get("decision") == "uphold", form.get("note", ""))
            audit(s, ctx, f"dispute.{d.status}", "dispute", did, {"status": "open"},
                  {"status": d.status, "note": d.decision_note})
    except AppError as exc:
        if exc.status == 404:
            raise
        with SessionLocal() as s:
            rows = participation.disputes(s, None)
            return HTMLResponse(views.page_disputes(ctx, rows, _titles(s, [d.question_id for d in rows]), exc.message),
                                status_code=exc.status)
    return _go("/admin/disputes", "updated")


# ================================================================== news / topics / quiz

def _news_page(ctx, s, errors=None, flash="", status=200):
    return HTMLResponse(views.page_news(ctx, news.admin_recent(s), errors or {}, flash), status_code=status)


@router.get("/admin/news", response_class=HTMLResponse)
def news_page(request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "news.write")
    with SessionLocal() as s:
        return _news_page(ctx, s, flash=_flash(request))


@router.post("/admin/news")
async def news_add(request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "news.write")
    f = await request.form()
    try:
        with session_scope() as s:
            item = news.add_manual(s, f.get("title"), f.get("source"), f.get("link"), f.get("category"))
            audit(s, ctx, "news.add", "headline", item.id, None, {"title": item.title, "source": item.source})
    except AppError as exc:
        with SessionLocal() as s:
            return _news_page(ctx, s, _details(exc), exc.message, exc.status)
    return _go("/admin/news", "added")


@router.post("/admin/news/refresh")
def news_refresh(ctx: AdminContext = Depends(admin_context)):
    require(ctx, "news.write")
    with session_scope() as s:
        result = news.refresh(s)
        audit(s, ctx, "news.refresh", None, None, None, {"fetched": result["fetched"], "new": result["new"]})
    if result["errors"] and not result["fetched"]:
        with SessionLocal() as s:
            return _news_page(ctx, s, flash="Couldn't reach the news source right now. Try again in a minute.", status=502)
    return _go("/admin/news", "refreshed")


@router.post("/admin/news/{item_id}/draft")
def news_draft(item_id: str, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "questions.write")
    with session_scope() as s:
        q = news.draft_from_headline(s, item_id)
        audit(s, ctx, "question.draft_from_headline", "question", q.id, None, {"headline": item_id})
        qid = q.id
    return _go(f"/admin/questions/{qid}", "drafted")


@router.post("/admin/news/{item_id}/hide")
async def news_hide(item_id: str, request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "news.write")
    hidden = (await request.form()).get("hidden") == "1"
    with session_scope() as s:
        news.set_hidden(s, item_id, hidden)
        audit(s, ctx, "news.hide" if hidden else "news.show", "headline", item_id, None, {"hidden": hidden})
    return _go("/admin/news", "updated")


@router.post("/admin/news/{item_id}/link")
async def news_link(item_id: str, request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "news.write")
    qid = ((await request.form()).get("question_id") or "").strip()[:40] or None
    try:
        with session_scope() as s:
            item = news.link_question(s, item_id, qid)
            audit(s, ctx, "news.link", "headline", item_id, None, {"question_id": item.question_id})
    except AppError as exc:
        with SessionLocal() as s:
            return _news_page(ctx, s, flash=exc.message, status=exc.status)
    return _go("/admin/news", "updated")


@router.get("/admin/topics", response_class=HTMLResponse)
def topics_page(request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "topics.write")
    with SessionLocal() as s:
        counts = dict(s.execute(select(Question.topic_id, func.count()).where(Question.topic_id.is_not(None))
                                .group_by(Question.topic_id)).all())
        return views.page_topics(ctx, forecasts.topics(s), counts, _flash(request))


@router.post("/admin/topics")
async def topic_create(request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "topics.write")
    f = await request.form()
    title = (f.get("title") or "").strip()[:200]
    category = f.get("category") if f.get("category") in CATEGORIES else "community"
    if title:
        with session_scope() as s:
            tid = new_id("tpc")
            s.add(Topic(id=tid, slug=forecasts._slug(title, tid), title=title, category=category,
                        short_label=(f.get("short_label") or "").strip()[:120] or None,
                        blurb=(f.get("blurb") or "").strip() or None))
            audit(s, ctx, "topic.create", "topic", tid, None, {"title": title, "category": category})
    return _go("/admin/topics", "updated")


@router.post("/admin/topics/{topic_id}/delete")
def topic_delete(topic_id: str, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "topics.write")
    with session_scope() as s:
        t = s.get(Topic, topic_id)
        if t:
            for q in s.scalars(select(Question).where(Question.topic_id == topic_id)).all():
                q.topic_id = None
            audit(s, ctx, "topic.delete", "topic", topic_id, {"title": t.title}, None)
            s.delete(t)
    return _go("/admin/topics", "updated")


def _quiz_form(form) -> dict:
    day = None
    try:
        day = datetime.strptime(form.get("day", ""), "%Y-%m-%d").date()
    except ValueError:
        pass
    return {"day": day, "question": (form.get("question") or "").strip(),
            "options": [{"key": k, "label": (form.get(f"option_{k}") or "").strip()} for k in ("a", "b", "c", "d")],
            "correct_key": form.get("correct_key"), "explanation": form.get("explanation"),
            "active": form.get("active") == "1"}


def _quiz_page(ctx, s, values, errors, editing, flash="", status=200):
    return HTMLResponse(views.page_quiz(ctx, engagement.quizzes(s), values, errors, editing, flash), status_code=status)


@router.get("/admin/quiz", response_class=HTMLResponse)
def quiz_page(request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "quiz.write")
    edit = request.query_params.get("edit")
    with SessionLocal() as s:
        values = {"day": (now_utc() + timedelta(days=1)).date().isoformat(), "active": True}
        if edit:
            q = engagement.get_quiz(s, edit)
            values = {**engagement.quiz_snapshot(q), "explanation": q.explanation or ""}
        return _quiz_page(ctx, s, values, {}, edit, _flash(request))


async def _quiz_save(request: Request, ctx: AdminContext, quiz_id: str | None):
    require(ctx, "quiz.write")
    form = await request.form()
    d = _quiz_form(form)
    try:
        with session_scope() as s:
            before = engagement.quiz_snapshot(engagement.get_quiz(s, quiz_id)) if quiz_id else None
            q = engagement.save_quiz(s, d, ctx.admin.id, quiz_id)
            audit(s, ctx, "quiz.update" if quiz_id else "quiz.create", "quiz", q.id, before, engagement.quiz_snapshot(q))
    except AppError as exc:
        values = {**d, "day": d["day"].isoformat() if d["day"] else ""}
        with SessionLocal() as s:
            return _quiz_page(ctx, s, values, _details(exc), quiz_id, exc.message, exc.status)
    return _go("/admin/quiz", "saved")


@router.post("/admin/quiz")
async def quiz_create(request: Request, ctx: AdminContext = Depends(admin_context)):
    return await _quiz_save(request, ctx, None)


@router.post("/admin/quiz/{quiz_id}")
async def quiz_update(quiz_id: str, request: Request, ctx: AdminContext = Depends(admin_context)):
    return await _quiz_save(request, ctx, quiz_id)


# ================================================================== moderation / users

def _moderation_page(ctx, s, flash="", status=200):
    return HTMLResponse(views.page_moderation(ctx, debate.queue(s, identity.profiles, _titles), debate.recent_actions(s),
                                              debate.REASON_CODES, debate.REPORT_REASONS, _admin_names(s), flash),
                        status_code=status)


@router.get("/admin/moderation", response_class=HTMLResponse)
def moderation_page(request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "moderation.act")
    with SessionLocal() as s:
        return _moderation_page(ctx, s, _flash(request))


@router.post("/admin/moderation/{comment_id}")
async def moderate(comment_id: int, request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "moderation.act")
    f = await request.form()
    try:
        with session_scope() as s:
            from app.modules.debate.models import Comment
            c = s.get(Comment, comment_id)
            before = debate.comment_snapshot(c) if c else None
            c = debate.moderate_comment(s, comment_id, f.get("action", ""), f.get("reason_code", ""),
                                        ctx.admin.id, f.get("note"))
            audit(s, ctx, f"moderation.{f.get('action')}", "comment", comment_id, before,
                  {**debate.comment_snapshot(c), "reason_code": f.get("reason_code")})
    except AppError as exc:
        if exc.status == 404:
            raise
        with SessionLocal() as s:
            return _moderation_page(ctx, s, exc.message, exc.status)
    return _go("/admin/moderation", "updated")


@router.get("/admin/users", response_class=HTMLResponse)
def users_page(request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "users.read")
    q = (request.query_params.get("q") or "").strip()
    with SessionLocal() as s:
        users = identity.admin_list(s, forecasts.calls_by_user(s), q or None)
        return views.page_users(ctx, users, identity.counts(s), q, _flash(request))


@router.get("/admin/users/{user_id}", response_class=HTMLResponse)
def user_page(user_id: str, request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "users.read")
    with SessionLocal() as s:
        u = identity.get(s, user_id)
        return views.page_user(ctx, u, identity.restriction(u), debate.user_history(s, u.id),
                               debate.REASON_CODES, _flash(request))


@router.post("/admin/users/{user_id}/sanction")
async def user_sanction(user_id: str, request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "users.sanction")
    f = await request.form()
    action, reason = f.get("action", ""), f.get("reason_code", "")
    try:
        days = int(f.get("days") or 7)
    except ValueError:
        days = 7
    try:
        with session_scope() as s:
            u = identity.get(s, user_id)
            before = identity.snapshot(u)
            if action == "warn":
                identity.warn(s, user_id)
            elif action == "suspend":
                identity.suspend(s, user_id, days)
            elif action == "unsuspend":
                identity.unsuspend(s, user_id)
            elif action in ("block", "unblock"):
                identity.set_blocked(s, user_id, action == "block")
            else:
                raise AppError(400, "BAD_REQUEST", "Unknown action.")
            debate.log_user_action(s, user_id, action, reason, ctx.admin.id, f.get("note"))
            audit(s, ctx, f"user.{action}", "user", user_id, before, {**identity.snapshot(u), "reason_code": reason})
    except AppError as exc:
        if exc.status == 404:
            raise
        with SessionLocal() as s:
            u = identity.get(s, user_id)
            return HTMLResponse(views.page_user(ctx, u, identity.restriction(u), debate.user_history(s, u.id),
                                                debate.REASON_CODES, exc.message), status_code=exc.status)
    return _go(f"/admin/users/{user_id}", "updated")


# ================================================================== grievances

@router.get("/admin/grievances", response_class=HTMLResponse)
def grievances_page(request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "grievances.handle")
    status = request.query_params.get("status", "active")
    with SessionLocal() as s:
        rows = compliance.admin_queue(s, status or None)
        return views.page_grievances(ctx, rows, status, compliance.GRIEVANCE_CATEGORIES, _flash(request))


def _grievance_page(ctx, s, gid: str, flash="", status=200):
    g = compliance.get(s, gid)
    user = s.get(identity.User, g.user_id)
    activity = None
    if compliance.has_review_consent(s, g.user_id, g.id):
        activity = {"calls": participation.my_calls(s, g.user_id, None),
                    "ledger": ledger.history(s, g.user_id, None, 50)["items"]}
    return HTMLResponse(views.page_grievance(ctx, g, compliance.notes_for(s, gid), user,
                                             compliance.GRIEVANCE_CATEGORIES, activity, _admin_names(s), flash),
                        status_code=status)


@router.get("/admin/grievances/{gid}", response_class=HTMLResponse)
def grievance_page(gid: str, request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "grievances.handle")
    with session_scope() as s:
        g = compliance.get(s, gid)
        if compliance.has_review_consent(s, g.user_id, g.id):
            audit(s, ctx, "grievance.activity_viewed", "grievance", gid, None, {"user_id": g.user_id})
        return _grievance_page(ctx, s, gid, _flash(request))


@router.post("/admin/grievances/{gid}")
async def grievance_update(gid: str, request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "grievances.handle")
    f = await request.form()
    try:
        with session_scope() as s:
            g = compliance.get(s, gid)
            before = compliance.snapshot(g)
            compliance.update(s, g, ctx.admin.id, f.get("status", ""), f.get("note", ""), f.get("visible") == "1",
                              f.get("resolution"))
            audit(s, ctx, "grievance.update", "grievance", gid, before, compliance.snapshot(g))
    except AppError as exc:
        if exc.status == 404:
            raise
        with SessionLocal() as s:
            return _grievance_page(ctx, s, gid, exc.message, exc.status)
    return _go(f"/admin/grievances/{gid}", "updated")


# ================================================================== policy / economy / badges

def _policy_page(ctx, s, errors=None, flash="", status=200):
    return HTMLResponse(views.page_policy(ctx, policy.values(s), policy.FEATURES, compliance.periods(s), now_utc(),
                                          errors or {}, flash), status_code=status)


@router.get("/admin/policy", response_class=HTMLResponse)
def policy_page(request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "policy.manage")
    with SessionLocal() as s:
        return _policy_page(ctx, s, flash=_flash(request))


@router.post("/admin/policy/features/{feature}")
async def policy_feature(feature: str, request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "policy.manage")
    f = await request.form()
    try:
        with session_scope() as s:
            before = policy.values(s)["features"].get(feature)
            policy.set_feature(s, feature, f.get("on") == "1", f.getlist("off_states"), ctx.admin.id)
            audit(s, ctx, "policy.feature", "feature", feature, before, policy.values(s)["features"][feature])
    except AppError as exc:
        with SessionLocal() as s:
            return _policy_page(ctx, s, flash=exc.message, status=exc.status)
    return _go("/admin/policy", "saved")


@router.post("/admin/policy/quiet")
async def policy_quiet(request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "policy.manage")
    f = await request.form()
    starts, ends = views.parse_local_input(f.get("starts_at")), views.parse_local_input(f.get("ends_at"))
    states = f.getlist("states")
    if "*" in states:
        states = ["*"]
    try:
        if starts == "invalid" or ends == "invalid":
            raise AppError(422, "VALIDATION_FAILED", "Pick valid start and end times.")
        with session_scope() as s:
            p = compliance.add_period(s, f.get("label", ""), states, starts, ends, f.get("hide_sentiment") == "1",
                                      ctx.admin.id)
            audit(s, ctx, "policy.quiet_period_add", "quiet_period", p.id, None, compliance.period_snapshot(p))
        public_sentiment.clear_cache()
    except AppError as exc:
        with SessionLocal() as s:
            return _policy_page(ctx, s, flash=exc.message, status=exc.status)
    return _go("/admin/policy", "saved")


@router.post("/admin/policy/quiet/{pid}/end")
def policy_quiet_end(pid: str, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "policy.manage")
    with session_scope() as s:
        p = compliance.end_period(s, pid)
        before = compliance.period_snapshot(p)
        audit(s, ctx, "policy.quiet_period_end", "quiet_period", pid, before, compliance.period_snapshot(p))
    public_sentiment.clear_cache()
    return _go("/admin/policy", "saved")


@router.get("/admin/economy", response_class=HTMLResponse)
def economy_page(request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "economy.manage")
    from app.clock import ist_day_start
    with SessionLocal() as s:
        return views.page_economy(ctx, ledger.economy(s, ist_day_start()), policy.daily_reward_cap(s), _flash(request))


@router.post("/admin/economy/cap")
async def economy_cap(request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "economy.manage")
    try:
        cap = int((await request.form()).get("cap", ""))
        with session_scope() as s:
            before = policy.daily_reward_cap(s)
            policy.set_daily_reward_cap(s, cap, ctx.admin.id)
            audit(s, ctx, "policy.daily_reward_cap", "policy", "daily_reward_cap", {"cap": before}, {"cap": cap})
    except (ValueError, AppError):
        return _go("/admin/economy", "updated")
    return _go("/admin/economy", "saved")


def _badges_page(ctx, s, errors=None, editing=None, flash="", status=200):
    return HTMLResponse(views.page_badges(ctx, policy.rank_tiers(s), standing.badges_catalogue(s, True), BADGE_RULES,
                                          errors or {}, editing, flash), status_code=status)


@router.get("/admin/badges", response_class=HTMLResponse)
def badges_page(request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "economy.manage")
    edit = request.query_params.get("edit")
    with SessionLocal() as s:
        editing = None
        if edit:
            from app.modules.standing.models import Badge
            b = s.get(Badge, edit)
            if b:
                editing = {"id": b.id, "name": b.name, "emoji": b.emoji, "description": b.description,
                           "rule": b.rule, "threshold": b.threshold, "active": b.active, "sort": b.sort}
        return _badges_page(ctx, s, editing=editing, flash=_flash(request))


@router.post("/admin/badges/tiers")
async def badges_tiers(request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "economy.manage")
    f = await request.form()
    try:
        mins = [int(f.get(f"min_{i}", "")) for i in range(len(policy.DEFAULT_TIERS))]
        with session_scope() as s:
            before = [t["min"] for t in policy.rank_tiers(s)]
            policy.set_rank_thresholds(s, mins, ctx.admin.id)
            audit(s, ctx, "policy.rank_thresholds", "policy", "rank_tiers", {"mins": before}, {"mins": mins})
    except ValueError:
        with SessionLocal() as s:
            return _badges_page(ctx, s, {"tiers": "Use whole numbers."}, status=422)
    except AppError as exc:
        with SessionLocal() as s:
            return _badges_page(ctx, s, {"tiers": exc.message}, status=exc.status)
    return _go("/admin/badges", "saved")


async def _badge_save(request: Request, ctx: AdminContext, badge_id: str | None):
    require(ctx, "economy.manage")
    f = await request.form()
    try:
        threshold = int(f.get("threshold") or 0)
    except ValueError:
        threshold = 0
    d = {"name": (f.get("name") or "").strip(), "emoji": f.get("emoji"), "description": f.get("description"),
         "rule": f.get("rule"), "threshold": threshold, "active": f.get("active") == "1",
         "sort": int(f.get("sort") or 0) if (f.get("sort") or "0").lstrip("-").isdigit() else 0}
    try:
        with session_scope() as s:
            b = standing.save_badge(s, d, badge_id)
            audit(s, ctx, "badge.update" if badge_id else "badge.create", "badge", b.id, None, standing.badge_snapshot(b))
    except AppError as exc:
        with SessionLocal() as s:
            return _badges_page(ctx, s, _details(exc), {**d, "id": badge_id}, exc.message, exc.status)
    return _go("/admin/badges", "saved")


@router.post("/admin/badges")
async def badge_create(request: Request, ctx: AdminContext = Depends(admin_context)):
    return await _badge_save(request, ctx, None)


@router.post("/admin/badges/{badge_id}")
async def badge_update(badge_id: str, request: Request, ctx: AdminContext = Depends(admin_context)):
    return await _badge_save(request, ctx, badge_id)


# ================================================================== operations / sentiment

@router.get("/admin/ops", response_class=HTMLResponse)
def ops_page(ctx: AdminContext = Depends(admin_context)):
    require(ctx, "ops.read")
    with SessionLocal() as s:
        quiet = compliance.quiet_states(s, sentiment=True)
        return views.page_ops(ctx, identity.activity(s), ops.funnel(s), ops.retention(s),
                              participation.volume_by_day(s), ops.error_trend(s),
                              public_sentiment.health(s, quiet), debate.handling_stats(s, views.days_ago(7)))


@router.get("/admin/sentiment", response_class=HTMLResponse)
def sentiment_page(ctx: AdminContext = Depends(admin_context)):
    with SessionLocal() as s:
        quiet = compliance.quiet_states(s, sentiment=True)
        return views.page_sentiment(ctx, sentiment.model(s), public_sentiment.dashboard(s, quiet))


# ================================================================== admin accounts / audit

def _admins_page(ctx, s, errors=None, values=None, flash="", status=200):
    return HTMLResponse(views.page_admins(ctx, auth.admins(s), auth.ROLES, errors or {}, values or {}, flash),
                        status_code=status)


@router.get("/admin/admins", response_class=HTMLResponse)
def admins_page(request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "admins.manage")
    with SessionLocal() as s:
        return _admins_page(ctx, s, flash=_flash(request))


@router.post("/admin/admins")
async def admin_create(request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "admins.manage")
    f = await request.form()
    values = {"name": f.get("name", ""), "email": f.get("email", ""), "roles": f.getlist("roles")}
    try:
        with session_scope() as s:
            a = auth.create_admin(s, values["email"], values["name"], values["roles"], f.get("password", ""))
            audit(s, ctx, "admin.create", "admin", a.id, None, auth.admin_snapshot(a))
    except AppError as exc:
        errors = _details(exc)
        if not errors:
            errors = {"roles": exc.message}
        else:
            errors = {k: (exc.message if v in ("invalid", "taken", "required") else v) for k, v in errors.items()}
        with SessionLocal() as s:
            return _admins_page(ctx, s, errors, values, exc.message, exc.status)
    return _go("/admin/admins", "added")


@router.post("/admin/admins/{admin_id}")
async def admin_update(admin_id: str, request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "admins.manage")
    f = await request.form()
    try:
        with session_scope() as s:
            a = auth.get_admin(s, admin_id)
            before = auth.admin_snapshot(a)
            roles = auth.validate_roles(f.getlist("roles"))
            active = f.get("active") == "1"
            if ("super_admin" not in roles or not active):
                auth.ensure_other_super_admin(s, a)
            a.roles, a.active = roles, active
            if not active:
                auth.revoke_all(s, a.id)
            audit(s, ctx, "admin.update", "admin", a.id, before, auth.admin_snapshot(a))
    except AppError as exc:
        if exc.status == 404:
            raise
        with SessionLocal() as s:
            return _admins_page(ctx, s, flash=exc.message, status=exc.status)
    return _go("/admin/admins", "saved")


@router.post("/admin/admins/{admin_id}/reset-2fa")
def admin_reset_2fa(admin_id: str, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "admins.manage")
    with session_scope() as s:
        a = auth.get_admin(s, admin_id)
        before = auth.admin_snapshot(a)
        a.totp_secret, a.totp_enabled, a.totp_last_step = None, False, None
        auth.revoke_all(s, a.id)
        audit(s, ctx, "admin.reset_2fa", "admin", a.id, before, auth.admin_snapshot(a))
    return _go("/admin/admins", "saved")


@router.get("/admin/audit", response_class=HTMLResponse)
def audit_page(request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "audit.read")
    action = (request.query_params.get("action") or "").strip()[:40]
    with SessionLocal() as s:
        return views.page_audit(ctx, auth.audit_rows(s, action or None), action, ctx.can("audit.export"))


@router.get("/admin/audit.csv")
def audit_export(request: Request, ctx: AdminContext = Depends(admin_context)):
    require(ctx, "audit.export")
    action = (request.query_params.get("action") or "").strip()[:40]
    with session_scope() as s:
        rows = auth.audit_rows(s, action or None, limit=50_000)
        audit(s, ctx, "audit.export", None, None, None, {"filter": action, "rows": len(rows)})
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "created_at", "admin_email", "roles", "action", "target_type", "target_id",
                    "before", "after", "ip", "correlation_id"])
        def cell(v):
            # Spreadsheet formula injection guard.
            v = "" if v is None else str(v)
            return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v

        for r in rows:
            w.writerow([cell(x) for x in [r.id, forecasts.iso(r.created_at), r.admin_email, " ".join(r.roles or []), r.action,
                        r.target_type, r.target_id, json.dumps(r.before, ensure_ascii=False) if r.before else "",
                        json.dumps(r.after, ensure_ascii=False) if r.after else "", r.ip, r.correlation_id]])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=audit-log.csv"})
