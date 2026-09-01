from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from library.db.bootstrap import bootstrap_schema_sync
from library.db.models import File
from library.tasks.handlers import delete_storage_object as handler
from library.utils.ids import new_id


class _FakeStorage:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def delete(self, key: str) -> None:
        self.deleted.append(key)


@pytest.mark.asyncio
async def test_delete_storage_rechecks_before_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'toctou.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    storage = _FakeStorage()
    key = "00/aa/toctou"
    now = datetime.now(timezone.utc)
    first = {"seen": False}

    @asynccontextmanager
    async def _scope():
        async with factory() as session:
            if first["seen"]:
                session.add(File(
                    id=new_id(),
                    storage_key=key,
                    sha256="a" * 64,
                    size_bytes=1,
                    mime_type="text/plain",
                    original_ext=".txt",
                    kind="text",
                    summary=None,
                    description=None,
                    extra=None,
                    ingest_status="done",
                    ingested_at=now,
                    deleted_at=None,
                    created_at=now,
                    updated_at=now,
                ))
                await session.flush()
            else:
                first["seen"] = True
            yield session

    async def _async_noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(handler, "session_scope", _scope)
    monkeypatch.setattr(handler, "_storage_from_payload", lambda payload: storage)
    monkeypatch.setattr(handler, "record_outcome", _async_noop)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(bootstrap_schema_sync)
        await handler.handle_delete_storage_object({
            "storage_key": key,
            "storage_backend": "local",
            "storage_root": str(tmp_path),
        })
        assert storage.deleted == []
    finally:
        await engine.dispose()
