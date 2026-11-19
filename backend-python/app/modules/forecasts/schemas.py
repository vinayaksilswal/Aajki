"""Public response contracts for the forecasts API (also drive the OpenAPI document)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Outcome(BaseModel):
    key: str
    label: str
    # Share of calls on this outcome, 0..1. Null when nobody has called yet, or while the
    # chance is withheld (election quiet period).
    chance: float | None


class Resolution(BaseModel):
    source_url: str | None
    rule: str | None


class Context(BaseModel):
    headline: str
    link: str | None


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
    trending: bool
    context: Context | None


class QuestionPage(BaseModel):
    items: list[QuestionOut]
    next_cursor: str | None
    as_of: str
