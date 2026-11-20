"""The only code that moves points. Other modules call these functions; none writes the
ledger tables itself."""
from __future__ import annotations

import base64
import hashlib
import json
from collections import defaultdict
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.clock import iso, now_utc
from app.errors import AppError
from app.ids import new_id
from app.modules.ledger.models import LedgerBalance, LedgerEntry, LedgerTransaction

ISSUANCE = "system:issuance"
ROUNDING = "system:rounding"


def available(user_id: str) -> str:
    return f"user:{user_id}:available"


def committed(user_id: str) -> str:
    return f"user:{user_id}:committed"


def pool(question_id: str) -> str:
    return f"question:{question_id}:pool"


def request_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def find_idempotent(s: Session, user_id: str, key: str, payload: dict) -> LedgerTransaction | None:
    """The transaction an earlier request with this key created, if any. A key reused for a
    different request is refused rather than silently ignored."""
    txn = s.scalar(select(LedgerTransaction).where(LedgerTransaction.user_id == user_id,
                                                   LedgerTransaction.idempotency_key == key))
    if txn and txn.request_hash != request_hash(payload):
        raise AppError(409, "IDEMPOTENCY_KEY_REUSED",
                       "This request key was already used for a different request.")
    return txn


def _lock(s: Session, accounts: list[str]) -> dict[str, int]:
    """Create missing balance rows, then lock all of them in a fixed order (no deadlocks)."""
    insert = pg_insert if s.bind.dialect.name == "postgresql" else sqlite_insert
    s.execute(insert(LedgerBalance).values([{"account": a, "balance": 0} for a in accounts])
              .on_conflict_do_nothing(index_elements=[LedgerBalance.account]))
    rows = s.execute(select(LedgerBalance.account, LedgerBalance.balance)
                     .where(LedgerBalance.account.in_(accounts))
                     .order_by(LedgerBalance.account).with_for_update()).all()
    return {a: b for a, b in rows}


def post(s: Session, kind: str, legs: list[tuple[str, int]], *, user_id: str | None = None,
         question_id: str | None = None, idempotency_key: str | None = None,
         payload: dict | None = None, earned: int = 0, ref: str | None = None,
         reverses_id: str | None = None, memo: str | None = None,
         allow_negative: bool = False) -> LedgerTransaction:
    """Record one balanced transaction. A user's available balance may not go below zero,
    except for a reversal (a corrected result may claw back points already used)."""
    merged: dict[str, int] = defaultdict(int)
    for account, amount in legs:
        merged[account] += int(amount)
    merged = {a: v for a, v in merged.items() if v}
    if not merged or sum(merged.values()) != 0:
        raise ValueError(f"unbalanced or empty ledger transaction: {legs}")

    balances = _lock(s, sorted(merged))
    for account, delta in merged.items():
        if (account.startswith("user:") and account.endswith(":available")
                and delta < 0 and balances[account] + delta < 0 and not allow_negative):
            raise AppError(409, "INSUFFICIENT_POINTS", "You don't have enough points for that.",
                           {"available": max(0, balances[account])})
    now = now_utc()
    txn = LedgerTransaction(id=new_id("txn"), kind=kind, user_id=user_id, question_id=question_id,
                            idempotency_key=idempotency_key,
                            request_hash=request_hash(payload) if payload is not None else None,
                            earned=earned, ref=ref, reverses_id=reverses_id, memo=memo,
                            created_at=now)
    s.add(txn)
    s.flush()
    s.add_all(LedgerEntry(txn_id=txn.id, account=a, amount=v, created_at=now)
              for a, v in merged.items())
    for account, delta in merged.items():
        s.execute(update(LedgerBalance).where(LedgerBalance.account == account)
                  .values(balance=LedgerBalance.balance + delta))
    s.flush()
    return txn


def reverse(s: Session, txn: LedgerTransaction, memo: str) -> LedgerTransaction:
    """A new transaction that undoes `txn` exactly. Nothing is edited or deleted."""
    entries = s.scalars(select(LedgerEntry).where(LedgerEntry.txn_id == txn.id)).all()
    return post(s, "reversal", [(e.account, -e.amount) for e in entries], user_id=txn.user_id,
                question_id=txn.question_id, earned=-txn.earned, ref=txn.ref,
                reverses_id=txn.id, memo=memo, allow_negative=True)


def by_ref(s: Session, ref: str) -> list[LedgerTransaction]:
    return list(s.scalars(select(LedgerTransaction).where(
        LedgerTransaction.ref == ref, LedgerTransaction.kind != "reversal")
        .order_by(LedgerTransaction.created_at)).all())


# ----------------------------------------------------------------------------- reads

def balance(s: Session, account: str) -> int:
    return int(s.scalar(select(LedgerBalance.balance).where(LedgerBalance.account == account)) or 0)


def user_balances(s: Session, user_id: str) -> dict[str, int]:
    return {"available": balance(s, available(user_id)), "committed": balance(s, committed(user_id))}


def lifetime_earned(s: Session, user_id: str) -> int:
    return int(s.scalar(select(func.coalesce(func.sum(LedgerTransaction.earned), 0))
                        .where(LedgerTransaction.user_id == user_id)) or 0)


def lifetime_for(s: Session, user_ids: list[str]) -> dict[str, int]:
    if not user_ids:
        return {}
    return {uid: int(v) for uid, v in s.execute(
        select(LedgerTransaction.user_id, func.sum(LedgerTransaction.earned))
        .where(LedgerTransaction.user_id.in_(user_ids)).group_by(LedgerTransaction.user_id)).all()}


