"""folders: unique (parent_id, name) only among live rows

Revision ID: 0017_folders_live_parent_name_unique
Revises: 0016_scale_safety_indexes
Create Date: 2026-08-31

Soft-deleted folders must not occupy the unique name so a nested
folder can be recreated after DELETE without IntegrityError → 500.
"""
from __future__ import annotations

from alembic import op

from library.db.bootstrap import _ensure_folders_live_parent_name_unique


revision = "0017_folders_live_parent_name_unique"
down_revision = "0016_scale_safety_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _ensure_folders_live_parent_name_unique(op.get_bind())


def downgrade() -> None:
    """Irreversible while a live folder and a tombstone share (parent, name).

    Restoring the old UNIQUE(parent_id, name) would fail on that data, and
    a silent no-op would desync alembic_version from the schema.
    """
    raise NotImplementedError(
        "0017_folders_live_parent_name_unique cannot be downgraded automatically. "
        "To roll back: drop uq_folders_live_parent_name, recreate "
        "UNIQUE(parent_id, name) after resolving live/tombstone name clashes, "
        "then stamp the target revision."
    )
