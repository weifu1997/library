"""files.kind: extend CHECK for supplemental kinds

Revision ID: 0014_files_kind_check
Revises: 0013_reconcile_dead_ingest_files
Create Date: 2026-06-25

Adds `email` and `ebook` to the legal files.kind values used by
supplemental extraction pipelines.
"""
from __future__ import annotations

from alembic import op

from library.db.bootstrap import _relax_files_kind_check


revision = "0014_files_kind_check"
down_revision = "0013_reconcile_dead_ingest_files"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _relax_files_kind_check(op.get_bind())


def downgrade() -> None:
    """Irreversible: this migration relaxes the files.kind CHECK constraint.

    Restoring the narrower constraint fails if any file row has since been written with one of the newly-allowed kinds.

    Raising is deliberate. A silent no-op here returns success while
    leaving the schema at the newer shape, so alembic_version and the
    actual database disagree with nothing to signal it — and the next
    upgrade then re-runs this migration against a database that already
    has its changes.
    """
    raise NotImplementedError(
        "0014_files_kind_check cannot be downgraded automatically. "
        "To roll back: reconcile the offending kind values, restore the old CHECK, then stamp the target revision."
    )
