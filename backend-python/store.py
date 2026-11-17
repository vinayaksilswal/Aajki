"""Data access + serialization. Turns ORM rows into the dict shapes the frontend expects,
and provides the queries/mutations the admin console uses. Seeds the DB from seed.py once.
"""
from __future__ import annotations

import base64
import random
from datetime import datetime, timezone

from sqlalchemy import select, func, delete

from db import engine, Base, SessionLocal
from models import User, Topic, Poll, Vote, Comment, Story, Board, Setting
import seed as seeddata


# --- setup / seed --------------------------------------------------------------------------

def init_db(seed: bool = True):
    Base.metadata.create_all(engine)
    if not seed:
        return
    with SessionLocal() as s:
        if s.scalar(select(func.count()).select_from(Poll)):
            return  # already seeded
        _seed(s)
        s.commit()


def _seed(s):
    for t in seeddata.TOPICS:
        s.add(Topic(id=t["id"], slug=t["slug"], title=t["title"], short_label=t["short_label"],
                    blurb=t["blurb"], image_url=t["image_url"], category=t["category"]))
    for pid, p in seeddata.POLLS.items():
        s.add(Poll(
            id=p["id"], slug=p["slug"], category=p["category"], question=p["question"],
            description=p.get("description"), image_url=p.get("image_url"),
            display_kind=p["display_kind"], topic_id=p.get("topic_id"),
            trending=p.get("trending", False), is_prediction=p.get("is_prediction", False),
            reward_coins=(p.get("reward") or {}).get("coins", 5), status="open",
            like_count=p.get("like_count", 0),
            options=[{"key": o["id"], "label": o["label"], "emoji": o.get("emoji"),
                      "base_votes": o.get("votes", 0)} for o in p["options"]],
        ))
    for st in seeddata.STORIES:
        s.add(Story(id=st["id"], desk=st["desk"], hook=st["cover"]["hook"], data=st))
    for b in seeddata.BOARDS:
        s.add(Board(id=b["id"], title=b["title"], data=b))
    # A few demo users + votes + comments so the admin's audience view isn't empty.
    rnd = random.Random(7)
    names = ["Aarav", "Diya", "Kabir", "Meera", "Rohan", "Ananya", "Vikram", "Isha"]
    users = []
    for i in range(8):
        u = User(id=f"usr_demo{i}", phone=f"+9190000000{i:02d}", display_name=names[i],
                 handle=names[i].lower(), coins=rnd.randint(50, 500))
        users.append(u); s.add(u)
    poll_ids = list(seeddata.POLLS.keys())
    for _ in range(60):
        p = seeddata.POLLS[rnd.choice(poll_ids)]
        u = rnd.choice(users)
        s.add(Vote(poll_id=p["id"], user_id=u.id, option_key=rnd.choice(p["options"])["id"]))
    for _ in range(25):
        p = seeddata.POLLS[rnd.choice(poll_ids)]
        u = rnd.choice(users)
        s.add(Comment(poll_id=p["id"], user_id=u.id, author_name=u.display_name,
                      body=rnd.choice(["Called it.", "No way.", "Closer than it looks.", "Big if true."])))


# --- serialization -------------------------------------------------------------------------

def _vote_counts(s, poll_id: str) -> dict:
    rows = s.execute(select(Vote.option_key, func.count()).where(Vote.poll_id == poll_id)
                     .group_by(Vote.option_key)).all()
    return {k: c for k, c in rows}


def _comment_count(s, poll_id: str) -> int:
    return s.scalar(select(func.count()).select_from(Comment)
                    .where(Comment.poll_id == poll_id, Comment.hidden == False)) or 0  # noqa: E712


# Batch counts: one query each for a set of polls, to avoid N+1 round-trips to a remote DB.
def _batch_vote_counts(s, poll_ids: list[str]) -> dict:
    out: dict[str, dict] = {pid: {} for pid in poll_ids}
    if not poll_ids:
        return out
    rows = s.execute(select(Vote.poll_id, Vote.option_key, func.count())
                     .where(Vote.poll_id.in_(poll_ids)).group_by(Vote.poll_id, Vote.option_key)).all()
    for pid, key, c in rows:
        out.setdefault(pid, {})[key] = c
    return out


def _batch_comment_counts(s, poll_ids: list[str]) -> dict:
    out = {pid: 0 for pid in poll_ids}
    if not poll_ids:
        return out
    rows = s.execute(select(Comment.poll_id, func.count()).where(
        Comment.poll_id.in_(poll_ids), Comment.hidden == False).group_by(Comment.poll_id)).all()  # noqa: E712
    for pid, c in rows:
        out[pid] = c
    return out


