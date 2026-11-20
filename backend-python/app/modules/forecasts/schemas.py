"""Public response and request contracts for the forecasts API (also drive the OpenAPI document)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Outcome(BaseModel):
    key: str
    label: str
    # Share of committed points on this outcome, 0..1. Null when nobody has called yet, or
    # while the chance is withheld (election quiet period).
    chance: float | None


class Resolution(BaseModel):
    source_url: str | None
    rule: str | None


class Context(BaseModel):
    headline: str
    link: str | None


class Result(BaseModel):
    # The winning outcome key, or "void" (points returned).
    result: str | None
    reason: str | None
    source_url: str | None
    settled_at: str | None
    dispute_until: str | None


class QuestionOut(BaseModel):
    id: str
    category: str
    title: str
    description: str | None
    image_url: str | None
    status: Literal["open", "closed", "paused", "settled", "voided"]
    opens_at: str | None
    closes_at: str | None
    outcomes: list[Outcome]
    participants: int
    chance_hidden: bool
    resolution: Resolution
    election_sensitive: bool
    election_state: str | None
    trending: bool
    context: Context | None
    result: Result | None = None


class QuestionPage(BaseModel):
    items: list[QuestionOut]
    next_cursor: str | None
    as_of: str


class CallIn(BaseModel):
    outcome_key: str = Field(max_length=40)
    points: int


class CallOut(BaseModel):
    id: str
    question_id: str
    outcome_key: str
    points: int
    status: Literal["active", "correct", "incorrect", "refunded"]
    released: int | None
    created_at: str | None
    settled_at: str | None
    question_title: str | None = None
    outcome_label: str | None = None
    question_status: str | None = None
    category: str | None = None


class DisputeIn(BaseModel):
    reason: str = Field(max_length=1000)
    evidence_url: str | None = Field(None, max_length=500)
