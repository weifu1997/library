"""Durable public chat-event ledger."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from library.db.models import AgentEvent
from library.utils.ids import new_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def append(
    db: AsyncSession,
    *,
    conversation_id: str,
    event: str,
    data: str,
) -> AgentEvent:
    cursor = int(
        await db.scalar(
            select(func.coalesce(func.max(AgentEvent.cursor), 0)).where(
                AgentEvent.conversation_id == conversation_id
            )
        )
        or 0
    ) + 1
    row = AgentEvent(
        id=new_id(),
        conversation_id=conversation_id,
        cursor=cursor,
        event=event,
        data=data,
        created_at=_utcnow(),
    )
    db.add(row)
    await db.flush()
    return row


async def list_after(
    db: AsyncSession,
    *,
    conversation_id: str,
    after_cursor: int,
    limit: int = 200,
) -> list[AgentEvent]:
    rows = (
        await db.execute(
            select(AgentEvent)
            .where(
                AgentEvent.conversation_id == conversation_id,
                AgentEvent.cursor > max(0, int(after_cursor)),
            )
            .order_by(AgentEvent.cursor.asc())
            .limit(max(1, min(int(limit), 1000)))
        )
    ).scalars().all()
    return list(rows)


async def delete_batch_before(
    db: AsyncSession,
    *,
    cutoff: datetime,
    limit: int,
) -> int:
    ids = list(
        (
            await db.execute(
                select(AgentEvent.id)
                .where(AgentEvent.created_at < cutoff)
                .order_by(AgentEvent.created_at.asc(), AgentEvent.id.asc())
                .limit(max(1, int(limit)))
            )
        ).scalars().all()
    )
    if not ids:
        return 0
    result = await db.execute(delete(AgentEvent).where(AgentEvent.id.in_(ids)))
    return max(0, int(result.rowcount or 0))


async def oldest_created_at(db: AsyncSession) -> datetime | None:
    return await db.scalar(select(func.min(AgentEvent.created_at)))


async def latest_event_name(
    db: AsyncSession,
    *,
    conversation_id: str,
) -> str | None:
    value = await db.scalar(
        select(AgentEvent.event)
        .where(AgentEvent.conversation_id == conversation_id)
        .order_by(AgentEvent.cursor.desc())
        .limit(1)
    )
    return str(value) if value is not None else None