def polls_to_dicts(s, polls: list) -> list[dict]:
    ids = [p.id for p in polls]
    vc = _batch_vote_counts(s, ids)
    cc = _batch_comment_counts(s, ids)
    return [poll_dict(s, p, vc.get(p.id), cc.get(p.id, 0)) for p in polls]


def poll_dict(s, p: Poll, counts: dict | None = None, ccount: int | None = None) -> dict:
    if counts is None:
        counts = _vote_counts(s, p.id)
    if ccount is None:
        ccount = _comment_count(s, p.id)
    options, total = [], 0
    for o in (p.options or []):
        v = (o.get("base_votes") or 0) + counts.get(o["key"], 0)
        total += v
        options.append({"id": o["key"], "label": o["label"], "emoji": o.get("emoji"), "votes": v})
    return {
        "id": p.id, "slug": p.slug, "category": p.category, "beat": p.category,
        "question": p.question, "description": p.description, "image_url": p.image_url,
        "display_kind": p.display_kind, "options": options, "total_votes": total,
        "my_vote": None, "like_count": p.like_count, "liked_by_me": False,
        "comment_count": ccount, "is_prediction": p.is_prediction,
        "trending": p.trending, "tags": [], "primary_topic_id": p.topic_id,
        "topic_id": p.topic_id, "status": p.status, "reward": {"coins": p.reward_coins},
    }


def topic_dict(t: Topic) -> dict:
    return {"id": t.id, "slug": t.slug, "title": t.title, "short_label": t.short_label,
            "blurb": t.blurb, "image_url": t.image_url, "category": t.category, "kind": "topic"}


# --- public reads --------------------------------------------------------------------------

def feed(cursor: str | None, page_size: int = 12) -> dict:
    with SessionLocal() as s:
        q = select(Poll).order_by(Poll.created_at.desc(), Poll.id)
        polls = s.scalars(q).all()
        start = 0
        if cursor:
            try:
                start = int(base64.urlsafe_b64decode(cursor.encode()).decode())
            except Exception:
                start = 0
        page = polls[start:start + page_size]
        nxt = start + page_size
        next_cursor = base64.urlsafe_b64encode(str(nxt).encode()).decode() if nxt < len(polls) else None
        return {"items": [{"type": "poll", "poll": d} for d in polls_to_dicts(s, page)],
                "next_cursor": next_cursor, "category": "trending",
                "as_of": datetime.now(timezone.utc).isoformat()}


def topics() -> dict:
    with SessionLocal() as s:
        return {"items": [topic_dict(t) for t in s.scalars(select(Topic).order_by(Topic.created_at)).all()]}


def topic(topic_id: str):
    with SessionLocal() as s:
        t = s.get(Topic, topic_id)
        if not t:
            return None
        polls = s.scalars(select(Poll).where(Poll.topic_id == topic_id).order_by(Poll.created_at)).all()
        return {**topic_dict(t), "polls": polls_to_dicts(s, polls),
                "answered_polls": [], "stories": [], "group_picks": [], "trivia": [],
                "sequence": [{"kind": "poll", "id": p.id} for p in polls], "curated": None, "leaderboard": None}


def home() -> dict:
    with SessionLocal() as s:
        ts = [topic_dict(t) for t in s.scalars(select(Topic).order_by(Topic.created_at)).all()]
    return {"topics": ts, "open_topic_ids": [t["id"] for t in ts], "daily_set": None,
            "onboarding": None, "balance": None, "daily_bonus_earned": False,
            "goal": {"label": "Vote on 10 polls today", "current": 3, "target": 10},
            "stories": [], "user_stories": [], "daily_remaining": 7,
            "as_of": datetime.now(timezone.utc).isoformat()}


def get_poll(poll_id: str):
    with SessionLocal() as s:
        p = s.get(Poll, poll_id)
        return poll_dict(s, p) if p else None


def poll_comments(poll_id: str) -> dict:
    with SessionLocal() as s:
        rows = s.scalars(select(Comment).where(Comment.poll_id == poll_id, Comment.hidden == False)  # noqa: E712
                         .order_by(Comment.created_at.desc())).all()
        return {"items": [{"id": c.id, "author": {"name": c.author_name}, "body": c.body,
                           "published_time": _ago(c.created_at), "vote_count": 0} for c in rows],
                "next_cursor": None}


def stories_daily() -> dict:
    with SessionLocal() as s:
        rows = s.scalars(select(Story).order_by(Story.published_at.desc())).all()
        return {"edition": datetime.now(timezone.utc).date().isoformat(),
                "stories": [r.data for r in rows], "next_cursor": None}


