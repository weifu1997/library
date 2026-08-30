"""repair tables whose FK text still points at _file_entries_old

Revision ID: 0004_repair_dangling_file_entries_fks
Revises: 0003_file_entries_folder_id_nullable
Create Date: 2026-05-27

One-shot repair from an earlier bootstrap that renamed file_entries
without `legacy_alter_table=ON`. SQLite-only; no-op when nothing dangles.
"""
from __future__ import annotations

from alembic import op

from library.db.bootstrap import _repair_dangling_file_entries_fks


revision = "0004_repair_dangling_file_entries_fks"
down_revision = "0003_file_entries_folder_id_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _repair_dangling_file_entries_fks(op.get_bind())


def downgrade() -> None:
    """Intentional no-op — nothing to undo.

    One-shot data repair with no schema change: it rewrites FK text that
    still pointed at _file_entries_old. There is nothing to revert —
    re-breaking those references would only reintroduce the corruption.

    This is NOT the silent-pass pattern that the other migrations were
    corrected away from: those changed the schema, so a no-op there
    left the database drifted from alembic_version. This one touches
    no schema at all.
    """
    return None