def earned_since(s: Session, since: datetime | None, limit: int, exclude: set[str]) -> list[tuple[str, int]]:
    """(user_id, points earned) for the top earners since a moment (None = all time)."""
    stmt = (select(LedgerTransaction.user_id, func.sum(LedgerTransaction.earned).label("pts"))
            .where(LedgerTransaction.user_id.is_not(None)).group_by(LedgerTransaction.user_id))
    if since is not None:
        stmt = stmt.where(LedgerTransaction.created_at >= since)
    if exclude:
        stmt = stmt.where(LedgerTransaction.user_id.not_in(exclude))
    stmt = stmt.having(func.sum(LedgerTransaction.earned) > 0).order_by(
        func.sum(LedgerTransaction.earned).desc(), LedgerTransaction.user_id).limit(limit)
    return [(uid, int(pts)) for uid, pts in s.execute(stmt).all()]


def earned_by(s: Session, user_id: str, since: datetime | None) -> int:
    stmt = select(func.coalesce(func.sum(LedgerTransaction.earned), 0)).where(
        LedgerTransaction.user_id == user_id)
    if since is not None:
        stmt = stmt.where(LedgerTransaction.created_at >= since)
    return int(s.scalar(stmt) or 0)


def users_ahead(s: Session, points: int, since: datetime | None, exclude: set[str]) -> int:
    """How many users earned more than `points` in the period (for "your position")."""
    inner = (select(LedgerTransaction.user_id, func.sum(LedgerTransaction.earned).label("pts"))
             .where(LedgerTransaction.user_id.is_not(None)).group_by(LedgerTransaction.user_id))
    if since is not None:
        inner = inner.where(LedgerTransaction.created_at >= since)
    if exclude:
        inner = inner.where(LedgerTransaction.user_id.not_in(exclude))
    sub = inner.subquery()
    return int(s.scalar(select(func.count()).select_from(sub).where(sub.c.pts > points)) or 0)


def rewards_since(s: Session, user_id: str, kinds: tuple[str, ...], since: datetime) -> int:
    """Points a user received from these reward kinds since a moment (daily reward cap)."""
    return int(s.scalar(select(func.coalesce(func.sum(LedgerTransaction.earned), 0)).where(
        LedgerTransaction.user_id == user_id, LedgerTransaction.kind.in_(kinds),
        LedgerTransaction.created_at >= since)) or 0)


def _cursor(created: datetime, txn_id: str) -> str:
    return base64.urlsafe_b64encode(json.dumps([iso(created), txn_id]).encode()).decode()


def history(s: Session, user_id: str, cursor: str | None, limit: int) -> dict:
    """The user's own ledger, newest first: one row per transaction with its effect on
    the user's available and committed points."""
    accounts = [available(user_id), committed(user_id)]
    stmt = select(LedgerTransaction).where(LedgerTransaction.user_id == user_id)
    if cursor:
        try:
            created_s, last_id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            created = datetime.fromisoformat(created_s.replace("Z", "+00:00"))
        except Exception:
            raise AppError(400, "BAD_CURSOR", "That page link has expired. Reload the list.")
        stmt = stmt.where((LedgerTransaction.created_at < created) |
                          ((LedgerTransaction.created_at == created) & (LedgerTransaction.id < last_id)))
    txns = s.scalars(stmt.order_by(LedgerTransaction.created_at.desc(), LedgerTransaction.id.desc())
                     .limit(limit + 1)).all()
    page, more = txns[:limit], len(txns) > limit
    effects: dict[str, dict[str, int]] = defaultdict(lambda: {"available": 0, "committed": 0})
    if page:
        for txn_id, account, amount in s.execute(
                select(LedgerEntry.txn_id, LedgerEntry.account, LedgerEntry.amount).where(
                    LedgerEntry.txn_id.in_([t.id for t in page]), LedgerEntry.account.in_(accounts))).all():
            effects[txn_id]["available" if account.endswith(":available") else "committed"] += amount
    items = [{"id": t.id, "kind": t.kind, "question_id": t.question_id, "memo": t.memo,
              "available_change": effects[t.id]["available"],
              "committed_change": effects[t.id]["committed"], "earned": t.earned,
              "created_at": iso(t.created_at)} for t in page]
    next_cursor = _cursor(page[-1].created_at, page[-1].id) if more else None
    return {"items": items, "next_cursor": next_cursor}


def economy(s: Session, since: datetime) -> dict:
    """Points issued against points committed (admin economy view)."""
    issued_total = -balance(s, ISSUANCE)
    committed_total = int(s.scalar(select(func.coalesce(func.sum(LedgerBalance.balance), 0)).where(
        LedgerBalance.account.like("user:%:committed"))) or 0)
    available_total = int(s.scalar(select(func.coalesce(func.sum(LedgerBalance.balance), 0)).where(
        LedgerBalance.account.like("user:%:available"))) or 0)
    in_pools = int(s.scalar(select(func.coalesce(func.sum(LedgerBalance.balance), 0)).where(
        LedgerBalance.account.like("question:%:pool"))) or 0)
    by_kind = dict(s.execute(
        select(LedgerTransaction.kind, func.coalesce(func.sum(-LedgerEntry.amount), 0))
        .join(LedgerEntry, LedgerEntry.txn_id == LedgerTransaction.id)
        .where(LedgerTransaction.created_at >= since, LedgerEntry.account == ISSUANCE)
        .group_by(LedgerTransaction.kind)).all())
    return {"issued_total": issued_total, "available_total": available_total,
            "committed_total": committed_total, "in_pools": in_pools,
            "rounding_total": balance(s, ROUNDING),
            "rewards_today": {k: int(v) for k, v in by_kind.items()},
            # Every point issued is somewhere: with users, in a pool or rounded off.
            "balanced": issued_total == available_total + committed_total + in_pools + balance(s, ROUNDING)}
