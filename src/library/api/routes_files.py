"""File-level operations — reprocess (single + bulk).

Why these live here and not under /file-entries: reprocess targets the
File row (the content + AI-filled metadata), not a per-position FileEntry.
A single file may have multiple entries across folders; reprocessing
clears `entry_tags` and AI-derived `entry_relations` for all of them, then
re-runs the ingest pipeline once.

The mental model: "user upgraded their LLM, redo the analysis." See
[[feedback-reprocess-scope]] and [[feedback-llm-first-class]].

Implementation: the per-file primitive lives in services.reprocess and
is shared with periodic_tick's self-heal dispatch for low-quality
summaries. Routes here only resolve the bulk filter into a list of
file_ids and chunk the commits.
"""
from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from library.config import get_settings
from library.db.models import File
from library.db.models.enums import INGEST_STATUSES
from library.db.session import get_session
from library.repositories import catalogs as catalogs_repo
from library.repositories import folders as folders_repo
from library.repositories import tasks as tasks_repo
from library.services.reprocess import (
    bulk_reprocess_file_ids_statement,
    reprocess_file,
)
from library.tasks.enqueue import enqueue
from library.tasks.kinds import KIND_BULK_REPROCESS_FILES

router = APIRouter(prefix="/files", tags=["files"])

@router.post("/{file_id}/reprocess", status_code=200)
async def reprocess_one(
    file_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    file_row = await session.get(File, file_id)
    if file_row is None or file_row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="file not found")
    task_id = await reprocess_file(session, file_row)
    await session.commit()
    return {
        "file_id": file_id,
        "task_id": task_id,
        "reused": task_id is None,
    }


class BulkReprocessBody(BaseModel):
    file_ids: list[str] | None = None
    catalog_id: str | None = None
    folder_id: str | None = None
    tag_id: str | None = None
    all: bool = False
    status: str | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "BulkReprocessBody":
        scope_count = sum([
            self.file_ids is not None,
            self.catalog_id is not None,
            self.folder_id is not None,
            self.tag_id is not None,
            self.all,
        ])
        if self.status is not None:
            self.status = self.status.strip().lower()
            if self.status not in INGEST_STATUSES:
                raise ValueError(
                    "status must be one of " + ", ".join(INGEST_STATUSES)
                )
        if scope_count == 0 and self.status is None:
            raise ValueError(
                "one of {file_ids, catalog_id, folder_id, tag_id, all, status} required"
            )
        if scope_count > 1:
            raise ValueError(
                "at most one of {file_ids, catalog_id, folder_id, tag_id, all} allowed"
            )
        if self.file_ids is not None and not self.file_ids:
            raise ValueError("file_ids must be non-empty")
        return self


async def _bulk_reprocess_payload(
    session: AsyncSession,
    body: BulkReprocessBody,
) -> dict[str, Any]:
    payload = body.model_dump(exclude_none=True)
    if body.file_ids is not None:
        payload["file_ids"] = list(dict.fromkeys(body.file_ids))
    elif body.catalog_id is not None:
        if await catalogs_repo.get_live(session, body.catalog_id) is None:
            raise HTTPException(status_code=404, detail="catalog not found")
        payload["catalog_ids"] = await catalogs_repo.expand_subtree(
            session,
            body.catalog_id,
        )
    elif body.folder_id is not None:
        if await folders_repo.get_live(session, body.folder_id) is None:
            raise HTTPException(status_code=404, detail="folder not found")
        payload["folder_ids"] = await folders_repo.list_live_descendant_ids(
            session,
            body.folder_id,
        )
    payload["scheduled_by"] = _reprocess_scope_name(body)
    payload["page_size"] = get_settings().bulk_reprocess_page_size
    return payload


def _reprocess_scope_name(body: BulkReprocessBody) -> str:
    if body.file_ids is not None:
        base = "file_ids"
    elif body.catalog_id is not None:
        base = "catalog_id"
    elif body.folder_id is not None:
        base = "folder_id"
    elif body.tag_id is not None:
        base = "tag_id"
    elif body.all:
        base = "all"
    else:
        base = "status"
    return f"{base}:status={body.status}" if body.status else base


@router.post("/reprocess", status_code=202)
async def reprocess_bulk(
    body: BulkReprocessBody,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    payload = await _bulk_reprocess_payload(session, body)
    count_stmt = bulk_reprocess_file_ids_statement(payload=payload).order_by(None)
    file_count = int((await session.execute(
        select(func.count()).select_from(count_stmt.subquery())
    )).scalar_one())
    fingerprint_payload = {
        key: value
        for key, value in payload.items()
        if key not in {"checkpoint", "dispatcher_task_id"}
    }
    fingerprint = sha256(json.dumps(
        fingerprint_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()[:24]
    dedup_key = f"bulk_reprocess_files:{fingerprint}"
    existing = await tasks_repo.find_pending_or_running_by_dedup(session, dedup_key)
    task = await enqueue(
        session,
        kind=KIND_BULK_REPROCESS_FILES,
        payload=payload,
        dedup_key=dedup_key,
        priority=55,
        max_attempts=20,
    )
    if task is None:
        raise HTTPException(status_code=409, detail="bulk reprocess could not be scheduled")
    reused = existing is not None
    if not reused:
        task.payload = {**payload, "dispatcher_task_id": task.id}
    await session.commit()
    return {
        "dispatcher_task_id": task.id,
        "file_count": file_count,
        "task_ids": [task.id],
        "reused": reused,
        "reused_count": int(reused),
        "skipped_count": 0,
        "scope": _reprocess_scope_name(body),
        "status": "scheduled",
        "status_filter": body.status,
    }
