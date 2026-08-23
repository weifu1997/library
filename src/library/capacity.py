"""Optional global capacity gates for expensive foreground operations."""
from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from library.config import Settings
from library.db.models import Conversation, File, Task
from library.tasks.kinds import KIND_BULK_REPROCESS_FILES, KIND_INGEST_FILE


class CapacityExceeded(HTTPException):
    """HTTP 429 with a stable machine-readable capacity payload."""

    def __init__(self, *, resource: str, limit: int, current: int) -> None:
        super().__init__(
            status_code=429,
            headers={"Retry-After": "5"},
            detail={
                "error": "capacity_exceeded",
                "resource": resource,
                "limit": int(limit),
                "current": int(current),
            },
        )


def _is_postgres(db: object) -> bool:
    try:
        return db.get_bind().dialect.name == "postgresql"  # type: ignore[attr-defined]
    except (AttributeError, TypeError):
        return False


async def _lock_gate(db: AsyncSession, *, operation: str) -> None:
    if not _is_postgres(db):
        return
    # Transaction-scoped advisory locks also work with transaction-pooled
    # proxies because no session-level state survives the transaction.
    await db.execute(
        text(
            "SELECT pg_advisory_xact_lock("
            "hashtextextended(:capacity_key, 817453223))"
        ),
        {"capacity_key": f"library-capacity:{operation}"},
    )


async def enforce_upload_capacity(
    db: AsyncSession,
    *,
    incoming_bytes: int,
    settings: Settings,
) -> None:
    """Atomically cap live files, stored bytes, and ingest backlog."""
    document_limit = int(settings.library_document_limit or 0)
    storage_limit = int(settings.library_storage_bytes_limit or 0)
    backlog_limit = int(settings.ingest_backlog_limit or 0)
    if not any(limit > 0 for limit in (document_limit, storage_limit, backlog_limit)):
        return

    await _lock_gate(db, operation="upload")
    file_count, storage_bytes = (
        await db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(File.size_bytes), 0),
            ).where(File.deleted_at.is_(None))
        )
    ).one()
    file_count = int(file_count or 0)
    storage_bytes = int(storage_bytes or 0)
    if document_limit > 0 and file_count >= document_limit:
        raise CapacityExceeded(
            resource="documents",
            limit=document_limit,
            current=file_count,
        )

    projected_storage = storage_bytes + max(0, int(incoming_bytes))
    if storage_limit > 0 and projected_storage > storage_limit:
        raise CapacityExceeded(
            resource="storage_bytes",
            limit=storage_limit,
            current=storage_bytes,
        )

    if backlog_limit <= 0:
        return
    active_ingest = int(
        await db.scalar(
            select(func.count(Task.id)).where(
                Task.status.in_(("pending", "running")),
                Task.kind.in_((KIND_INGEST_FILE, KIND_BULK_REPROCESS_FILES)),
            )
        )
        or 0
    )
    if active_ingest >= backlog_limit:
        raise CapacityExceeded(
            resource="ingest_backlog",
            limit=backlog_limit,
            current=active_ingest,
        )


async def enforce_chat_concurrency(
    db: AsyncSession,
    *,
    limit: int,
    stale_before: datetime,
) -> None:
    """Atomically cap unfinished, non-stale chat turns."""
    if limit <= 0:
        return
    await _lock_gate(db, operation="chat")
    active = int(
        await db.scalar(
            select(func.count(Conversation.id)).where(
                Conversation.ended_at.is_(None),
                Conversation.started_at >= stale_before,
            )
        )
        or 0
    )
    if active >= limit:
        raise CapacityExceeded(
            resource="concurrent_chat_turns",
            limit=limit,
            current=active,
        )


__all__ = ["CapacityExceeded", "enforce_chat_concurrency", "enforce_upload_capacity"]
