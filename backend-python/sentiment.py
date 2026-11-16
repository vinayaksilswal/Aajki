"""Sentiment engine (Python port) — BACKEND ONLY.

Two signals per poll: question-wording tone (lexicon) and crowd leaning (vote split),
blended into a category/overall "public mood". No external NLP service.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

POSITIVE = {
    "win", "wins", "winning", "won", "best", "great", "good", "strong", "surge", "boost",
    "rise", "rises", "rising", "grow", "growth", "gain", "gains", "success", "record",
    "top", "lead", "leads", "hit", "hope", "hopeful", "confident", "improve", "support",
    "love", "happy", "celebrate", "reward", "historic", "breakthrough", "deal", "agree",
    "approve", "safe", "safer", "rescue", "recover", "recovery", "peace", "trust", "worth",
}
NEGATIVE = {
    "lose", "loses", "lost", "worst", "bad", "weak", "fall", "falls", "drop", "drops",
    "crash", "crisis", "fail", "fails", "failure", "fear", "fears", "risk", "risks", "risky",
    "concern", "concerned", "worried", "worry", "threat", "ban", "cut", "cuts", "death",
    "war", "attack", "fight", "scandal", "fraud", "probe", "resign", "delay", "wrong",
    "danger", "protest", "strike", "crime", "arrest", "collapse", "sue", "quit", "block",
}
NEGATORS = {"not", "no", "never", "without", "wont", "cant"}


def _tokens(text: str) -> list[str]:
    return [t for t in "".join(c.lower() if (c.isalnum() or c in " '-") else " "
                                for c in (text or "")).split() if t]


def question_tone(text: str) -> dict:
    toks = _tokens(text)
    score = 0
    hits = 0
    for i, w in enumerate(toks):
        s = 1 if w in POSITIVE else -1 if w in NEGATIVE else 0
        if s:
            if i > 0 and toks[i - 1] in NEGATORS:
                s = -s
            score += s
            hits += 1
    if not hits:
        return {"score": 0.0, "label": "neutral", "hits": 0}
    norm = max(-1.0, min(1.0, score / math.sqrt(hits)))
    label = "positive" if norm > 0.15 else "negative" if norm < -0.15 else "neutral"
    return {"score": round(norm, 3), "label": label, "hits": hits}


def crowd_leaning(poll: dict) -> dict:
    opts = poll.get("options") or []
    weights = [(o.get("votes") if o.get("votes") is not None else o.get("pct") or 0) for o in opts]
    total_votes = poll.get("total_votes") or sum(weights) or 0
    s = sum(weights) or 1
    p = [w / s for w in weights]
    entropy = -sum(x * math.log2(x) for x in p if x > 0)
    max_ent = math.log2(len(opts)) if len(opts) > 1 else 1
    consensus = round(1 - entropy / max_ent, 3) if max_ent else 1.0

    optimism = None
    yes = next((o for o in opts if o.get("id") == "yes"), None)
    no = next((o for o in opts if o.get("id") == "no"), None)
    if yes and no:
        y = (yes.get("votes") if yes.get("votes") is not None else yes.get("pct") or 0) / s
        optimism = round(y * 2 - 1, 3)
    leader = max(opts, key=lambda o: (o.get("votes") if o.get("votes") is not None else o.get("pct") or 0), default=None)
    return {
        "total_votes": total_votes, "consensus": consensus, "optimism": optimism,
        "divisive": consensus < 0.25,
        "leader": ({"id": leader["id"], "label": leader["label"]} if leader else None),
    }


def analyze_poll(poll: dict) -> dict:
    tone = question_tone(poll.get("question", ""))
    crowd = crowd_leaning(poll)
    parts = [tone["score"]] + ([crowd["optimism"]] if crowd["optimism"] is not None else [])
    mood = round(sum(parts) / len(parts), 3)
    return {
        "id": poll.get("id"), "question": poll.get("question"),
        "category": poll.get("category") or poll.get("beat") or "other",
        "tone": tone, "crowd": crowd, "mood": mood,
        "mood_label": "positive" if mood > 0.15 else "negative" if mood < -0.15 else "neutral",
        "engagement": (poll.get("total_votes") or crowd["total_votes"] or 0) + (poll.get("comment_count") or 0) * 3,
    }


def _avg(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def analyze_set(polls: list[dict]) -> dict:
    records = [analyze_poll(p) for p in polls if p and p.get("question")]
    by_cat: dict[str, list[dict]] = {}
    for r in records:
        by_cat.setdefault(r["category"], []).append(r)

    categories = []
    for cat, rs in by_cat.items():
        opt = [r["crowd"]["optimism"] for r in rs if r["crowd"]["optimism"] is not None]
        categories.append({
            "category": cat, "count": len(rs),
            "mood": round(_avg([r["mood"] for r in rs]), 3),
            "optimism": round(_avg(opt), 3),
            "consensus": round(_avg([r["crowd"]["consensus"] for r in rs]), 3),
            "total_votes": sum(r["crowd"]["total_votes"] or 0 for r in rs),
            "positive": sum(1 for r in rs if r["mood_label"] == "positive"),
            "negative": sum(1 for r in rs if r["mood_label"] == "negative"),
            "neutral": sum(1 for r in rs if r["mood_label"] == "neutral"),
        })
    categories.sort(key=lambda c: -c["count"])
    s = sorted(records, key=lambda r: -r["mood"])
    divisive = sorted([r for r in records if r["crowd"]["divisive"]], key=lambda r: r["crowd"]["consensus"])
    opt_all = [r["crowd"]["optimism"] for r in records if r["crowd"]["optimism"] is not None]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_polls": len(records),
        "total_votes": sum(r["crowd"]["total_votes"] or 0 for r in records),
        "overall_mood": round(_avg([r["mood"] for r in records]), 3),
        "overall_optimism": round(_avg(opt_all), 3),
        "distribution": {
            "positive": sum(1 for r in records if r["mood_label"] == "positive"),
            "neutral": sum(1 for r in records if r["mood_label"] == "neutral"),
            "negative": sum(1 for r in records if r["mood_label"] == "negative"),
        },
        "categories": categories,
        "most_positive": s[:5],
        "most_negative": list(reversed(s[-5:])),
        "most_divisive": divisive[:5],
        "most_engaged": sorted(records, key=lambda r: -r["engagement"])[:5],
    }
