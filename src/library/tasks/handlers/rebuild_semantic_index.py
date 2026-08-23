from __future__ import annotations

from typing import Any, Mapping

from library.db.session import session_scope
from library.repositories import audit_events as audit_events_repo
from library.semantic.index import DEFAULT_INDEX_NAME, build_semantic_index
from library.tasks.kinds import KIND_REBUILD_SEMANTIC_INDEX, task_handler


@task_handler(KIND_REBUILD_SEMANTIC_INDEX)
async def handle_rebuild_semantic_index(payload: Mapping[str, Any]) -> None:
    index_name = str(payload.get("index_name") or DEFAULT_INDEX_NAME)
    batch_size = payload.get("batch_size")
    concurrency = int(payload.get("concurrency") or 1)
    page_size = payload.get("page_size")
    task_id = str(payload.get("_task_id") or "") or None

    async with session_scope() as session:
        result = await build_semantic_index(
            session,
            index_name=index_name,
            batch_size=int(batch_size) if batch_size is not None else None,
            concurrency=concurrency,
            # A task-specific resume key prevents an interrupted rebuild from
            # mixing with a manual CLI rebuild or a later independent task.
            resume=task_id is not None,
            resume_key=task_id,
            progress_every=0,
            page_size=int(page_size) if page_size is not None else None,
        )
        await audit_events_repo.append(
            session,
            kind="semantic_index_rebuilt",
            payload={
                "index_name": result.index_name,
                "index_dir": str(result.index_dir),
                "entries_indexed": result.entries_indexed,
                "model": result.model,
                "dimensions": result.dimensions,
                "elapsed_ms": result.elapsed_ms,
                "total_tokens": result.total_tokens,
            },
        )
        await session.commit()
