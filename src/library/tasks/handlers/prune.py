"""Bounded retention pruner for operational history and chat-event ledgers.

DESIGN.md §9.1 + §14.2.3 + §14.2.3a.

Four retention windows live in this one handler:
  - audit_events       : 90d (the audit log)
  - tasks              : 30d (terminal delivery records only)
  - task_outcomes      : 30d (covers longest periodic = suggest_archival 14d × 2)
  - agent_events       : 30d (durable SSE replay history)

The three event/outcome ledgers are INSERT-only, and this handler is their sole
legal delete path; only terminal delivery rows are deleted from `tasks`. After
deleting, ONE summary row is written into task_outcomes covering the whole run
(per-target counts in the detail JSON). audit_events also gets one
`audit_events_pruned` row per phase that actually deleted anything, so the
prune itself stays auditable.

Payload (all optional):
  {"targets": ["audit_events", "tasks", "task_outcomes", "agent_events"]}
  {"retention_days": {"audit_events": 90, "tasks": 30, "task_outcomes": 30,
                       "agent_events": 30}}
  {"batch_size": 1000, "max_batches": 10}
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from library.repositories import audit_events as audit_events_repo
from library.db.session import session_scope
from library.repositories import audit_events as audit_repo
from library.repositories import task_outcomes as task_outcomes_repo
from library.repositories import tasks as tasks_repo
from library.repositories import agent_events as agent_events_repo
from library.config import get_settings
from library.repositories.task_outcomes import (
    GLOBAL_OBJECT_ID,
    GLOBAL_OBJECT_KIND,
    record_outcome,
)
from library.tasks.kinds import KIND_PRUNE, task_handler

log = logging.getLogger(__name__)

ALL_TARGETS = ("audit_events", "task_outcomes", "tasks", "agent_events")

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

@task_handler(KIND_PRUNE)
async def handle_prune(payload: Mapping[str, Any]) -> None:
    now = _utcnow()
    settings = get_settings()
    targets = list(payload.get("targets") or ALL_TARGETS)
    retention_days = {
        "audit_events": settings.audit_retention_days,
        "tasks": settings.task_retention_days,
        "task_outcomes": settings.task_outcome_retention_days,
        "agent_events": settings.agent_event_retention_days,
    }
    retention_days.update(dict(payload.get("retention_days") or {}))
    batch_size = max(1, int(payload.get("batch_size") or settings.prune_batch_size))
    max_batches = max(1, int(payload.get("max_batches") or settings.prune_max_batches))

    per_target: dict[str, dict[str, Any]] = {}
    total_deleted = 0

    async with session_scope() as session:
        for target in targets:
            days = int(retention_days.get(target, 0))
            if days <= 0:
                continue
            cutoff = now - timedelta(days=days)
            if target == "audit_events":
                oldest = await audit_repo.oldest_occurred_at(session)
                deleted = await _prune_in_batches(
                    lambda cutoff=cutoff: audit_repo.delete_before(
                        session, cutoff, limit=batch_size
                    ),
                    batch_size=batch_size,
                    max_batches=max_batches,
                )
                if deleted:
                    await audit_events_repo.append(
                        session,
                        kind="audit_events_pruned",
                        payload={"deleted": deleted, "cutoff": cutoff.isoformat()},
                    )
            elif target == "task_outcomes":
                oldest = await task_outcomes_repo.oldest_completed_at(session)
                deleted = await _prune_in_batches(
                    lambda cutoff=cutoff: task_outcomes_repo.delete_before(
                        session, cutoff, limit=batch_size
                    ),
                    batch_size=batch_size,
                    max_batches=max_batches,
                )
            elif target == "tasks":
                oldest = await tasks_repo.oldest_terminal_finished_at(session)
                deleted = await _prune_in_batches(
                    lambda cutoff=cutoff: tasks_repo.delete_terminal_batch_before(
                        session, cutoff=cutoff, limit=batch_size
                    ),
                    batch_size=batch_size,
                    max_batches=max_batches,
                )
            elif target == "agent_events":
                oldest = await agent_events_repo.oldest_created_at(session)
                deleted = await _prune_in_batches(
                    lambda cutoff=cutoff: agent_events_repo.delete_batch_before(
                        session, cutoff=cutoff, limit=batch_size
                    ),
                    batch_size=batch_size,
                    max_batches=max_batches,
                )
            else:
                log.warning("prune: unknown target %r — skipped", target)
                continue
            total_deleted += deleted
            per_target[target] = {
                "deleted": deleted,
                "cutoff": cutoff.isoformat(),
                "retention_days": days,
                "oldest_before": oldest.isoformat() if oldest else None,
                "batch_size": batch_size,
                "max_batches": max_batches,
            }

        await record_outcome(
            session,
            task_kind=KIND_PRUNE,
            object_kind=GLOBAL_OBJECT_KIND,
            object_id=GLOBAL_OBJECT_ID,
            outcome="applied" if total_deleted else "noop",
            detail={"per_target": per_target, "total_deleted": total_deleted},
        )
        log.info(
            "prune: total_deleted=%d targets=%s",
            total_deleted, list(per_target.keys()),
        )
        await session.commit()

async def _prune_in_batches(
    delete_one_batch,
    *,
    batch_size: int,
    max_batches: int,
) -> int:
    total = 0
    for _ in range(max_batches):
        deleted = int(await delete_one_batch())
        total += deleted
        if deleted < batch_size:
            break
    return total
