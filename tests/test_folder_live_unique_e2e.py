"""ORG-H1: soft-deleted nested folders must not occupy the unique name.

After DELETE /v1/folders/{id}, creating the same name under the same live
parent must succeed (201), not IntegrityError 500. Two live siblings still
409.

Run:
    uv run pytest tests/test_folder_live_unique_e2e.py -q
"""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import inspect

_TEST_PARENT = Path(os.environ.get("LIBRARY_TEST_TMP", Path(__file__).resolve().parent))
_TEST_ROOT = _TEST_PARENT / f"_folder_live_unique_{os.getpid()}_{uuid4().hex[:8]}"
_TEST_ROOT.mkdir(parents=True)
os.environ["LIBRARY_HOME"] = str(_TEST_ROOT)
os.environ["STORAGE_BACKEND"] = "local"
os.environ["WORKER_ENABLED"] = "false"
os.environ["LLM_DEFAULT_API_KEY"] = "sk-fake"
os.environ["LLM_DEFAULT_MODEL"] = "fake-model"

from library.config import get_settings  # noqa: E402

get_settings.cache_clear()  # type: ignore[attr-defined]

from library.db.bootstrap import bootstrap_schema  # noqa: E402
from library.db.engine import get_engine, get_session_factory  # noqa: E402
from library.db.models import Folder  # noqa: E402
from library.main import app  # noqa: E402


async def _client() -> AsyncClient:
    await bootstrap_schema()
    return AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
    )


async def test_soft_deleted_nested_folder_name_can_be_recreated() -> None:
    async with app.router.lifespan_context(app):
        async with await _client() as c:
            work = await c.post("/v1/folders", json={"name": "work", "parent_id": None})
            assert work.status_code == 201, work.text
            work_id = work.json()["id"]

            projects = await c.post(
                "/v1/folders", json={"name": "Projects", "parent_id": work_id},
            )
            assert projects.status_code == 201, projects.text
            old_id = projects.json()["id"]

            deleted = await c.delete(f"/v1/folders/{old_id}")
            assert deleted.status_code == 200, deleted.text

            factory = get_session_factory()
            async with factory() as session:
                tombstone = await session.get(Folder, old_id)
                assert tombstone is not None
                assert tombstone.deleted_at is not None

            recreated = await c.post(
                "/v1/folders", json={"name": "Projects", "parent_id": work_id},
            )
            assert recreated.status_code == 201, recreated.text
            assert recreated.json()["id"] != old_id
            assert recreated.json()["name"] == "Projects"


async def test_two_live_siblings_still_conflict() -> None:
    async with app.router.lifespan_context(app):
        async with await _client() as c:
            parent = await c.post("/v1/folders", json={"name": "docs", "parent_id": None})
            assert parent.status_code == 201, parent.text
            parent_id = parent.json()["id"]

            first = await c.post(
                "/v1/folders", json={"name": "Notes", "parent_id": parent_id},
            )
            assert first.status_code == 201, first.text

            clash = await c.post(
                "/v1/folders", json={"name": "Notes", "parent_id": parent_id},
            )
            assert clash.status_code == 409, clash.text
            detail = clash.json()["detail"]
            assert detail["error"] == "folder_name_conflict"


async def test_bootstrap_creates_partial_unique_index() -> None:
    await bootstrap_schema()
    engine = get_engine()
    async with engine.connect() as conn:
        indexes = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_indexes("folders"))
    live = next(idx for idx in indexes if idx["name"] == "uq_folders_live_parent_name")
    assert live.get("unique")
