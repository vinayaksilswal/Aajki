"""Grievance portal (in-app complaints with ticket status)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.db import SessionLocal, session_scope
from app.modules.compliance import service
from app.modules.identity.deps import current_user
from app.modules.identity.models import User
from app.ratelimit import hit

router = APIRouter(prefix="/v1", tags=["grievances"])


class GrievanceIn(BaseModel):
    category: str = Field(max_length=24)
    subject: str = Field(max_length=140)
    description: str = Field(max_length=3000)
    question_id: str | None = Field(None, max_length=40)
    support_review_consent: bool = False


@router.post("/grievances", status_code=201)
def raise_grievance(body: GrievanceIn, user: User = Depends(current_user)):
    # Blocked or suspended users can still complain: that is often what the complaint is about.
    hit("grievance", user.id, 5, 86400, "You've raised several complaints today. We'll reply to those first.")
    with session_scope() as s:
        return service.raise_grievance(s, user.id, body.category, body.subject, body.description,
                                       body.question_id, body.support_review_consent)


@router.get("/me/grievances")
def my_grievances(user: User = Depends(current_user)):
    with SessionLocal() as s:
        return service.my_grievances(s, user.id)
