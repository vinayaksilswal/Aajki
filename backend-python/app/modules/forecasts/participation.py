"""Calls, settlement and disputes (spec s.2, s.3, s.6; SOW 2.4, 2.6, 3.3).

Settlement formula: a correct call receives
    points committed x total points on the question / points on the winning outcome
rounded down; the remainder of the pool goes to system:rounding. The question is voided and
every point returned when nobody chose the winning outcome, when only one outcome had calls,
or when the event is cancelled.

Two-person rule: a Settlement Officer proposes a result with its source link; a different
admin holding the Settlement Approver role approves or rejects it. A correction to an
approved result goes through the same rule and reverses the earlier ledger entries with new
ones.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.clock import aware, ist_day, ist_day_start, iso, now_utc
from app.config import get_settings
from app.errors import AppError, not_found
from app.ids import new_id
from app.modules.forecasts import service
from app.modules.forecasts.models import Call, Dispute, Question, Settlement
from app.modules.ledger import service as ledger

# ----------------------------------------------------------------------------- calls


def calls_today(s: Session, user_id: str) -> int:
    return int(s.scalar(select(func.count()).select_from(Call).where(
        Call.user_id == user_id, Call.created_at >= ist_day_start())) or 0)


def _call_out(c: Call, q: Question | None = None) -> dict:
    out = {"id": c.id, "question_id": c.question_id, "outcome_key": c.outcome_key,
           "points": c.points, "status": c.status, "released": c.released,
           "created_at": iso(c.created_at), "settled_at": iso(c.settled_at)}
    if q is not None:
        labels = {o["key"]: o["label"] for o in q.outcomes or []}
        out.update(question_title=q.title, outcome_label=labels.get(c.outcome_key, c.outcome_key),
                   question_status=service.effective_status(q), category=q.category)
    return out


def place_call(s: Session, user_id: str, question_id: str, outcome_key: str, points: int,
               idempotency_key: str) -> tuple[dict, bool]:
    """Commit points to an outcome. Returns (call, created). Retrying with the same
    Idempotency-Key returns the original call instead of committing points twice."""
    st = get_settings()
    payload = {"question_id": question_id, "outcome_key": outcome_key, "points": points}
    earlier = ledger.find_idempotent(s, user_id, idempotency_key, payload)
    if earlier:
        call = s.scalar(select(Call).where(Call.commit_txn_id == earlier.id))
        return _call_out(call, s.get(Question, call.question_id)), False

    q = s.get(Question, question_id)
    if not q or not service.is_public(q):
        raise not_found("Question")
    if service.effective_status(q) != "open":
        raise AppError(409, "QUESTION_NOT_OPEN", "This question isn't taking calls right now.")
    if outcome_key not in {o["key"] for o in q.outcomes or []}:
        raise AppError(422, "VALIDATION_FAILED", "Choose one of the question's outcomes.")
    if not st.call_min_points <= points <= st.call_max_points:
        raise AppError(422, "VALIDATION_FAILED",
                       f"Commit between {st.call_min_points} and {st.call_max_points} points.")
    if s.scalar(select(Call.id).where(Call.question_id == q.id, Call.user_id == user_id)):
        raise AppError(409, "ALREADY_CALLED", "You've already made your call on this question.")
    if calls_today(s, user_id) >= st.daily_call_cap:
        raise AppError(429, "DAILY_CALL_LIMIT",
                       f"You've made your {st.daily_call_cap} calls for today. More tomorrow.")

    txn = ledger.post(s, "call_commit",
                      [(ledger.available(user_id), -points), (ledger.committed(user_id), points)],
                      user_id=user_id, question_id=q.id, idempotency_key=idempotency_key,
                      payload=payload, memo=q.title[:200])
    call = Call(id=new_id("call"), question_id=q.id, user_id=user_id, outcome_key=outcome_key,
                points=points, status="active", commit_txn_id=txn.id, created_at=txn.created_at)
    s.add(call)
    try:
        s.flush()
    except IntegrityError:
        # A concurrent request for the same question won the race; this one rolls back.
        raise AppError(409, "ALREADY_CALLED", "You've already made your call on this question.")
    return _call_out(call, q), True


def my_calls(s: Session, user_id: str, status: str | None = None, limit: int = 100) -> list[dict]:
    stmt = select(Call, Question).join(Question, Question.id == Call.question_id).where(
        Call.user_id == user_id)
    if status == "active":
        stmt = stmt.where(Call.status == "active")
    elif status == "settled":
        stmt = stmt.where(Call.status != "active")
    rows = s.execute(stmt.order_by(Call.created_at.desc()).limit(limit)).all()
    return [_call_out(c, q) for c, q in rows]


def my_call_on(s: Session, user_id: str, question_id: str) -> dict | None:
    c = s.scalar(select(Call).where(Call.user_id == user_id, Call.question_id == question_id))
    return _call_out(c) if c else None


def accuracy(s: Session, user_id: str) -> dict:
    rows = dict(s.execute(select(Call.status, func.count()).where(Call.user_id == user_id)
                          .group_by(Call.status)).all())
    correct, incorrect = rows.get("correct", 0), rows.get("incorrect", 0)
    decided = correct + incorrect
    return {"calls": sum(rows.values()), "correct": correct, "incorrect": incorrect,
            "active": rows.get("active", 0), "refunded": rows.get("refunded", 0),
            "accuracy": round(correct / decided, 4) if decided else None}


# ----------------------------------------------------------------------------- refunds

def refund_all(s: Session, q: Question, memo: str, ref: str | None = None) -> int:
    """Return the points of every active call on a question. Returns how many."""
    now = now_utc()
    calls = s.scalars(select(Call).where(Call.question_id == q.id, Call.status == "active")
                      .order_by(Call.id)).all()
    for c in calls:
        ledger.post(s, "call_refund", [(ledger.committed(c.user_id), -c.points),
                                       (ledger.available(c.user_id), c.points)],
                    user_id=c.user_id, question_id=q.id, ref=ref, memo=memo)
        c.status, c.released, c.settled_at = "refunded", c.points, now
    for p in s.scalars(select(Settlement).where(Settlement.question_id == q.id,
                                                Settlement.status == "proposed")).all():
        p.status, p.decided_at, p.decision_note = "rejected", now, "Question voided"
    return len(calls)


# ----------------------------------------------------------------------------- settlement

def pending_proposal(s: Session, question_id: str) -> Settlement | None:
    return s.scalar(select(Settlement).where(Settlement.question_id == question_id,
                                             Settlement.status == "proposed"))


def approved(s: Session, question_id: str) -> Settlement | None:
    return s.scalar(select(Settlement).where(Settlement.question_id == question_id,
                                             Settlement.status == "approved"))


def propose(s: Session, q: Question, result: str, source_url: str | None, note: str | None,
            admin_id: str) -> Settlement:
    now = now_utc()
    keys = {o["key"] for o in q.outcomes or []}
    if result not in keys | {"void"}:
        raise AppError(422, "VALIDATION_FAILED", "Choose an outcome, or void for a cancelled event.")
    if result != "void" and not service._https(source_url):
        raise AppError(422, "VALIDATION_FAILED", "Link the official https source that confirms the result.",
                       {"source_url": "required"})
    if result == "void" and len((note or "").strip()) < 10:
        raise AppError(422, "VALIDATION_FAILED", "Explain why the event was cancelled.",
                       {"note": "required"})
    if pending_proposal(s, q.id):
        raise AppError(409, "CONFLICT", "A proposed result is already waiting for approval.")
    status = service.effective_status(q, now)
    current = approved(s, q.id)
    if current:
        if not current.dispute_until or aware(current.dispute_until) <= now:
            raise AppError(409, "CONFLICT", "The dispute window has ended; this result is final.")
        if result == current.applied_result:
            raise AppError(409, "CONFLICT", "That is already the settled result.")
    elif status != "closed" and not (result == "void" and status in ("open", "paused")):
        raise AppError(409, "CONFLICT", "Results can be proposed once the question has closed "
                       "(or, for a cancelled event, voided at any time).")
    p = Settlement(id=new_id("stl"), question_id=q.id, result=result, source_url=source_url,
                   note=(note or "").strip() or None, status="proposed",
                   corrects_id=current.id if current else None, proposed_by=admin_id, proposed_at=now)
    s.add(p)
    s.flush()
    return p


def reject(s: Session, p: Settlement, admin_id: str, note: str) -> Settlement:
    _check_decider(p, admin_id)
    if len((note or "").strip()) < 5:
        raise AppError(422, "VALIDATION_FAILED", "Say why the result is rejected.", {"note": "required"})
    p.status, p.decided_by, p.decided_at, p.decision_note = "rejected", admin_id, now_utc(), note.strip()
    return p


def _check_decider(p: Settlement, admin_id: str) -> None:
    if p.status != "proposed":
        raise AppError(409, "CONFLICT", "This proposal has already been decided.")
    if p.proposed_by == admin_id:
        raise AppError(403, "TWO_PERSON_RULE", "A different admin must approve this result.")


def approve(s: Session, p: Settlement, admin_id: str, note: str | None = None) -> Settlement:
    """Apply the result: release points to correct calls, or void and refund."""
    _check_decider(p, admin_id)
    q = s.get(Question, p.question_id)
    now = now_utc()
    if p.corrects_id:
        _reverse(s, s.get(Settlement, p.corrects_id), f"Corrected result: {p.result}")

    ref = f"settlement:{p.id}"
    calls = s.scalars(select(Call).where(Call.question_id == q.id, Call.status == "active")
                      .order_by(Call.id)).all()
    by_outcome: dict[str, int] = {}
    for c in calls:
        by_outcome[c.outcome_key] = by_outcome.get(c.outcome_key, 0) + c.points
    total = sum(by_outcome.values())
    winning = by_outcome.get(p.result, 0)

    if p.result == "void":
        applied, reason = "void", "Event cancelled or abandoned"
    elif not calls:
        applied, reason = "void", "No calls were made"
    elif winning == 0:
        applied, reason = "void", "Nobody chose the winning outcome"
    elif len(by_outcome) == 1:
        applied, reason = "void", "Only one outcome received calls"
    else:
        applied, reason = p.result, None

    if applied == "void":
        refund_all(s, q, f"Question voided ({reason.lower()}): points returned", ref=ref)
        q.status = "voided"
    else:
        released_total = 0
        pool = ledger.pool(q.id)
        for c in calls:
            correct = c.outcome_key == applied
            released = c.points * total // winning if correct else 0
            released_total += released
            legs = [(ledger.committed(c.user_id), -c.points), (pool, c.points - released)]
            if released:
                legs.append((ledger.available(c.user_id), released))
            ledger.post(s, "call_settle", legs, user_id=c.user_id, question_id=q.id, ref=ref,
                        earned=max(0, released - c.points),
                        memo=("Correct call: points released" if correct else "Call settled"))
            c.status, c.released, c.settled_at = ("correct" if correct else "incorrect"), released, now
        remainder = total - released_total
        if remainder:
            ledger.post(s, "rounding", [(pool, -remainder), (ledger.ROUNDING, remainder)],
                        question_id=q.id, ref=ref, memo="Rounding remainder")
        q.status = "settled"

    p.status, p.decided_by, p.decided_at = "approved", admin_id, now
    p.decision_note = (note or "").strip() or None
    p.applied_result, p.applied_reason = applied, reason
    p.dispute_until = now + timedelta(hours=get_settings().dispute_window_hours)
    return p


def _reverse(s: Session, old: Settlement, memo: str) -> None:
    """Undo an approved result with new, opposite ledger entries; calls become active again."""
    for txn in ledger.by_ref(s, f"settlement:{old.id}"):
        ledger.reverse(s, txn, memo)
    for c in s.scalars(select(Call).where(Call.question_id == old.question_id)).all():
        c.status, c.released, c.settled_at = "active", None, None
    old.status = "superseded"
    q = s.get(Question, old.question_id)
    q.status = "published"
    s.flush()  # sessions don't autoflush: the re-settlement below reads these calls back


def history(s: Session, question_id: str | None = None, limit: int = 200) -> list[Settlement]:
    stmt = select(Settlement).order_by(Settlement.proposed_at.desc()).limit(limit)
    if question_id:
        stmt = stmt.where(Settlement.question_id == question_id)
    return list(s.scalars(stmt).all())


def get_settlement(s: Session, sid: str) -> Settlement:
    p = s.get(Settlement, sid)
    if not p:
        raise not_found("Settlement")
    return p


def public_result(s: Session, question_id: str) -> dict | None:
    p = approved(s, question_id)
    if not p:
        return None
    return {"result": p.applied_result, "reason": p.applied_reason, "source_url": p.source_url,
            "settled_at": iso(p.decided_at), "dispute_until": iso(p.dispute_until)}


# ----------------------------------------------------------------------------- disputes

def raise_dispute(s: Session, user_id: str, question_id: str, reason: str,
                  evidence_url: str | None) -> Dispute:
    p = approved(s, question_id)
    if not p:
        raise AppError(409, "CONFLICT", "This question has no settled result to dispute.")
    if not p.dispute_until or aware(p.dispute_until) <= now_utc():
        raise AppError(409, "DISPUTE_WINDOW_CLOSED", "The dispute window for this result has ended.")
    if not s.scalar(select(Call.id).where(Call.question_id == question_id, Call.user_id == user_id)):
        raise AppError(403, "FORBIDDEN", "Only people who made a call can dispute the result.")
    reason = (reason or "").strip()
    if not 10 <= len(reason) <= 1000:
        raise AppError(422, "VALIDATION_FAILED", "Explain the problem in 10 to 1,000 characters.")
    if evidence_url and not service._https(evidence_url):
        raise AppError(422, "VALIDATION_FAILED", "Use an https:// link for evidence.")
    if s.scalar(select(Dispute.id).where(Dispute.settlement_id == p.id, Dispute.user_id == user_id)):
        raise AppError(409, "CONFLICT", "You've already disputed this result.")
    d = Dispute(id=new_id("dsp"), settlement_id=p.id, question_id=question_id, user_id=user_id,
                reason=reason, evidence_url=evidence_url or None)
    s.add(d)
    s.flush()
    return d


def decide_dispute(s: Session, d: Dispute, admin_id: str, upheld: bool, note: str) -> Dispute:
    """Upholding a dispute records the decision; the result itself changes only through a
    corrected proposal and a second admin's approval (two-person rule)."""
    if d.status != "open":
        raise AppError(409, "CONFLICT", "This dispute has already been decided.")
    if len((note or "").strip()) < 5:
        raise AppError(422, "VALIDATION_FAILED", "Record the reason for the decision.")
    d.status = "upheld" if upheld else "dismissed"
    d.decided_by, d.decided_at, d.decision_note = admin_id, now_utc(), note.strip()
    return d


