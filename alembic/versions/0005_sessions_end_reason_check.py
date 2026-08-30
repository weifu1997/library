"""sessions.end_reason: extend CHECK to include newer enum values

Revision ID: 0005_sessions_end_reason_check
Revises: 0004_repair_dangling_file_entries_fks
Create Date: 2026-05-27

Wraps `_relax_sessions_end_reason_check`. SQLite has no
`ALTER TABLE … DROP CONSTRAINT`, so the helper rebuilds `sessions`
when the live CHECK is older than `enums.SESSION_END_REASONS`.
"""
from __future__ import annotations

from alembic import op

from library.db.bootstrap import _relax_sessions_end_reason_check


revision = "0005_sessions_end_reason_check"
down_revision = "0004_repair_dangling_file_entries_fks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _relax_sessions_end_reason_check(op.get_bind())


def downgrade() -> None:
    """Irreversible: this migration relaxes the sessions.end_reason CHECK constraint.

    Restoring the narrower constraint fails if any session has since been written with one of the newly-allowed values.

    Raising is deliberate. A silent no-op here returns success while
    leaving the schema at the newer shape, so alembic_version and the
    actual database disagree with nothing to signal it — and the next
    upgrade then re-runs this migration against a database that already
    has its changes.
    """
    raise NotImplementedError(
        "0005_sessions_end_reason_check cannot be downgraded automatically. "
        "To roll back: reconcile the offending end_reason values, restore the old CHECK, then stamp the target revision."
    )
