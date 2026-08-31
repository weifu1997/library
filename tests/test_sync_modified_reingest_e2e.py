"""Regression: Finder in-place edit must re-ingest through reprocess_file.

UPLOAD-1: apply_modified used to update sha/size, clear summary, set
ingest_status=pending, and enqueue ingest_file without dedup_key and
without clearing ingested_at. ingest_file._persist is write-once, so
the second run never overwrote summary/description/kind/extra.

This test:
  1. Ingests a file (summary + ingested_at set).
  2. Edits the vault bytes (same path, new sha).
  3. apply_modified — entry identity stays, ingested_at is cleared,
     sha/size update, one pending ingest with dedup_key=ingest_file:{id}.
  4. apply_modified again while that task is still pending — still one
     pending/running ingest for the file.
  5. Running the ingest handler persists the *new* summary.
  6. An unmodified sibling is left alone.

Run:
    uv run pytest tests/test_sync_modified_reingest_e2e.py -q
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

_TEST_PARENT = Path(os.environ.get("LIBRARY_TEST_TMP", Path(__file__).resolve().parent))
_TEST_ROOT = _TEST_PARENT / f"_sync_modified_reingest_e2e_{os.getpid()}_{uuid4().hex[:8]}"
_VAULT = _TEST_ROOT / "library"
_TEST_ROOT.mkdir(parents=True)
os.environ["LIBRARY_HOME"] = str(_TEST_ROOT)
os.environ["STORAGE_BACKEND"] = "mirror"
os.environ["WORKER_ENABLED"] = "false"
os.environ["LLM_DEFAULT_API_KEY"] = "sk-fake"
os.environ["LLM_DEFAULT_MODEL"] = "fake-model"

from library.config import get_settings  # noqa: E402

get_settings.cache_clear()  # type: ignore[attr-defined]

from library.db.engine import get_engine, get_session_factory  # noqa: E402
from library.db.models import Base, File, FileEntry, Task  # noqa: E402
from library.pipelines.base import PipelineResult  # noqa: E402
from library.services.scan import scan_vault  # noqa: E402
from library.services.sync import apply_modified  # noqa: E402
from library.storage import get_storage, reset_storage_cache  # noqa: E402
from library.tasks.handlers.ingest_file import handle_ingest_file  # noqa: E402
from library.tasks.kinds import KIND_INGEST_FILE  # noqa: E402


async def _create_schema() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


async def _upload(body: bytes, *, name: str, remote_path: str) -> str:
    from library.services.upload import upload

    storage = get_storage()

    async def _stream():
        yield body

    factory = get_session_factory()
    async with factory() as db:
        result = await upload(
            db, storage,
            stream=_stream(), fallback_name=name,
            remote_path=remote_path,
            content_type="text/plain",
        )
        await db.commit()
        return result.entry_id


async def _mark_ingest_done(
    session,
    *,
    file_id: str,
    summary: str,
    extra: str,
) -> None:
    file_row = await session.get(File, file_id)
    assert file_row is not None
    now = _now()
    file_row.summary = summary
    file_row.description = {"sections": []}
    file_row.kind = "text"
    file_row.extra = extra
    file_row.ingest_status = "done"
    file_row.ingested_at = now
    file_row.updated_at = now
    tasks = (
        await session.execute(
            select(Task).where(
                Task.kind == KIND_INGEST_FILE,
                Task.status.in_(("pending", "running")),
            )
        )
    ).scalars().all()
    for task in tasks:
        if task.payload.get("file_id") == file_id:
            task.status = "done"
            task.finished_at = now


async def _pending_ingest_tasks(session, file_id: str) -> list[Task]:
    rows = (
        await session.execute(
            select(Task).where(
                Task.kind == KIND_INGEST_FILE,
                Task.status.in_(("pending", "running")),
            )
        )
    ).scalars().all()
    return [t for t in rows if t.payload.get("file_id") == file_id]


async def _noop_async(*_args, **_kwargs) -> None:
    return None


class _FakePipeline:
    name = "text"

    def __init__(self, result: PipelineResult) -> None:
        self._result = result

    async def run(self, *, ctx, storage):  # noqa: ANN001
        del ctx, storage
        return self._result


@pytest.mark.asyncio
async def test_apply_modified_reingest_persists_new_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_storage_cache()

    first_body = b"alpha original\n"
    sibling_body = b"beta original\n"
    edited_body = b"alpha edited in Finder\n"

    a_id = await _upload(first_body, name="a.txt", remote_path="notes/a.txt")
    b_id = await _upload(sibling_body, name="b.txt", remote_path="notes/b.txt")

    factory = get_session_factory()
    async with factory() as session:
        a_entry = await session.get(FileEntry, a_id)
        b_entry = await session.get(FileEntry, b_id)
        assert a_entry is not None and b_entry is not None
        a_file_id = a_entry.file_id
        b_file_id = b_entry.file_id
        a_folder_id = a_entry.folder_id
        a_display = a_entry.display_name
        await _mark_ingest_done(
            session, file_id=a_file_id,
            summary="first summary", extra="first extra",
        )
        await _mark_ingest_done(
            session, file_id=b_file_id,
            summary="sibling summary", extra="sibling extra",
        )
        await session.commit()
        first_ingested_at = (await session.get(File, a_file_id)).ingested_at
        sibling_ingested_at = (await session.get(File, b_file_id)).ingested_at
        assert first_ingested_at is not None
        assert sibling_ingested_at is not None

    (_VAULT / "notes" / "a.txt").write_bytes(edited_body)
    report = await scan_vault(_VAULT)
    assert len(report.modified) == 1, report.modified
    assert report.modified[0][0].id == a_id

    n, failures = await apply_modified(report)
    assert failures == [], failures
    assert n == 1

    async with factory() as session:
        a_entry = await session.get(FileEntry, a_id)
        a_file = await session.get(File, a_file_id)
        b_file = await session.get(File, b_file_id)
        assert a_entry is not None and a_file is not None and b_file is not None
        assert a_entry.id == a_id
        assert a_entry.folder_id == a_folder_id
        assert a_entry.display_name == a_display
        assert a_file.sha256 == _sha256(edited_body)
        assert a_file.size_bytes == len(edited_body)
        assert a_file.ingested_at is None
        assert a_file.ingest_status == "pending"
        assert b_file.ingested_at == sibling_ingested_at
        assert b_file.summary == "sibling summary"
        assert b_file.ingest_status == "done"
        pending_a = await _pending_ingest_tasks(session, a_file_id)
        pending_b = await _pending_ingest_tasks(session, b_file_id)
        assert len(pending_a) == 1
        assert pending_a[0].dedup_key == f"ingest_file:{a_file_id}"
        assert pending_b == []

    n2, failures2 = await apply_modified(report)
    assert failures2 == [], failures2
    assert n2 == 1
    async with factory() as session:
        pending_a = await _pending_ingest_tasks(session, a_file_id)
        assert len(pending_a) == 1
        assert pending_a[0].dedup_key == f"ingest_file:{a_file_id}"

    new_result = PipelineResult(
        summary="new summary after edit",
        description={"sections": [{"id": "s1"}]},
        kind="text",
        extra="new extra",
        entry_extra=None,
        entry_catalog_path=None,
        entry_tags=[],
    )
    monkeypatch.setattr(
        "library.tasks.handlers.ingest_file.resolve_pipeline",
        lambda *_args, **_kwargs: _FakePipeline(new_result),
    )
    monkeypatch.setattr(
        "library.tasks.handlers.ingest_file._refresh_semantic_index",
        _noop_async,
    )
    await handle_ingest_file({"file_id": a_file_id, "entry_id": a_id})

    async with factory() as session:
        a_file = await session.get(File, a_file_id)
        a_entry = await session.get(FileEntry, a_id)
        assert a_file is not None and a_entry is not None
        assert a_file.summary == "new summary after edit"
        assert a_file.description == {"sections": [{"id": "s1"}]}
        assert a_file.kind == "text"
        assert a_file.extra == "new extra"
        assert a_file.ingest_status == "done"
        assert a_file.ingested_at is not None
        assert a_file.ingested_at != first_ingested_at
        assert a_entry.id == a_id
        assert a_entry.folder_id == a_folder_id
        assert a_entry.display_name == a_display
