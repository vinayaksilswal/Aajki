"""In-memory seed data for the Aajki backend — original sample content, no external calls.

Shapes match what the frontend reads (see ../ENDPOINTS.md). Data is deterministic so IDs
stay stable across restarts/cold-starts, which keeps the frontend's links valid.
Replace this module with a real database layer when you're ready.
"""
from __future__ import annotations

import random
from datetime import datetime, timezone, timedelta

random.seed(1729)

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _ulid(prefix: str) -> str:
    return prefix + "_" + "".join(random.choice(_ALPHABET) for _ in range(26))


def _img(slug: str, w: int = 800, h: int = 450) -> str:
    # Stable placeholder image per slug (same provider the original app used).
    return f"https://picsum.photos/seed/{slug}/{w}/{h}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Topics and their polls, by category ---------------------------------------------------

_CATEGORY_TOPICS = {
    "politics": ("The State of the Union", "Policy & Power",
                 "Budgets, bills and ballot math — the decisions shaping the year ahead."),
    "movies":   ("This Season at the Movies", "Box Office Watch",
                 "Releases, reviews and the races everyone's arguing about."),
    "cricket":  ("The Cricket Room", "Match Pulse",
                 "Selections, run chases and the calls that decide a series."),
    "tech":     ("Tech, Decoded", "Silicon & Software",
                 "Launches, outages and the bets big tech is making."),
    "money":    ("Markets & Money", "Your Wallet",
                 "Rates, prices and the moves that hit everyday budgets."),
}

# A few question templates per category to generate plausible binary + multi polls.
_BINARY_QS = {
    "politics": [
        "Will the new budget pass before the deadline?",
        "Should the fuel subsidy be extended another year?",
        "Will voter turnout beat the last election?",
    ],
    "movies": [
        "Will this weekend's release cross ₹100 crore?",
        "Does the sequel live up to the original?",
        "Will the lead win an award for this role?",
    ],
    "cricket": [
        "Will the openers put on a century stand?",
        "Should the captain bat first if they win the toss?",
        "Will the series be decided before the final match?",
    ],
    "tech": [
        "Will the new phone outsell last year's model?",
        "Is the AI feature actually useful day to day?",
        "Will the outage hurt the company's next results?",
    ],
    "money": [
        "Will the central bank cut rates this quarter?",
        "Is gold a better buy than stocks right now?",
        "Will petrol prices rise before the festival season?",
    ],
}
_MULTI = {
    "politics": ("Which issue will decide the next election?",
                 ["Jobs", "Prices", "Healthcare", "Security"]),
    "movies": ("What makes you pick a movie on opening night?",
               ["The cast", "The trailer", "Reviews", "The director"]),
    "cricket": ("What wins a modern ODI?",
                ["Top-order runs", "Death bowling", "Fielding", "Spin in the middle"]),
    "tech": ("What matters most in a new phone?",
             ["Battery", "Camera", "Price", "Software updates"]),
    "money": ("Where would you put ₹10,000 today?",
              ["Index fund", "Fixed deposit", "Gold", "Savings"]),
}

TOPICS: list[dict] = []
POLLS: dict[str, dict] = {}
_TOPIC_POLLS: dict[str, list[str]] = {}


def _make_poll(category: str, topic_id: str, question: str, options: list[dict],
               display_kind: str, trending: bool = False) -> dict:
    pid = _ulid("pl")
    slug = "-".join(question.lower().split()[:6]).strip("?.,")
    total = sum(o["votes"] for o in options)
    poll = {
        "id": pid, "slug": slug, "category": category, "beat": category,
        "subcategory_key": None, "path_key": None,
        "question": question, "description": None,
        "image_url": _img(pid[-8:]),
        "display_kind": display_kind, "layout": None,
        "options": options,
        "total_votes": total, "my_vote": None,
        "like_count": random.randint(0, 240), "liked_by_me": False,
        "comment_count": random.randint(0, 40),
        "is_prediction": display_kind == "binary" and random.random() < 0.4,
        "show_friends": False, "trending": trending, "tags": [],
        "primary_topic_id": topic_id, "topic_id": topic_id,
        "reward": {"coins": 5},
    }
    POLLS[pid] = poll
    _TOPIC_POLLS.setdefault(topic_id, []).append(pid)
    return poll


