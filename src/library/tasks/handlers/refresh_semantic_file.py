from __future__ import annotations

import logging
from typing import Any, Mapping

from library.db.session import session_scope
from library.repositories import audit_events as audit_events_repo
from library.semantic.index import refresh_semantic_index_for_file
from library.tasks.kinds import KIND_REFRESH_SEMANTIC_FILE, task_handler

log = logging.getLogger(__name__)


@task_handler(KIND_REFRESH_SEMANTIC_FILE)
async def handle_refresh_semantic_file(payload: Mapping[str, Any]) -> None:
    file_id = str(payload.get("file_id") or "")
    if not file_id:
        raise ValueError("refresh_semantic_file payload missing file_id")

    async with session_scope() as session:
        result = await refresh_semantic_index_for_file(session, file_id)
        await audit_events_repo.append(
            session,
            kind=(
                "semantic_index_refresh_deferred"
                if result.skipped_reason
                else "semantic_index_refreshed"
            ),
            payload={
                "file_id": file_id,
                "index_name": result.index_name,
                "entries_removed": result.entries_removed,
                "entries_refreshed": result.entries_refreshed,
                "entries_total": result.entries_total,
                "vectors_reused": result.vectors_reused,
                "total_tokens": result.total_tokens,
                "reason": result.skipped_reason,
            },
        )
        await session.commit()

    log.info(
        "semantic file refresh completed file_id=%s refreshed=%d reused=%d reason=%s",
        file_id,
        result.entries_refreshed,
        result.vectors_reused,
        result.skipped_reason,
    )
