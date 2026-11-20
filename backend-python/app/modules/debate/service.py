"""Debate: comments and replies, reports, blocks and the moderation queue (spec s.2, s.3;
SOW 2.7, 3.4).

- Comments are 1 to 140 characters, with one level of replies. Links are not allowed.
- Rate limits (enforced by the router): 20 comments per user per hour, 5 per question per hour.
- Three separate reports hold a comment out of view until a moderator reviews it.
- Report-handling target: 24 hours from the first open report.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.clock import aware, iso, now_utc
from app.errors import AppError, not_found
from app.modules.debate.models import Comment, CommentReport, ModerationAction, UserBlock

MAX_LEN = 140
HOLD_AFTER_REPORTS = 3
HANDLING_TARGET = timedelta(hours=24)
REPORT_REASONS = {"abuse": "Abuse or harassment", "hate": "Hate speech", "spam": "Spam",
                  "misinfo": "False information", "explicit": "Explicit or graphic",
                  "privacy": "Shares personal information", "other": "Something else"}
REASON_CODES = {"abuse": "Abuse or harassment", "hate": "Hate speech", "spam": "Spam or scam",
                "misinfo": "Misinformation", "explicit": "Explicit or graphic content",
                "privacy": "Personal information", "impersonation": "Impersonation",
                "election_period": "Election-period restriction (RP Act s.126)",
                "court_order": "Court or government order", "no_violation": "No violation found",
                "other": "Other policy breach"}
_LINK = re.compile(r"(https?://|www\.|\b[a-z0-9-]+\.(com|in|org|net|io|co|xyz|ly|me)\b)", re.IGNORECASE)


def _out(c: Comment, viewer_id: str | None, profiles: dict) -> dict:
    p = profiles.get(c.user_id or "", {})
    return {"id": c.id, "question_id": c.question_id, "parent_id": c.parent_id,
            "author": {"display_name": p.get("display_name", c.author_name), "avatar": p.get("avatar")},
            "body": c.body, "created_at": iso(c.created_at), "mine": bool(viewer_id and c.user_id == viewer_id)}


def post(s: Session, user_id: str, author_name: str, question_id: str, body: str,
         parent_id: int | None) -> Comment:
    body = " ".join((body or "").split())
    if not 1 <= len(body) <= MAX_LEN:
        raise AppError(422, "VALIDATION_FAILED", f"Write 1 to {MAX_LEN} characters.")
    if _LINK.search(body):
        raise AppError(422, "LINKS_NOT_ALLOWED", "Links aren't allowed in comments.")
    if parent_id is not None:
        parent = s.get(Comment, parent_id)
        if not parent or parent.question_id != question_id or parent.status != "visible":
            raise AppError(404, "NOT_FOUND", "That comment is no longer available.")
        if parent.parent_id is not None:
            parent_id = parent.parent_id  # replies stay one level deep
    c = Comment(question_id=question_id, parent_id=parent_id, user_id=user_id,
                author_name=author_name[:80], body=body, status="visible")
    s.add(c)
    s.flush()
    return c


def thread(s: Session, question_id: str, viewer_id: str | None, profiles_fn, limit: int = 30,
           before_id: int | None = None) -> dict:
    """Visible top-level comments, newest first, each with its visible replies (oldest first).
    Authors the viewer has blocked are left out."""
    blocked = blocked_by(s, viewer_id) if viewer_id else set()
    stmt = select(Comment).where(Comment.question_id == question_id, Comment.parent_id.is_(None),
                                 Comment.status == "visible")
    if blocked:
        stmt = stmt.where(or_(Comment.user_id.is_(None), Comment.user_id.not_in(blocked)))
    if before_id:
        stmt = stmt.where(Comment.id < before_id)
    tops = s.scalars(stmt.order_by(Comment.id.desc()).limit(limit + 1)).all()
    page, more = tops[:limit], len(tops) > limit
    replies: dict[int, list[Comment]] = {c.id: [] for c in page}
    if page:
        rstmt = select(Comment).where(Comment.parent_id.in_(list(replies)), Comment.status == "visible")
        if blocked:
            rstmt = rstmt.where(or_(Comment.user_id.is_(None), Comment.user_id.not_in(blocked)))
        for r in s.scalars(rstmt.order_by(Comment.id)).all():
            replies[r.parent_id].append(r)
    ids = {c.user_id for c in page} | {r.user_id for rs in replies.values() for r in rs}
    profiles = profiles_fn(s, [i for i in ids if i])
    total = s.scalar(select(func.count()).select_from(Comment).where(
        Comment.question_id == question_id, Comment.status == "visible")) or 0
    return {"items": [{**_out(c, viewer_id, profiles),
                       "replies": [_out(r, viewer_id, profiles) for r in replies[c.id][:50]]}
                      for c in page],
            "next_before": page[-1].id if more else None, "total": total}


def delete_own(s: Session, user_id: str, comment_id: int) -> None:
    c = s.get(Comment, comment_id)
    if not c or c.user_id != user_id or c.status == "deleted":
        raise not_found("Comment")
    c.status, c.body = "deleted", ""


def report(s: Session, reporter_id: str, comment_id: int, reason: str, note: str | None) -> None:
    if reason not in REPORT_REASONS:
        raise AppError(422, "VALIDATION_FAILED", "Choose a reason.")
    c = s.get(Comment, comment_id)
    if not c or c.status not in ("visible", "held"):
        raise not_found("Comment")
    if c.user_id == reporter_id:
        raise AppError(422, "VALIDATION_FAILED", "You can delete your own comment instead.")
    s.add(CommentReport(comment_id=c.id, reporter_id=reporter_id, reason=reason,
                        note=(note or "").strip()[:280] or None))
    try:
        s.flush()
    except IntegrityError:
        raise AppError(409, "ALREADY_REPORTED", "You've already reported this comment.")
    open_reports = s.scalar(select(func.count()).select_from(CommentReport).where(
        CommentReport.comment_id == c.id, CommentReport.status == "open")) or 0
    if open_reports >= HOLD_AFTER_REPORTS and c.status == "visible":
        c.status = "held"


def block(s: Session, blocker_id: str, blocked_id: str) -> None:
    if blocker_id == blocked_id:
        raise AppError(422, "VALIDATION_FAILED", "You can't block yourself.")
    if not s.get(UserBlock, (blocker_id, blocked_id)):
        s.add(UserBlock(blocker_id=blocker_id, blocked_id=blocked_id))


def unblock(s: Session, blocker_id: str, blocked_id: str) -> None:
    b = s.get(UserBlock, (blocker_id, blocked_id))
    if b:
        s.delete(b)


def blocked_by(s: Session, user_id: str) -> set[str]:
    return set(s.scalars(select(UserBlock.blocked_id).where(UserBlock.blocker_id == user_id)).all())


def author_of(s: Session, comment_id: int) -> str | None:
    return s.scalar(select(Comment.user_id).where(Comment.id == comment_id))


# ----------------------------------------------------------------------------- moderation

def queue(s: Session, profiles_fn, titles_fn) -> list[dict]:
    """Reported and held comments, oldest report first, with everything a moderator needs on
    one screen: the content, who reported it and why, and the author's history."""
    rows = s.execute(select(CommentReport.comment_id, func.min(CommentReport.created_at),
                            func.count()).where(CommentReport.status == "open")
                     .group_by(CommentReport.comment_id)
                     .order_by(func.min(CommentReport.created_at))).all()
    comment_ids = [r[0] for r in rows]
    comments = {c.id: c for c in s.scalars(select(Comment).where(Comment.id.in_(comment_ids))).all()} if comment_ids else {}
    reports: dict[int, list[CommentReport]] = {i: [] for i in comment_ids}
    if comment_ids:
        for r in s.scalars(select(CommentReport).where(CommentReport.comment_id.in_(comment_ids),
                                                       CommentReport.status == "open")).all():
            reports[r.comment_id].append(r)
    user_ids = {c.user_id for c in comments.values() if c.user_id} | {
        r.reporter_id for rs in reports.values() for r in rs}
    profiles = profiles_fn(s, list(user_ids))
    titles = titles_fn(s, list({c.question_id for c in comments.values()}))
    now = now_utc()
    out = []
    for cid, first, n in rows:
        c = comments.get(cid)
        if not c:
            continue
        waited = now - aware(first)
        out.append({"comment": c, "question_title": titles.get(c.question_id, ""),
                    "author": profiles.get(c.user_id or "", {}), "reports": reports[cid],
                    "reporters": {r.reporter_id: profiles.get(r.reporter_id, {}) for r in reports[cid]},
                    "history": user_history(s, c.user_id) if c.user_id else None,
                    "waited_hours": int(waited.total_seconds() // 3600),
                    "overdue": waited > HANDLING_TARGET})
    return out


def user_history(s: Session, user_id: str) -> dict:
    stats = dict(s.execute(select(Comment.status, func.count()).where(Comment.user_id == user_id)
                           .group_by(Comment.status)).all())
    actions = s.scalars(select(ModerationAction).where(ModerationAction.user_id == user_id)
                        .order_by(ModerationAction.created_at.desc()).limit(10)).all()
    reported = s.scalar(select(func.count()).select_from(CommentReport).join(
        Comment, Comment.id == CommentReport.comment_id).where(Comment.user_id == user_id)) or 0
    return {"comments": sum(stats.values()), "removed": stats.get("removed", 0),
            "times_reported": reported, "actions": actions}


def _close_reports(s: Session, comment_id: int, status: str, admin_id: str) -> int | None:
    now = now_utc()
    first = None
    for r in s.scalars(select(CommentReport).where(CommentReport.comment_id == comment_id,
                                                   CommentReport.status == "open")).all():
        first = min(first, aware(r.created_at)) if first else aware(r.created_at)
        r.status, r.handled_by, r.handled_at = status, admin_id, now
    return int((now - first).total_seconds() // 3600) if first else None


def moderate_comment(s: Session, comment_id: int, action: str, reason_code: str, admin_id: str,
                     note: str | None) -> Comment:
    if reason_code not in REASON_CODES:
        raise AppError(422, "VALIDATION_FAILED", "Choose a reason code.")
    c = s.get(Comment, comment_id)
    if not c:
        raise not_found("Comment")
    if action == "remove":
        if c.status == "deleted":
            raise AppError(409, "CONFLICT", "The author already deleted this comment.")
        c.status, c.removed_reason = "removed", reason_code
        hours = _close_reports(s, c.id, "actioned", admin_id)
    elif action == "restore":
        if c.status not in ("removed", "held"):
            raise AppError(409, "CONFLICT", "This comment is not hidden.")
        c.status, c.removed_reason = "visible", None
        hours = _close_reports(s, c.id, "dismissed", admin_id)
    elif action == "dismiss":
        if c.status == "held":
            c.status = "visible"
        hours = _close_reports(s, c.id, "dismissed", admin_id)
    else:
        raise AppError(400, "BAD_REQUEST", "Unknown action.")
    s.add(ModerationAction(admin_id=admin_id, action=action, reason_code=reason_code,
                           comment_id=c.id, user_id=c.user_id, note=(note or "").strip() or None,
                           handling_hours=hours))
    return c


def log_user_action(s: Session, user_id: str, action: str, reason_code: str, admin_id: str,
                    note: str | None, comment_id: int | None = None) -> None:
    if reason_code not in REASON_CODES:
        raise AppError(422, "VALIDATION_FAILED", "Choose a reason code.")
    s.add(ModerationAction(admin_id=admin_id, action=action, reason_code=reason_code,
                           comment_id=comment_id, user_id=user_id, note=(note or "").strip() or None))


def recent_actions(s: Session, limit: int = 100) -> list[ModerationAction]:
    return list(s.scalars(select(ModerationAction).order_by(ModerationAction.created_at.desc())
                          .limit(limit)).all())


def comment_snapshot(c: Comment) -> dict:
    return {"status": c.status, "removed_reason": c.removed_reason}


def all_comments(s: Session, titles_fn, limit: int = 200) -> list[dict]:
    rows = s.scalars(select(Comment).order_by(Comment.created_at.desc()).limit(limit)).all()
    titles = titles_fn(s, list({c.question_id for c in rows}))
    return [{"c": c, "question_title": titles.get(c.question_id, "")} for c in rows]


def counts(s: Session) -> dict[str, int]:
    total = s.scalar(select(func.count()).select_from(Comment)) or 0
    open_reports = s.scalar(select(func.count(func.distinct(CommentReport.comment_id))).where(
        CommentReport.status == "open")) or 0
    overdue = s.scalar(select(func.count(func.distinct(CommentReport.comment_id))).where(
        CommentReport.status == "open", CommentReport.created_at < now_utc() - HANDLING_TARGET)) or 0
    return {"comments": total, "reports_open": open_reports, "reports_overdue": overdue}


def handling_stats(s: Session, since: datetime) -> dict:
    hours = [h for h in s.scalars(select(ModerationAction.handling_hours).where(
        ModerationAction.created_at >= since, ModerationAction.handling_hours.is_not(None))).all()]
    within = sum(1 for h in hours if h <= HANDLING_TARGET.total_seconds() // 3600)
    return {"handled": len(hours), "within_target": within,
            "median_hours": sorted(hours)[len(hours) // 2] if hours else None}


def visible_counts(s: Session, ids: list[str]) -> dict[str, int]:
    if not ids:
        return {}
    return dict(s.execute(select(Comment.question_id, func.count())
                          .where(Comment.question_id.in_(ids), Comment.status == "visible")
                          .group_by(Comment.question_id)).all())


def user_comments(s: Session, user_id: str) -> list[dict]:
    return [{"id": c.id, "question_id": c.question_id, "body": c.body, "status": c.status,
             "created_at": iso(c.created_at)}
            for c in s.scalars(select(Comment).where(Comment.user_id == user_id)
                               .order_by(Comment.created_at.desc()).limit(500)).all()]


def erase_user(s: Session, user_id: str) -> None:
    """Account deletion: the user's comments are withdrawn and their text erased. Content a
    moderator removed is kept as evidence (IT Rules 2021 r.3(1)(g) retention), out of view."""
    for c in s.scalars(select(Comment).where(Comment.user_id == user_id)).all():
        if c.status not in ("deleted", "removed"):
            c.status, c.body = "deleted", ""
