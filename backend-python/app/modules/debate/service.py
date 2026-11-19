"""Comment moderation for the admin panel. The full debate module (replies, attachments,
reports, blocks, rate limits, reason-coded moderation queue) arrives in M4."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import not_found
from app.modules.debate.models import Comment


def admin_list(s: Session, titles: dict[str, str], limit: int = 200) -> list[dict]:
    rows = s.scalars(select(Comment).order_by(Comment.created_at.desc()).limit(limit)).all()
    return [{"id": c.id, "author_name": c.author_name, "body": c.body, "hidden": c.hidden,
             "question_id": c.question_id, "question_title": titles.get(c.question_id, "(deleted)"),
             "created_at": c.created_at} for c in rows]


def question_ids(s: Session, limit: int = 200) -> list[str]:
    return list({qid for qid in s.scalars(select(Comment.question_id)
                                          .order_by(Comment.created_at.desc()).limit(limit)).all()})


def counts(s: Session) -> dict[str, int]:
    total, hidden = s.execute(select(func.count(), func.count().filter(Comment.hidden.is_(True)))
                              .select_from(Comment)).one()
    return {"comments": total, "hidden_comments": hidden}


def visible_counts(s: Session, ids: list[str]) -> dict[str, int]:
    if not ids:
        return {}
    return dict(s.execute(select(Comment.question_id, func.count())
                          .where(Comment.question_id.in_(ids), Comment.hidden.is_(False))
                          .group_by(Comment.question_id)).all())


def set_hidden(s: Session, comment_id: int, hidden: bool) -> None:
    c = s.get(Comment, comment_id)
    if not c:
        raise not_found("Comment")
    c.hidden = hidden


def delete(s: Session, comment_id: int) -> None:
    c = s.get(Comment, comment_id)
    if not c:
        raise not_found("Comment")
    s.delete(c)
