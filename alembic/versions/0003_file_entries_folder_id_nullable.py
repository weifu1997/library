"""file_entries.folder_id: drop NOT NULL on existing SQLite DBs

Revision ID: 0003_file_entries_folder_id_nullable
Revises: 0002_additive_columns
Create Date: 2026-05-27

Wraps `_relax_file_entries_folder_id_nullable`. SQLite-only: the helper
rebuilds the table when the live schema still has NOT NULL on
folder_id; on Postgres it's a no-op (operators drop the constraint via
a hand-written migration when needed).
"""
from __future__ import annotations

from alembic import op

from library.db.bootstrap import _relax_file_entries_folder_id_nullable


revision = "0003_file_entries_folder_id_nullable"
down_revision = "0002_additive_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _relax_file_entries_folder_id_nullable(op.get_bind())


def downgrade() -> None:
    """Irreversible: this migration relaxes file_entries.folder_id to nullable.

    Re-tightening it to NOT NULL fails outright if any row has since taken a NULL, and there is no correct automatic value to backfill.

    Raising is deliberate. A silent no-op here returns success while
    leaving the schema at the newer shape, so alembic_version and the
    actual database disagree with nothing to signal it — and the next
    upgrade then re-runs this migration against a database that already
    has its changes.
    """
    raise NotImplementedError(
        "0003_file_entries_folder_id_nullable cannot be downgraded automatically. "
        "To roll back: decide what NULL folder_id should become, backfill it, re-add the NOT NULL constraint, then stamp the target revision."
    )
