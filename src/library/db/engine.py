from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from library.config import Settings, get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[Any] | None = None


def _build_engine(settings: Settings) -> AsyncEngine:
    url = settings.database_url
    if settings.db_backend == "sqlite":
        engine = create_async_engine(
            url,
            future=True,
            connect_args={"check_same_thread": False, "timeout": 30.0},
        )

        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA synchronous=NORMAL")
                # WAL allows readers + one writer concurrently, but a second
                # writer (e.g. another worker committing audit_events while
                # ingest_file commits its own) gets SQLITE_BUSY immediately
                # unless busy_timeout is set. 30s of patient retry covers
                # phase-3 _persist commits that hold the writer for several
                # seconds while a batch of ingest_file tasks pile up behind.
                cursor.execute("PRAGMA busy_timeout=30000")
                # Keep the personal-library hot set in process memory and
                # avoid temp b-trees hitting disk during sort/group bursts.
                cursor.execute("PRAGMA cache_size=-65536")
                cursor.execute("PRAGMA temp_store=MEMORY")
                cursor.execute("PRAGMA mmap_size=268435456")
                cursor.execute("PRAGMA optimize")
            finally:
                cursor.close()

        return engine

    connect_args: dict[str, Any] = {}
    cache_size = settings.postgres_prepared_statement_cache_size
    if cache_size != 100:
        connect_args["prepared_statement_cache_size"] = cache_size
    if cache_size == 0:
        # Disabling asyncpg's client cache does not disable server-side
        # prepares. Unique names avoid collisions when transaction pooling
        # assigns a different backend connection to the next transaction.
        connect_args["prepared_statement_name_func"] = (
            lambda: f"__asyncpg_{uuid4()}__"
        )
    return create_async_engine(
        url,
        future=True,
        pool_pre_ping=True,
        pool_size=settings.postgres_pool_size,
        max_overflow=settings.postgres_max_overflow,
        pool_timeout=settings.postgres_pool_timeout_seconds,
        connect_args=connect_args,
    )


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = _build_engine(get_settings())
    return _engine


def get_session_factory() -> async_sessionmaker[Any]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
