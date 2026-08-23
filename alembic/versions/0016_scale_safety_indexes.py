"""indexes for stable pagination and bounded retention

Revision ID: 0016_scale_safety_indexes
Revises: 0015_agent_events
Create Date: 2026-08-20
"""
from __future__ import annotations

from alembic import op

from library.db.bootstrap import (
    SCALE_SAFETY_INDEXES,
    _ensure_scale_safety_indexes,
)

revision = "0016_scale_safety_indexes"
down_revision = "0015_agent_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _ensure_scale_safety_indexes(op.get_bind())


def downgrade() -> None:
    for index_name, _table_name, _columns in reversed(SCALE_SAFETY_INDEXES):
        op.execute(f'DROP INDEX IF EXISTS "{index_name}"')
