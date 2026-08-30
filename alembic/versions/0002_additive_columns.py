"""additive columns: total_cache_read on conversations + sessions, sessions.deleted_at

Revision ID: 0002_additive_columns
Revises: 0001_initial
Create Date: 2026-05-27

Wraps `_apply_additive_columns` from `library.db.bootstrap`. The
helper is defensive: each ALTER runs only when the target column is
missing, so the revision is safe against DBs where bootstrap already
applied these mutations.
"""
from __future__ import annotations

from alembic import op

from library.db.bootstrap import _apply_additive_columns


revision = "0002_additive_columns"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _apply_additive_columns(op.get_bind())


def downgrade() -> None:
    """Irreversible: this migration adds columns to existing tables.

    Reverting means dropping those columns, which discards whatever has been written to them since. SQLite has no DROP COLUMN either, so the table would have to be rebuilt.

    Raising is deliberate. A silent no-op here returns success while
    leaving the schema at the newer shape, so alembic_version and the
    actual database disagree with nothing to signal it — and the next
    upgrade then re-runs this migration against a database that already
    has its changes.
    """
    raise NotImplementedError(
        "0002_additive_columns cannot be downgraded automatically. "
        "To roll back: drop the columns by hand, then stamp the target revision."
    )
