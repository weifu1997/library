"""Local and PostgreSQL serialization for stateful Agent tools."""
from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from weakref import WeakValueDictionary

from sqlalchemy import text


_LOCK_NAMESPACE = b"library:agent-tool:v1"
_GLOBAL_TOOL_LOCKS: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
_SESSION_TOOL_LOCKS: WeakValueDictionary[tuple[str, str], asyncio.Lock] = (
    WeakValueDictionary()
)


def _advisory_lock_id(scope: str, *parts: str) -> int:
    """Return a deterministic signed bigint suitable for PostgreSQL locks."""
    digest = hashlib.blake2b(digest_size=8)
    digest.update(_LOCK_NAMESPACE)
    for value in (scope, *parts):
        digest.update(b"\0")
        digest.update(value.encode("utf-8"))
    return int.from_bytes(digest.digest(), byteorder="big", signed=True)


def _local_lock(
    *,
    concurrency: str,
    session_id: str,
    tool_name: str,
) -> tuple[asyncio.Lock, int] | None:
    if concurrency == "global_serial":
        lock = _GLOBAL_TOOL_LOCKS.setdefault(tool_name, asyncio.Lock())
        return lock, _advisory_lock_id("global", tool_name)
    if concurrency == "session_serial":
        key = (session_id, tool_name)
        lock = _SESSION_TOOL_LOCKS.setdefault(key, asyncio.Lock())
        return lock, _advisory_lock_id("session", *key)
    return None


def _is_postgresql_session(db: object) -> bool:
    get_bind = getattr(db, "get_bind", None)
    if not callable(get_bind):
        return False
    bind = get_bind()
    return getattr(getattr(bind, "dialect", None), "name", None) == "postgresql"


@asynccontextmanager
async def tool_execution_lock(
    db: object,
    *,
    concurrency: str,
    session_id: str,
    tool_name: str,
) -> AsyncIterator[None]:
    """Serialize locally and, when available, across PostgreSQL replicas."""
    resolved = _local_lock(
        concurrency=concurrency,
        session_id=session_id,
        tool_name=tool_name,
    )
    if resolved is None:
        yield
        return
    local_lock, lock_id = resolved
    async with local_lock:
        if _is_postgresql_session(db):
            execute = db.execute
            await execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"),
                {"lock_id": lock_id},
            )
        yield


@asynccontextmanager
async def session_execution_lock(
    db: object,
    *,
    session_id: str,
) -> AsyncIterator[None]:
    """Hold one PostgreSQL transaction lock for a complete Agent turn."""
    if _is_postgresql_session(db):
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": _advisory_lock_id("turn", session_id)},
        )
    yield


__all__ = ["session_execution_lock", "tool_execution_lock"]
