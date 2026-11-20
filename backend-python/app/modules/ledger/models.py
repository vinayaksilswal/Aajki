"""Double-entry points ledger (spec s.1, s.5).

Every movement of points is one transaction whose entries sum to zero. Entries are never
updated or deleted (a Postgres trigger enforces it); a correction is a new, reversing
transaction. There is no payout, withdrawal or user-to-user transfer path.

Accounts are strings:
    user:<id>:available     points a user can commit
    user:<id>:committed     points committed to open calls
    question:<id>:pool      points gathered on a question while it settles
    system:issuance         source of every reward
    system:rounding         the remainder left when released points are rounded down
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.modules.identity.models import utcnow


class LedgerTransaction(Base):
    __tablename__ = "ledger_transactions"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key",
                                       name="uq_ledger_transactions_user_idempotency"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    # signup_reward, checkin_reward, quiz_reward, call_commit, call_settle, call_refund, reversal
    kind: Mapped[str] = mapped_column(String(24), index=True)
    # The user this transaction is for (also the partition key the spec asks for).
    user_id: Mapped[str | None] = mapped_column(String(40), index=True)
    question_id: Mapped[str | None] = mapped_column(String(40), index=True)
    # Client-supplied key: a retried request returns the first result instead of moving
    # points twice. request_hash detects a key reused for a different request.
    idempotency_key: Mapped[str | None] = mapped_column(String(80))
    request_hash: Mapped[str | None] = mapped_column(String(64))
    # Points this transaction adds to the user's lifetime earned total (rank basis). Rewards
    # count in full; a correct call counts what it released beyond the points committed.
    earned: Mapped[int] = mapped_column(Integer, default=0)
    # Groups transactions for reversal, e.g. "settlement:<id>".
    ref: Mapped[str | None] = mapped_column(String(80), index=True)
    reverses_id: Mapped[str | None] = mapped_column(ForeignKey("ledger_transactions.id"))
    memo: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    txn_id: Mapped[str] = mapped_column(ForeignKey("ledger_transactions.id"), index=True)
    account: Mapped[str] = mapped_column(String(80), index=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LedgerBalance(Base):
    """Running balance per account, updated in the same transaction as its entries and
    locked while it changes. Always equal to the sum of the account's entries."""
    __tablename__ = "ledger_balances"

    account: Mapped[str] = mapped_column(String(80), primary_key=True)
    balance: Mapped[int] = mapped_column(BigInteger, default=0)