def my_disputes(s: Session, user_id: str) -> list[dict]:
    return [{"id": d.id, "question_id": d.question_id, "status": d.status, "reason": d.reason,
             "created_at": iso(d.created_at), "decision_note": d.decision_note}
            for d in s.scalars(select(Dispute).where(Dispute.user_id == user_id)
                               .order_by(Dispute.created_at.desc())).all()]


def disputes(s: Session, status: str | None = "open") -> list[Dispute]:
    stmt = select(Dispute).order_by(Dispute.created_at)
    if status:
        stmt = stmt.where(Dispute.status == status)
    return list(s.scalars(stmt.limit(300)).all())


def get_dispute(s: Session, did: str) -> Dispute:
    d = s.get(Dispute, did)
    if not d:
        raise not_found("Dispute")
    return d


def outcome_totals(s: Session, question_id: str) -> dict[str, dict[str, int]]:
    return service.participation(s, [question_id]).get(question_id, {})


def volume_by_day(s: Session, days: int = 14) -> list[tuple[str, int]]:
    """Calls per Indian day for the operations dashboard."""
    since = ist_day_start() - timedelta(days=days - 1)
    counts: dict[str, int] = {}
    for created in s.scalars(select(Call.created_at).where(Call.created_at >= since)).all():
        day = ist_day(aware(created)).isoformat()
        counts[day] = counts.get(day, 0) + 1
    today = ist_day()
    return [((today - timedelta(days=days - 1 - i)).isoformat(),
             counts.get((today - timedelta(days=days - 1 - i)).isoformat(), 0)) for i in range(days)]


def first_call_users(s: Session, since: datetime) -> int:
    return int(s.scalar(select(func.count(func.distinct(Call.user_id))).where(
        Call.created_at >= since)) or 0)


def results_for(s: Session, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    return {p.question_id: {"result": p.applied_result, "reason": p.applied_reason,
                            "source_url": p.source_url, "settled_at": iso(p.decided_at),
                            "dispute_until": iso(p.dispute_until)}
            for p in s.scalars(select(Settlement).where(Settlement.question_id.in_(ids),
                                                        Settlement.status == "approved")).all()}


def users_with_calls(s: Session, ids: list[str]) -> set[str]:
    out: set[str] = set()
    for chunk in range(0, len(ids), 500):
        out |= set(s.scalars(select(Call.user_id).where(Call.user_id.in_(ids[chunk:chunk + 500]))
                             .distinct()).all())
    return out
