"""Read-only statistics router — the Overview dashboard backend.

One endpoint, `GET /v1/stats/overview`, aggregates library-wide counts,
task pressure, recent entries, storage backend, and semantic-index status
into a single read-only payload so the Overview page can render from one
request. Strictly read-only: no writes, no side effects, safe to poll.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from library.config import get_settings
from library.db.models import File, FileEntry, Folder, Tag
from library.db.session import get_session
from library.repositories import tasks as tasks_repo
from library.semantic.index import semantic_index_status
from library.services.entries import _build_folder_display_path

router = APIRouter(prefix="/stats", tags=["stats"])

_RECENT_LIMIT = 10


async def _count_live_entries(db: AsyncSession) -> int:
    """Live entries joined to their live file rows."""
    row = await db.execute(
        select(func.count())
        .select_from(FileEntry)
        .join(File, File.id == FileEntry.file_id)
        .where(
            FileEntry.deleted_at.is_(None),
            File.deleted_at.is_(None),
        )
    )
    return int(row.scalar_one())


async def _count_live_folders(db: AsyncSession) -> int:
    row = await db.execute(
        select(func.count()).select_from(Folder).where(Folder.deleted_at.is_(None))
    )
    return int(row.scalar_one())


async def _count_tags(db: AsyncSession) -> int:
    row = await db.execute(select(func.count()).select_from(Tag))
    return int(row.scalar_one())


async def _list_recent_entries(
    db: AsyncSession, *, limit: int,
) -> list[dict[str, Any]]:
    """Most-recently-added live entries, newest first."""
    rows = (
        await db.execute(
            select(FileEntry, File.ingest_status)
            .join(File, File.id == FileEntry.file_id)
            .where(
                FileEntry.deleted_at.is_(None),
                File.deleted_at.is_(None),
            )
            .order_by(FileEntry.created_at.desc(), FileEntry.id.desc())
            .limit(limit)
        )
    ).all()
    out: list[dict[str, Any]] = []
    for entry, ingest_status in rows:
        folder_path = await _build_folder_display_path(db, entry.folder_id)
        out.append({
            "entry_id": entry.id,
            "display_name": entry.display_name,
            "folder_path": folder_path or None,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
            "ingest_status": ingest_status,
        })
    return out


@router.get("/overview")
async def stats_overview(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Read-only knowledge-base overview. No side effects — safe to poll."""
    s = get_settings()
    # Sequential, not asyncio.gather: these share one AsyncSession, and
    # SQLAlchemy async sessions must not be used concurrently.
    entries = await _count_live_entries(session)
    folders = await _count_live_folders(session)
    tags = await _count_tags(session)
    task_counts = await tasks_repo.count_running_and_pending(session)
    recent = await _list_recent_entries(session, limit=_RECENT_LIMIT)
    index = semantic_index_status()
    return {
        "totals": {
            "entries": entries,
            "folders": folders,
            "tags": tags,
        },
        "tasks": {
            "running": int(task_counts.get("running", 0)),
            "pending": int(task_counts.get("pending", 0)),
        },
        "recent": recent,
        "storage_backend": s.storage_backend,
        "semantic": {
            "enabled": bool(s.semantic_recall_enabled),
            "configured": bool(s.semantic_recall_enabled and s.embedding_api_key),
            "index_ready": bool(index.get("exists") and index.get("compatible")),
        },
    }
