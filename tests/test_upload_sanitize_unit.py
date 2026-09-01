from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from library.db.bootstrap import bootstrap_schema_sync
from library.services.folders import resolve_or_create_folder
from library.storage.sanitize import sanitize_name


@pytest.mark.asyncio
async def test_auto_created_folder_name_is_sanitized(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sanitize.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(bootstrap_schema_sync)
        async with factory() as session:
            folder = await resolve_or_create_folder(session, ["foo:bar"])
            await session.commit()
        assert folder is not None
        assert folder.name == sanitize_name("foo:bar")
        assert folder.name == "foo_bar"
    finally:
        await engine.dispose()


def test_sanitize_name_maps_colon() -> None:
    assert sanitize_name("foo:bar") == "foo_bar"
