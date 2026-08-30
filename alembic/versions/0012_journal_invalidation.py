"""add journal contradiction invalidation columns

Revision ID: 0012_journal_invalidation
Revises: 0011_postgres_metadata_fts
Create Date: 2026-06-10

Adds nullable invalidation metadata to journal rows. The helper is
idempotent so this revision is safe on databases where startup bootstrap
has already applied the same additive columns and index.
"""
from __future__ import annotations

from alembic import op

from library.db.bootstrap import _ensure_journal_invalidation


revision = "0012_journal_invalidation"
down_revision = "0011_postgres_metadata_fts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _ensure_journal_invalidation(op.get_bind())


def downgrade() -> None:
    """Irreversible: this migration adds the journal invalidation columns.

    Dropping them discards the record of why older notes were hidden from active recall — audit history that cannot be reconstructed.

    Raising is deliberate. A silent no-op here returns success while
    leaving the schema at the newer shape, so alembic_version and the
    actual database disagree with nothing to signal it — and the next
    upgrade then re-runs this migration against a database that already
    has its changes.
    """
    raise NotImplementedError(
        "0012_journal_invalidation cannot be downgraded automatically. "
        "To roll back: drop the columns by hand if you accept losing that history, then stamp the target revision."
    )
