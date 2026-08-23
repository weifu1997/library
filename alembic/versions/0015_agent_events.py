"""durable public chat-event ledger

Revision ID: 0015_agent_events
Revises: 0014_files_kind_check
Create Date: 2026-08-20
"""
from __future__ import annotations

from alembic import op

from library.db.bootstrap import _ensure_agent_events

revision = "0015_agent_events"
down_revision = "0014_files_kind_check"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _ensure_agent_events(op.get_bind())


def downgrade() -> None:
    op.drop_table("agent_events")
