"""Phase 1 question model and the news ticker.

- Questions gain a publish window, a resolution source and rule, and an
  election-sensitive flag. Prototype-only columns (display kind, prediction flag,
  per-poll coin reward, like count) are dropped.
- Categories move to the spec's six. Every existing question becomes a draft: none has
  a resolution source yet, and the spec forbids opening a question without one.
- Fabricated `base_votes` and emoji are stripped from outcomes, so the consensus shown
  in the app comes only from real participation.
- New table news_items backs the context ticker.

The data changes (status, categories, outcome cleanup) are one-way; downgrade restores
the columns but not the previous values.

Revision ID: 0002_phase1_questions_news
Revises: 0001_baseline
Create Date: 2026-11-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_phase1_questions_news"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)
SPEC_CATEGORIES = {"elections", "markets", "sports", "policy", "world", "community"}
# Prototype categories -> spec categories. Admins review every migrated draft anyway.
CATEGORY_MAP = {"politics": "policy", "money": "markets", "business": "markets",
                "cricket": "sports", "sport": "sports", "tech": "world",
                "movies": "community", "entertainment": "community"}


def upgrade() -> None:
    with op.batch_alter_table("polls") as b:
        b.add_column(sa.Column("opens_at", TS, nullable=True))
        b.add_column(sa.Column("closes_at", TS, nullable=True))
        b.add_column(sa.Column("resolution_source_url", sa.Text, nullable=True))
        b.add_column(sa.Column("resolution_rule", sa.Text, nullable=True))
        b.add_column(sa.Column("election_sensitive", sa.Boolean, nullable=False,
                               server_default=sa.false()))
        b.add_column(sa.Column("source_headline", sa.Text, nullable=True))
        b.add_column(sa.Column("source_link", sa.Text, nullable=True))
        b.add_column(sa.Column("updated_at", TS, nullable=True))
        b.drop_column("display_kind")
        b.drop_column("is_prediction")
        b.drop_column("reward_coins")
        b.drop_column("like_count")
    op.create_index("ix_polls_status_closes_at", "polls", ["status", "closes_at"])

    polls = sa.table("polls", sa.column("id", sa.String), sa.column("category", sa.String),
                     sa.column("status", sa.String), sa.column("options", sa.JSON))
    conn = op.get_bind()
    for pid, category, options in conn.execute(
            sa.select(polls.c.id, polls.c.category, polls.c.options)).all():
        cat = (category or "").lower()
        cat = cat if cat in SPEC_CATEGORIES else CATEGORY_MAP.get(cat, "community")
        outcomes = [{"key": str(o.get("key") or o.get("id")), "label": str(o.get("label") or "")}
                    for o in (options or []) if isinstance(o, dict)]
        conn.execute(polls.update().where(polls.c.id == pid)
                     .values(category=cat, status="draft", options=outcomes))

    op.create_table(
        "news_items",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("source", sa.String(200), nullable=False),
        sa.Column("link", sa.Text, nullable=False),
        sa.Column("link_hash", sa.String(64), nullable=False),
        sa.Column("published_at", TS, nullable=True),
        sa.Column("fetched_at", TS, nullable=False),
        sa.Column("question_id", sa.String(40), nullable=True),
        sa.Column("hidden", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["question_id"], ["polls.id"], ondelete="SET NULL",
                                name="fk_news_items_question_id_polls"),
        sa.UniqueConstraint("link_hash", name="uq_news_items_link_hash"),
    )
    op.create_index("ix_news_items_category", "news_items", ["category"])
    op.create_index("ix_news_items_fetched_at", "news_items", ["fetched_at"])


def downgrade() -> None:
    op.drop_index("ix_news_items_fetched_at", table_name="news_items")
    op.drop_index("ix_news_items_category", table_name="news_items")
    op.drop_table("news_items")
    op.drop_index("ix_polls_status_closes_at", table_name="polls")
    with op.batch_alter_table("polls") as b:
        b.add_column(sa.Column("display_kind", sa.String(20), nullable=False, server_default="binary"))
        b.add_column(sa.Column("is_prediction", sa.Boolean, nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("reward_coins", sa.Integer, nullable=False, server_default="0"))
        b.add_column(sa.Column("like_count", sa.Integer, nullable=False, server_default="0"))
        for col in ("updated_at", "source_link", "source_headline", "election_sensitive",
                    "resolution_rule", "resolution_source_url", "closes_at", "opens_at"):
            b.drop_column(col)