def leaderboards() -> dict:
    with SessionLocal() as s:
        rows = s.scalars(select(Board).order_by(Board.created_at)).all()
        boards = [r.data for r in rows]
    return {"boards": boards, "server_time": datetime.now(timezone.utc).isoformat(),
            "copy": {"subtitle": "Vote daily to climb the board and win gift cards."},
            "headline_monthly_paise": 4000000,
            "today_pool_paise": sum(b.get("campaign_pool_paise", 0) for b in boards) // 4}


def board(board_id: str):
    with SessionLocal() as s:
        b = s.get(Board, board_id)
        if not b:
            return None
        d = b.data
        return {"board": d, "frequencies": d.get("frequencies", []), "served": d.get("served"),
                "me_status": None, "server_time": datetime.now(timezone.utc).isoformat(),
                "recent_wins": d.get("recent_wins", [])}


# --- user actions --------------------------------------------------------------------------

def ensure_user(user_id: str, phone: str) -> dict:
    with SessionLocal() as s:
        u = s.get(User, user_id)
        if not u:
            u = User(id=user_id, phone=phone, display_name="Player", handle=None)
            s.add(u); s.commit()
        return {"id": u.id, "display_name": u.display_name, "handle": u.handle,
                "phone": u.phone, "coins": u.coins, "blocked": u.blocked}


def is_blocked(user_id: str) -> bool:
    with SessionLocal() as s:
        u = s.get(User, user_id)
        return bool(u and u.blocked)


def record_vote(poll_id: str, option_key: str, user_id: str | None):
    with SessionLocal() as s:
        if not s.get(Poll, poll_id):
            return False
        s.add(Vote(poll_id=poll_id, option_key=option_key, user_id=user_id))
        s.commit()
        return True


def wallet(user_id: str) -> dict:
    with SessionLocal() as s:
        u = s.get(User, user_id)
        bal = u.coins if u else 0
    return {"balance": bal, "entries": [
        {"title": "Welcome coins", "amount": 100, "kind": "signup"},
        {"title": "Daily bonus", "amount": 50, "kind": "bonus"}]}


def _ago(dt: datetime) -> str:
    if not dt:
        return ""
    secs = (datetime.now(timezone.utc) - dt.replace(tzinfo=dt.tzinfo or timezone.utc)).total_seconds()
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


# --- sentiment source ----------------------------------------------------------------------

def all_polls_for_sentiment() -> list[dict]:
    with SessionLocal() as s:
        return polls_to_dicts(s, s.scalars(select(Poll)).all())


# --- admin: polls --------------------------------------------------------------------------

def _ulid(prefix):
    import random as _r
    abc = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    return prefix + "_" + "".join(_r.choice(abc) for _ in range(26))


def admin_list_polls():
    with SessionLocal() as s:
        polls = s.scalars(select(Poll).order_by(Poll.created_at.desc())).all()
        dicts = polls_to_dicts(s, polls)
        return [{**d, "created_at": p.created_at} for p, d in zip(polls, dicts)]


def admin_get_poll(poll_id):
    with SessionLocal() as s:
        p = s.get(Poll, poll_id)
        if not p:
            return None
        return {"id": p.id, "question": p.question, "category": p.category,
                "description": p.description or "", "image_url": p.image_url or "",
                "display_kind": p.display_kind, "topic_id": p.topic_id or "",
                "trending": p.trending, "is_prediction": p.is_prediction,
                "reward_coins": p.reward_coins, "status": p.status,
                "options": p.options or []}


def admin_create_poll(question, category, options, image_url=None, description=None,
                      topic_id=None, display_kind="binary", trending=False,
                      is_prediction=False, reward_coins=5):
    with SessionLocal() as s:
        pid = _ulid("pl")
        slug = "-".join(question.lower().split()[:6]).strip("?.,") or pid[-6:]
        s.add(Poll(id=pid, slug=slug, category=category, question=question,
                   description=description, image_url=image_url, display_kind=display_kind,
                   topic_id=topic_id or None, trending=trending, is_prediction=is_prediction,
                   reward_coins=reward_coins, status="open", options=options))
        s.commit()
        return pid


def admin_update_poll(poll_id, **fields):
    with SessionLocal() as s:
        p = s.get(Poll, poll_id)
        if not p:
            return False
        for k, v in fields.items():
            if v is not None and hasattr(p, k):
                setattr(p, k, v)
        s.commit()
        return True


def admin_delete_poll(poll_id):
    with SessionLocal() as s:
        p = s.get(Poll, poll_id)
        if p:
            s.delete(p); s.commit()
        return bool(p)


def admin_set_status(poll_id, status):
    return admin_update_poll(poll_id, status=status)


# --- admin: topics -------------------------------------------------------------------------

def admin_list_topics():
    with SessionLocal() as s:
        out = []
        for t in s.scalars(select(Topic).order_by(Topic.created_at)).all():
            n = s.scalar(select(func.count()).select_from(Poll).where(Poll.topic_id == t.id))
            out.append({**topic_dict(t), "poll_count": n})
        return out


def admin_create_topic(title, category, short_label=None, blurb=None, image_url=None):
    with SessionLocal() as s:
        tid = _ulid("tpc")
        s.add(Topic(id=tid, slug="-".join(title.lower().split()), title=title,
                    short_label=short_label, blurb=blurb, image_url=image_url, category=category))
        s.commit()
        return tid


def admin_delete_topic(topic_id):
    with SessionLocal() as s:
        t = s.get(Topic, topic_id)
        if t:
            # detach polls so they aren't orphaned by FK
            for p in s.scalars(select(Poll).where(Poll.topic_id == topic_id)).all():
                p.topic_id = None
            s.delete(t); s.commit()
        return bool(t)


# --- admin: comments -----------------------------------------------------------------------

def admin_list_comments(limit=200):
    with SessionLocal() as s:
        rows = s.scalars(select(Comment).order_by(Comment.created_at.desc()).limit(limit)).all()
        pids = list({c.poll_id for c in rows})
        qmap = dict(s.execute(select(Poll.id, Poll.question).where(Poll.id.in_(pids))).all()) if pids else {}
        return [{"id": c.id, "author_name": c.author_name, "body": c.body, "hidden": c.hidden,
                 "poll_id": c.poll_id, "poll_q": (qmap.get(c.poll_id, "(deleted)") or "")[:60],
                 "created_at": c.created_at} for c in rows]


def admin_set_comment_hidden(comment_id, hidden):
    with SessionLocal() as s:
        c = s.get(Comment, int(comment_id))
        if c:
            c.hidden = hidden; s.commit()
        return bool(c)


def admin_delete_comment(comment_id):
    with SessionLocal() as s:
        c = s.get(Comment, int(comment_id))
        if c:
            s.delete(c); s.commit()
        return bool(c)


# --- admin: users / audience ---------------------------------------------------------------

def admin_list_users():
    with SessionLocal() as s:
        users = s.scalars(select(User).order_by(User.created_at.desc())).all()
        vc = dict(s.execute(select(Vote.user_id, func.count()).group_by(Vote.user_id)).all())
        return [{"id": u.id, "display_name": u.display_name, "handle": u.handle,
                 "phone": u.phone, "coins": u.coins, "blocked": u.blocked,
                 "votes": vc.get(u.id, 0), "created_at": u.created_at} for u in users]


def admin_set_user_blocked(user_id, blocked):
    with SessionLocal() as s:
        u = s.get(User, user_id)
        if u:
            u.blocked = blocked; s.commit()
        return bool(u)


def admin_stats():
    with SessionLocal() as s:
        polls, open_polls = s.execute(select(
            func.count(), func.count().filter(Poll.status == "open")).select_from(Poll)).one()
        users, blocked = s.execute(select(
            func.count(), func.count().filter(User.blocked == True)).select_from(User)).one()  # noqa: E712
        topics = s.scalar(select(func.count()).select_from(Topic)) or 0
        votes = s.scalar(select(func.count()).select_from(Vote)) or 0
        comments = s.scalar(select(func.count()).select_from(Comment)) or 0
        return {"polls": polls, "open_polls": open_polls, "topics": topics, "users": users,
                "blocked": blocked, "votes": votes, "comments": comments}


def add_comment(poll_id: str, body: str, user_id=None, author_name="User"):
    body = (body or "").strip()[:1000]
    if not body:
        return None
    with SessionLocal() as s:
        if not s.get(Poll, poll_id):
            return None
        name = author_name
        if user_id:
            u = s.get(User, user_id)
            if u:
                if u.blocked:
                    return False
                name = u.display_name
        c = Comment(poll_id=poll_id, user_id=user_id, author_name=name, body=body)
        s.add(c); s.commit()
        return {"id": c.id, "author": {"name": c.author_name}, "body": c.body,
                "published_time": "just now", "vote_count": 0}


def question_exists(question: str) -> bool:
    q = (question or "").strip()
    with SessionLocal() as s:
        return s.scalar(select(func.count()).select_from(Poll).where(Poll.question == q)) > 0


def create_poll_if_new(args: dict):
    """Create a poll unless one with the same question already exists. Returns id or None."""
    if not args.get("question") or question_exists(args["question"]):
        return None
    return admin_create_poll(**args)


def existing_questions(questions: list[str]) -> set:
    qs = [q for q in questions if q]
    if not qs:
        return set()
    with SessionLocal() as s:
        rows = s.scalars(select(Poll.question).where(Poll.question.in_(qs))).all()
    return set(rows)
