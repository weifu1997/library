"""soft_delete merge_into must not close a catalog parent cycle.

ORG-M1: merging a parent into its grandchild re-parents the child under
that grandchild, which is already under the child — a two-node loop.
The apply step must reject the whole op (no half-updated tree).

Run:
    uv run pytest tests/test_restructure_catalogs_cycle_e2e.py -q
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

_TEST_PARENT = Path(os.environ.get("LIBRARY_TEST_TMP", Path(__file__).resolve().parent))
_TEST_ROOT = _TEST_PARENT / f"_restructure_cycle_e2e_{os.getpid()}_{uuid4().hex[:8]}"
_TEST_ROOT.mkdir(parents=True)
os.environ["LIBRARY_HOME"] = str(_TEST_ROOT)
os.environ["STORAGE_BACKEND"] = "local"
os.environ["WORKER_ENABLED"] = "false"
os.environ["LLM_DEFAULT_API_KEY"] = "sk-fake"
os.environ["LLM_DEFAULT_MODEL"] = "fake-model"

from library.config import get_settings  # noqa: E402

get_settings.cache_clear()  # type: ignore[attr-defined]

from library.db.engine import get_engine, get_session_factory  # noqa: E402
from library.db.models import Base, Catalog, TaskOutcome  # noqa: E402
from library.tasks.handlers.restructure_catalogs_apply import (  # noqa: E402
    apply_operations,
)
from library.utils.ids import new_id  # noqa: E402


async def _create_schema() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _assert_no_catalog_cycle(session, catalog_id: str, limit: int = 32) -> None:
    seen: set[str] = set()
    cur: str | None = catalog_id
    for _ in range(limit):
        if cur is None:
            return
        assert cur not in seen, f"catalog cycle through {cur}"
        seen.add(cur)
        row = await session.get(Catalog, cur)
        assert row is not None, f"dangling parent {cur}"
        cur = row.parent_id
    raise AssertionError(f"parent chain from {catalog_id} did not terminate")


async def test_soft_delete_merge_into_grandchild_is_rejected() -> None:
    """parent → child → grandchild; soft_delete(parent, merge_into=grandchild)."""
    now = _now()
    parent_id = new_id()
    child_id = new_id()
    grandchild_id = new_id()
    factory = get_session_factory()
    async with factory() as session:
        session.add(Catalog(
            id=parent_id, parent_id=None, name="parent",
            created_at=now, updated_at=now,
        ))
        session.add(Catalog(
            id=child_id, parent_id=parent_id, name="child",
            created_at=now, updated_at=now,
        ))
        session.add(Catalog(
            id=grandchild_id, parent_id=child_id, name="grandchild",
            created_at=now, updated_at=now,
        ))
        await session.commit()

    await apply_operations(
        operations=[{
            "op": "soft_delete",
            "catalog_id": parent_id,
            "merge_into": grandchild_id,
        }],
        now=_now(),
    )

    async with factory() as session:
        parent = await session.get(Catalog, parent_id)
        child = await session.get(Catalog, child_id)
        grandchild = await session.get(Catalog, grandchild_id)
        assert parent is not None and parent.deleted_at is None
        assert child is not None and child.parent_id == parent_id
        assert grandchild is not None and grandchild.parent_id == child_id
        await _assert_no_catalog_cycle(session, parent_id)
        await _assert_no_catalog_cycle(session, child_id)
        await _assert_no_catalog_cycle(session, grandchild_id)

        rejected = (
            await session.execute(
                select(TaskOutcome).where(TaskOutcome.outcome == "rejected")
            )
        ).scalars().all()
        assert any(
            row.object_kind == "catalog_op" and row.object_id == parent_id
            for row in rejected
        ), [row.detail for row in rejected]
