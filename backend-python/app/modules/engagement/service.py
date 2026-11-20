"""Daily check-in with a fixed streak reward, and the daily quiz (spec s.2, SOW 2.8).

Both rewards come from system:issuance through the ledger and count toward the user's daily
reward cap, which admins set in the policy panel. A reward withheld by the cap is recorded
as 0; the check-in or answer itself still counts.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.clock import ist_day, ist_day_start
from app.config import get_settings
from app.errors import AppError, not_found
from app.ids import new_id
from app.modules.engagement.models import CheckIn, Quiz, QuizAnswer
from app.modules.ledger import service as ledger
from app.modules.policy import service as policy

REWARD_KINDS = ("checkin_reward", "quiz_reward")


def _capped(s: Session, user_id: str, amount: int) -> int:
    used = ledger.rewards_since(s, user_id, REWARD_KINDS, ist_day_start())
    return max(0, min(amount, policy.daily_reward_cap(s) - used))


def _credit(s: Session, user_id: str, kind: str, amount: int, memo: str) -> None:
    if amount > 0:
        ledger.post(s, kind, [(ledger.ISSUANCE, -amount), (ledger.available(user_id), amount)],
                    user_id=user_id, earned=amount, memo=memo)


# ----------------------------------------------------------------------------- check-in

def checkin_status(s: Session, user_id: str) -> dict:
    today = ist_day()
    last = s.scalar(select(CheckIn).where(CheckIn.user_id == user_id).order_by(CheckIn.day.desc()))
    done = bool(last and last.day == today)
    alive = bool(last and last.day >= today - timedelta(days=1))
    return {"checked_in_today": done, "streak": last.streak if alive else 0,
            "reward": get_settings().checkin_reward}


def check_in(s: Session, user_id: str) -> dict:
    today = ist_day()
    last = s.scalar(select(CheckIn).where(CheckIn.user_id == user_id).order_by(CheckIn.day.desc()))
    if last and last.day == today:
        raise AppError(409, "ALREADY_CHECKED_IN", "You've already checked in today.")
    streak = last.streak + 1 if last and last.day == today - timedelta(days=1) else 1
    reward = _capped(s, user_id, get_settings().checkin_reward)
    s.add(CheckIn(user_id=user_id, day=today, streak=streak, reward=reward))
    try:
        s.flush()
    except IntegrityError:
        raise AppError(409, "ALREADY_CHECKED_IN", "You've already checked in today.")
    _credit(s, user_id, "checkin_reward", reward, f"Daily check-in reward (day {streak})")
    return {"checked_in_today": True, "streak": streak, "reward": reward}


def longest_streak(s: Session, user_id: str) -> int:
    return int(s.scalar(select(func.max(CheckIn.streak)).where(CheckIn.user_id == user_id)) or 0)


# ----------------------------------------------------------------------------- quiz

def _public_quiz(q: Quiz, answer: QuizAnswer | None) -> dict:
    out = {"id": q.id, "day": q.day.isoformat(), "question": q.question,
           "options": q.options, "reward": get_settings().quiz_reward, "answered": bool(answer)}
    if answer:
        out.update(your_answer=answer.answer_key, correct=answer.correct,
                   correct_key=q.correct_key, explanation=q.explanation, reward_received=answer.reward)
    return out


def today_quiz(s: Session, user_id: str | None) -> dict | None:
    q = s.scalar(select(Quiz).where(Quiz.day == ist_day(), Quiz.active.is_(True)))
    if not q:
        return None
    answer = s.scalar(select(QuizAnswer).where(QuizAnswer.quiz_id == q.id,
                                               QuizAnswer.user_id == user_id)) if user_id else None
    return _public_quiz(q, answer)


def answer_quiz(s: Session, user_id: str, quiz_id: str, answer_key: str) -> dict:
    q = s.get(Quiz, quiz_id)
    if not q or not q.active or q.day != ist_day():
        raise AppError(409, "QUIZ_CLOSED", "This quiz is no longer open.")
    if answer_key not in {o["key"] for o in q.options}:
        raise AppError(422, "VALIDATION_FAILED", "Choose one of the options.")
    correct = answer_key == q.correct_key
    reward = _capped(s, user_id, get_settings().quiz_reward) if correct else 0
    answer = QuizAnswer(quiz_id=q.id, user_id=user_id, answer_key=answer_key, correct=correct,
                        reward=reward)
    s.add(answer)
    try:
        s.flush()
    except IntegrityError:
        raise AppError(409, "ALREADY_ANSWERED", "You've already answered today's quiz.")
    _credit(s, user_id, "quiz_reward", reward, "Daily quiz reward")
    return _public_quiz(q, answer)


_KEYS = ("a", "b", "c", "d")


def quiz_problems(d: dict) -> dict[str, str]:
    p: dict[str, str] = {}
    if not 10 <= len(d.get("question") or "") <= 300:
        p["question"] = "Write the question in 10 to 300 characters."
    opts = [o for o in d.get("options") or [] if o.get("label")]
    if not 2 <= len(opts) <= 4:
        p["options"] = "Give 2 to 4 options."
    if d.get("correct_key") not in {o["key"] for o in opts}:
        p["correct_key"] = "Pick the correct option."
    if not isinstance(d.get("day"), date):
        p["day"] = "Pick the day this quiz runs."
    if re.search(r"\b(bet|odds|stake|wager|gambl\w*)\b", d.get("question") or "", re.IGNORECASE):
        p["question"] = "Use the product vocabulary: forecast, call, chance, points, reward."
    return p


def save_quiz(s: Session, d: dict, admin_id: str, quiz_id: str | None = None) -> Quiz:
    problems = quiz_problems(d)
    if problems:
        raise AppError(422, "VALIDATION_FAILED", "Fix the highlighted fields.", problems)
    opts = [{"key": _KEYS[i], "label": o["label"].strip()[:120]}
            for i, o in enumerate(o for o in d["options"] if o.get("label"))]
    if quiz_id:
        q = s.get(Quiz, quiz_id)
        if not q:
            raise not_found("Quiz")
        if s.scalar(select(func.count()).select_from(QuizAnswer).where(QuizAnswer.quiz_id == q.id)):
            raise AppError(409, "LOCKED", "People have already answered this quiz, so it can't be changed.")
    else:
        if s.scalar(select(Quiz.id).where(Quiz.day == d["day"])):
            raise AppError(409, "CONFLICT", "There is already a quiz for that day.", {"day": "taken"})
        q = Quiz(id=new_id("quiz"), created_by=admin_id)
        s.add(q)
    q.day, q.question, q.options = d["day"], d["question"].strip(), opts
    remap = {o["key"]: _KEYS[i] for i, o in enumerate(o for o in d["options"] if o.get("label"))}
    q.correct_key = remap.get(d["correct_key"], d["correct_key"])
    q.explanation = (d.get("explanation") or "").strip() or None
    q.active = bool(d.get("active", True))
    s.flush()
    return q


def quizzes(s: Session, limit: int = 60) -> list[dict]:
    rows = s.scalars(select(Quiz).order_by(Quiz.day.desc()).limit(limit)).all()
    stats = dict(s.execute(select(QuizAnswer.quiz_id, func.count()).group_by(QuizAnswer.quiz_id)).all())
    return [{"quiz": q, "answers": stats.get(q.id, 0)} for q in rows]


def get_quiz(s: Session, quiz_id: str) -> Quiz:
    q = s.get(Quiz, quiz_id)
    if not q:
        raise not_found("Quiz")
    return q


def quiz_snapshot(q: Quiz) -> dict:
    return {"day": q.day.isoformat(), "question": q.question, "options": q.options,
            "correct_key": q.correct_key, "active": q.active}


def checkins_today(s: Session) -> int:
    return int(s.scalar(select(func.count()).select_from(CheckIn).where(CheckIn.day == ist_day())) or 0)




def users_checked_in(s: Session, ids: list[str]) -> set[str]:
    out: set[str] = set()
    for chunk in range(0, len(ids), 500):
        out |= set(s.scalars(select(CheckIn.user_id).where(CheckIn.user_id.in_(ids[chunk:chunk + 500]))
                             .distinct()).all())
    return out
