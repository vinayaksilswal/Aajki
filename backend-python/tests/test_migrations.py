"""Migrations: prototype data moves to the Phase 1 model as documented."""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
from alembic import command

from tests.conftest import alembic_config


def test_prototype_rows_become_reviewable_drafts_with_spec_categories():
    db = Path(tempfile.mkdtemp(prefix="bf-mig-")) / "proto.db"
    engine = sa.create_engine(f"sqlite:///{db.as_posix()}")
    cfg = alembic_config()
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0001_baseline")
        conn.execute(sa.text(
            "INSERT INTO polls (id, slug, category, question, display_kind, options, trending, "
            "is_prediction, reward_coins, status, like_count, created_at) VALUES "
            "(:id, 's', :cat, 'Old question?', 'binary', :opts, 0, 0, 5, 'open', 3, :now)"),
            [{"id": "pl_1", "cat": "politics", "now": now,
              "opts": '[{"key":"yes","label":"Yes","emoji":"x","base_votes":120},'
                      '{"key":"no","label":"No","emoji":null,"base_votes":80}]'},
             {"id": "pl_2", "cat": "cricket", "now": now, "opts": '[]'},
             {"id": "pl_3", "cat": "unknown", "now": now, "opts": '[]'}])
        command.upgrade(cfg, "head")
        rows = {r.id: r for r in conn.execute(sa.text("SELECT id, category, status, options FROM polls"))}
        cols = {c["name"] for c in sa.inspect(conn).get_columns("polls")}
    engine.dispose()

    assert {i: (r.category, r.status) for i, r in rows.items()} == {
        "pl_1": ("policy", "draft"), "pl_2": ("sports", "draft"), "pl_3": ("community", "draft")}
    assert '"base_votes"' not in rows["pl_1"].options and '"label": "Yes"' in rows["pl_1"].options
    assert {"resolution_source_url", "closes_at", "election_sensitive"} <= cols
    assert not {"reward_coins", "is_prediction", "like_count", "display_kind"} & cols
