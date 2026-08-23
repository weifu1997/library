from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect

from library.config import Settings
from library.db.bootstrap import (
    QUERY_PERFORMANCE_INDEXES,
    bootstrap_schema_sync,
)
from library.db.engine import _build_engine
from library.db.models import Base


def test_query_performance_indexes_are_modelled_and_bootstrapped(tmp_path) -> None:
    metadata_indexes = {
        index.name
        for table in Base.metadata.tables.values()
        for index in table.indexes
    }
    for index_name, _table_name, _columns in QUERY_PERFORMANCE_INDEXES:
        assert index_name in metadata_indexes

    engine = create_engine(f"sqlite:///{tmp_path / 'library.db'}")
    try:
        with engine.begin() as conn:
            bootstrap_schema_sync(conn)
            inspector = inspect(conn)
            indexes_by_table = {
                table_name: {idx["name"] for idx in inspector.get_indexes(table_name)}
                for _index_name, table_name, _columns in QUERY_PERFORMANCE_INDEXES
            }
            for index_name, table_name, _columns in QUERY_PERFORMANCE_INDEXES:
                assert index_name in indexes_by_table[table_name]
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_sqlite_engine_sets_performance_pragmas(tmp_path) -> None:
    settings = Settings(library_home=str(tmp_path))
    engine = _build_engine(settings)
    try:
        async with engine.connect() as conn:
            journal_mode = (
                await conn.exec_driver_sql("PRAGMA journal_mode")
            ).scalar_one()
            synchronous = (
                await conn.exec_driver_sql("PRAGMA synchronous")
            ).scalar_one()
            busy_timeout = (
                await conn.exec_driver_sql("PRAGMA busy_timeout")
            ).scalar_one()
            cache_size = (
                await conn.exec_driver_sql("PRAGMA cache_size")
            ).scalar_one()
            temp_store = (
                await conn.exec_driver_sql("PRAGMA temp_store")
            ).scalar_one()

        assert str(journal_mode).lower() == "wal"
        assert int(synchronous) == 1
        assert int(busy_timeout) == 30000
        assert int(cache_size) == -65536
        assert int(temp_store) == 2
    finally:
        await engine.dispose()


def test_postgres_engine_uses_configured_pool_limits(monkeypatch) -> None:
    from library.db import engine as engine_module

    captured: dict[str, object] = {}
    sentinel = object()

    def fake_create_async_engine(url: str, **kwargs):  # noqa: ANN003
        captured["url"] = url
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(engine_module, "create_async_engine", fake_create_async_engine)
    settings = Settings(
        db_backend="postgres",
        postgres_dsn="postgresql+asyncpg://user:pass@db/example",
        postgres_pool_size=12,
        postgres_max_overflow=34,
        postgres_pool_timeout_seconds=56,
    )

    result = engine_module._build_engine(settings)

    assert result is sentinel
    assert captured["pool_size"] == 12
    assert captured["max_overflow"] == 34
    assert captured["pool_timeout"] == 56
    assert captured["pool_pre_ping"] is True
