"""Baseline: the schema the prototype created with metadata.create_all().

An existing prototype database already has these tables: mark it with
`alembic stamp 0001_baseline` instead of running this migration. A fresh database runs it.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("handle", sa.String(40), nullable=True),
        sa.Column("coins", sa.Integer, nullable=False),
        sa.Column("blocked", sa.Boolean, nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_users_phone", "users", ["phone"])

    op.create_table(
        "topics",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("short_label", sa.String(120), nullable=True),
        sa.Column("blurb", sa.Text, nullable=True),
        sa.Column("image_url", sa.Text, nullable=True),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_topics_category", "topics", ["category"])

    op.create_table(
        "polls",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("slug", sa.String(160), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("image_url", sa.Text, nullable=True),
        sa.Column("display_kind", sa.String(20), nullable=False),
        sa.Column("options", sa.JSON, nullable=False),
        sa.Column("topic_id", sa.String(40), sa.ForeignKey("topics.id"), nullable=True),
        sa.Column("trending", sa.Boolean, nullable=False),
        sa.Column("is_prediction", sa.Boolean, nullable=False),
        sa.Column("reward_coins", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("like_count", sa.Integer, nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_polls_category", "polls", ["category"])
    op.create_index("ix_polls_topic_id", "polls", ["topic_id"])

    op.create_table(
        "votes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("poll_id", sa.String(40), sa.ForeignKey("polls.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("user_id", sa.String(40), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("option_key", sa.String(40), nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_votes_poll_id", "votes", ["poll_id"])
    op.create_index("ix_votes_user_id", "votes", ["user_id"])

    op.create_table(
        "comments",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("poll_id", sa.String(40), sa.ForeignKey("polls.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("user_id", sa.String(40), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("author_name", sa.String(80), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("hidden", sa.Boolean, nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_comments_poll_id", "comments", ["poll_id"])

    # Prototype-only tables (daily stories, prize boards, settings). No longer mapped by the
    # app; kept so existing data is not dropped without a deliberate decision.
    op.create_table(
        "stories",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("desk", sa.String(60), nullable=False),
        sa.Column("hook", sa.Text, nullable=False),
        sa.Column("data", sa.JSON, nullable=False),
        sa.Column("published_at", TS, nullable=False),
    )
    op.create_table(
        "boards",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("data", sa.JSON, nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_table(
        "settings",
        sa.Column("key", sa.String(60), primary_key=True),
        sa.Column("value", sa.JSON, nullable=False),
    )


def downgrade() -> None:
    for table in ("settings", "boards", "stories", "comments", "votes", "polls", "topics", "users"):
        op.drop_table(table)
