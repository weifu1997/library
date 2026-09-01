"""TQ-2 regression: purge_deleted_files must re-check storage references
between the DB commit and the physical storage delete (TOCTOU).

`storage_key` is UNIQUE on files, so a second row can only appear with the
same key AFTER the purged row was committed away — exactly the concurrent
restore / re-registration race the post-commit re-check protects against.
We simulate that restore landing between the commit and the re-check, then
assert the physical delete is skipped and the object survives.

Storage keys are unique per test so the shared module DB accumulates rows
across runs without colliding.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from library.db.engine import get_engine, get_session_factory
from library.db.models import File, FileEntry, Folder
from library.db.models.base import Base
from library.repositories import files as files_repo
from library.storage import get_storage
from library.tasks import handlers
from library.tasks.handlers.purge_deleted_files import (
    handle_purge_deleted_files,
    _storage_object_referenced,
)
from library.utils.ids import new_id


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _create_schema() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _storage_key() -> str:
    return f"00/aa/{new_id()}"


async def _seed() -> dict:
    factory = get_session_factory()
    storage = get_storage()
    now = _now()
    suggested = _storage_key()

    async def _stream():
        yield b"shared content"

    # MirrorStorage ignores the suggested key and computes the path from
    # (display_name, folder_path), falling back to the key's basename. It
    # returns the rel it actually wrote; the DB row must store exactly that
    # key so purge's post-commit re-check and storage.delete() line up.
    storage_key = await storage.put(
        suggested, _stream(), content_type="text/plain",
    )

    async with factory() as s:
        folder = Folder(id=new_id(), parent_id=None, name="root",
                        created_at=now, updated_at=now)
        s.add(folder)
        f = File(
            id=new_id(), storage_key=storage_key, sha256="a" * 64, size_bytes=16,
            mime_type="text/plain", original_ext=".txt", kind="text",
            summary="x", description={"sections": []}, extra=None,
            ingest_status="done", ingested_at=now,
            created_at=now, updated_at=now,
        )
        s.add(f)
        await s.flush()
        e = FileEntry(id=new_id(), folder_id=folder.id, file_id=f.id,
                      display_name="alpha.txt", lifecycle="active",
                      catalog_id=None, extra=None,
                      created_at=now, updated_at=now)
        s.add(e)
        e.deleted_at = now
        e.purge_after = now - timedelta(minutes=60)
        e.updated_at = now
        await s.commit()
        return {"file_id": f.id, "storage_key": storage_key}


async def _insert_restored_row(storage_key: str) -> None:
    """Simulate a concurrent restore: re-register a file row for the object."""
    factory = get_session_factory()
    now = _now()
    async with factory() as s:
        s.add(File(
            id=new_id(), storage_key=storage_key, sha256="b" * 64, size_bytes=16,
            mime_type="text/plain", original_ext=".txt", kind="text",
            summary="restored", description={"sections": []}, extra=None,
            ingest_status="done", ingested_at=now,
            created_at=now, updated_at=now,
        ))
        await s.commit()


async def test_purge_skips_delete_when_object_referenced(
    monkeypatch,
) -> None:
    seeded = await _seed()
    factory = get_session_factory()
    storage = get_storage()
    storage_key = seeded["storage_key"]

    real_check = _storage_object_referenced

    async def racing_check(key: str) -> bool:
        # The restore lands between the purge commit and the re-check.
        await _insert_restored_row(key)
        return await real_check(key)

    monkeypatch.setattr(
        handlers.purge_deleted_files, "_storage_object_referenced", racing_check,
    )

    await handle_purge_deleted_files({})

    async with factory() as s:
        assert await s.get(File, seeded["file_id"]) is None, "purged file row gone"
        assert await files_repo.exists_by_storage_key(s, storage_key), (
            "restored reference must be visible in a fresh transaction"
        )
    assert await storage.exists(storage_key), (
        "storage object deleted despite the restored reference (TOCTOU)"
    )


async def test_purge_still_deletes_when_no_reference() -> None:
    seeded = await _seed()
    factory = get_session_factory()
    storage = get_storage()

    await handle_purge_deleted_files({})

    async with factory() as s:
        assert await s.get(File, seeded["file_id"]) is None
    assert not await storage.exists(seeded["storage_key"]), (
        "unreferenced object should be deleted (normal path preserved)"
    )


async def test_exists_by_storage_key() -> None:
    factory = get_session_factory()
    key = _storage_key()
    async with factory() as s:
        assert not await files_repo.exists_by_storage_key(s, key)
    await _insert_restored_row(key)
    async with factory() as s:
        assert await files_repo.exists_by_storage_key(s, key)