def _binary_options() -> list[dict]:
    yes = random.randint(20, 900)
    no = random.randint(20, 900)
    return [
        {"id": "yes", "label": "Yes", "emoji": None, "votes": yes},
        {"id": "no", "label": "No", "emoji": None, "votes": no},
    ]


def _multi_options(labels: list[str]) -> list[dict]:
    return [
        {"id": f"opt{i+1}", "label": lab, "emoji": None, "votes": random.randint(10, 600)}
        for i, lab in enumerate(labels)
    ]


for cat, (title, short, blurb) in _CATEGORY_TOPICS.items():
    tid = _ulid("tpc")
    TOPICS.append({
        "id": tid, "slug": "-".join(title.lower().split()),
        "title": title, "short_label": short, "blurb": blurb,
        "image_url": _img(tid[-8:]), "category": cat,
        "subcategory_key": None, "path_key": None, "kind": "topic",
        "parent_id": None, "provider": "aajki", "voice": None, "list_mode": "feed",
    })
    for i, q in enumerate(_BINARY_QS[cat]):
        _make_poll(cat, tid, q, _binary_options(), "binary", trending=(i == 0))
    mq, mlabels = _MULTI[cat]
    _make_poll(cat, tid, mq, _multi_options(mlabels), "multi")

ALL_POLL_IDS = list(POLLS.keys())
random.shuffle(ALL_POLL_IDS)  # a mixed "trending" feed order


# --- Comments ------------------------------------------------------------------------------

_NAMES = ["Aarav", "Diya", "Kabir", "Meera", "Rohan", "Ananya", "Vikram", "Isha", "Arjun", "Sara"]
_COMMENTS = [
    "Called it last week.", "No way this happens.", "The numbers don't add up.",
    "Totally agree with the top option.", "This one's closer than people think.",
    "Changed my vote after reading the thread.", "Big if true.", "Classic overreaction.",
]


def comments_for(poll_id: str) -> list[dict]:
    poll = POLLS.get(poll_id)
    if not poll:
        return []
    n = min(poll["comment_count"], 8)
    rnd = random.Random(poll_id)
    out = []
    for i in range(n):
        out.append({
            "id": f"cmt_{poll_id[-6:]}_{i}",
            "author": {"name": rnd.choice(_NAMES)},
            "body": rnd.choice(_COMMENTS),
            "published_time": "2h ago",
            "vote_count": rnd.randint(0, 50),
        })
    return out


# --- Daily stories -------------------------------------------------------------------------

def _story(desk: str, hook: str, sections: list[tuple[str, str]], questions: list[tuple[str, bool]]) -> dict:
    sid = _ulid("dst")
    q_objs = []
    rnd = random.Random(sid)
    for qtext, _ in questions:
        yes = rnd.randint(1, 100)
        q_objs.append({
            "id": _ulid("pl"), "kind": "verdict", "question": qtext,
            "options": [
                {"id": "yes", "label": "Yes", "pct": yes, "icon": "check"},
                {"id": "no", "label": "No", "pct": 100 - yes, "icon": "cross"},
            ],
            "total_votes": rnd.randint(5, 400), "reward_coins": 5,
            "settles_on": None, "closes_at": None, "closed": False,
            "my_option_id": None, "format": "poll", "correct_option_id": None,
        })
    return {
        "id": sid, "path": desk, "desk": desk, "shelf": desk,
        "subcategory_key": None, "edition_day": _today(),
        "published_at": _now(),
        "cover": {"image_key": _img(sid[-8:], 1080, 1080), "alt": hook, "hook": hook,
                  "style": {"font": "geometric", "tone": "base", "pattern": "stripes"},
                  "ratio": "square", "wide_key": _img(sid[-8:] + "w", 1200, 630)},
        "context": [
            {"label": label, "body": body,
             "visual": {"kind": "illustration", "image_key": _img(f"{sid[-6:]}{i}"), "alt": label}}
            for i, (label, body) in enumerate(sections)
        ],
        "questions": q_objs,
        "share_url": f"https://aajki.app/s/{sid[-8:]}",
        "relevance": None, "share_hint": "Share with the group chat.",
    }


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


STORIES = [
    _story("money_work",
           "Rates held steady, but your EMI math just changed",
           [("What happened", "The central bank kept the benchmark rate unchanged for a third straight review, citing sticky food prices."),
            ("Why it matters", "Floating-rate loans won't fall yet, but banks are quietly trimming fixed-deposit returns."),
            ("What's next", "Economists are split on whether the next move is a cut or a long pause.")],
           [("Will the next move be a rate cut?", True), ("Is now a good time to lock a fixed deposit?", True)]),
    _story("tech_world",
           "A big outage, and a bigger question about who holds the keys",
           [("What happened", "A configuration error took a major cloud provider offline for hours, stalling apps worldwide."),
            ("Why it's strange", "The same provider powers many of its own competitors, so rivals went down together."),
            ("What's going on", "Regulators are asking whether too much of the internet leans on too few companies.")],
           [("Should critical services run on a single cloud?", True), ("Will this change anyone's provider?", True)]),
    _story("sport_room",
           "A selection gamble that could define the series",
           [("What happened", "Selectors dropped a senior batter for an uncapped all-rounder ahead of the decider."),
            ("The debate", "Form says yes, experience says wait — the dressing room reportedly disagrees."),
            ("The stakes", "Win and it's a masterstroke; lose and the questions write themselves.")],
           [("Was dropping the senior batter the right call?", True), ("Will the all-rounder score 30+?", True)]),
]


# --- Leaderboards --------------------------------------------------------------------------

def _board(title: str, pitch: str, pool_paise: int, players: int, day: int) -> dict:
    bid = _ulid("lb")
    rnd = random.Random(bid)
    now = datetime.now(timezone.utc)
    wins = []
    tiers = [("Gold", 1, 50000), ("Silver", 2, 20000), ("Bronze", 3, 10000)]
    for i in range(12):
        name, tier, paise = tiers[i % 3]
        wins.append({
            "name": rnd.choice(_NAMES) + " " + rnd.choice("KSRMPT") + ".",
            "tier": tier, "tier_name": name,
            "prize_each_paise": paise, "prize_line": f"₹{paise // 100}",
            "round_id": _ulid("lbr"),
            "won_at": (now - timedelta(days=rnd.randint(0, 5))).isoformat(),
        })
    board = {
        "id": bid, "title": title, "scope": {"kind": "app", "label": "Entire app"},
        "status": "live", "accent": None, "prize_art": "prize:gift",
        "starts_on": (now - timedelta(days=day)).date().isoformat(),
        "ends_on": (now + timedelta(days=7 - day)).date().isoformat(),
        "campaign_pool_paise": pool_paise, "campaign_line": pitch,
        "headline_monthly_paise": pool_paise * 4, "min_players": 10,
        "served": {"frequency_id": _ulid("lbq"), "frequency": "daily", "label": "Daily draw",
                   "round_id": _ulid("lbr"), "round_label": f"Day {day}", "state": "live",
                   "opens_at": (now - timedelta(hours=6)).isoformat(),
                   "closes_at": (now + timedelta(hours=18)).isoformat(),
                   "pitch": pitch, "players": players, "cancellation": None,
                   "draw_at": (now + timedelta(hours=18)).isoformat()},
        "recent_wins": wins,
        "frequencies": [{"id": _ulid("lbq"), "frequency": "daily", "label": "Daily draw"}],
    }
    return board


BOARDS = [
    _board("Daily Draw", "Gift cards worth up to ₹500 each", 350000, 128, 3),
    _board("Weekend Special", "Win from a ₹10,000 weekend pool", 1000000, 64, 2),
]

APP_CONFIG = {
    "min_supported_build": 1, "latest_build": 1,
    "store_urls": {"ios": "", "android": ""},
    "app_icon": None,
    "reward_frame": {"enabled": True, "coin_target": 500,
                     "progress_suffix": "/500 Coins", "title": "You hit 500 coins!"},
    "phone_step_required": True,
}
