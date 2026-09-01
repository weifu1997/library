"""TQ-1 regression: enqueue's dedup short-circuit must agree with
`has_inflight_for_kind` about expired-lease running rows.

A running row whose lease has expired is presumed dead — a new enqueue for
the same dedup_key must be able to take over (reclaim the slot) instead of
silently stalling the dispatch chain (periodic_tick sees "not inflight" via
`has_inflight_for_kind`, then enqueue's pre-read would otherwise return the
stale row and never dispatch a successor).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from library.db.models.base import Base
from library.db.models.tasks import Task
from library.tasks.enqueue import enqueue
from library.utils.ids import new_id


def _task(*, dedup_key: str, status: str, lease_minutes: int | None) -> Task:
    now = datetime.now(timezone.utc)
    running = status == "running"
    return Task(
        id=new_id(),
        kind="test_dedup_lease",
        payload={},
        status=status,
        dedup_key=dedup_key,
        priority=100,
        attempts=1 if running else 0,
        max_attempts=5,
        scheduled_at=now,
        lease_expires_at=(
            now + timedelta(minutes=lease_minutes) if running and lease_minutes is not None else None
        ),
        last_heartbeat_at=now if running else None,
        locked_by="worker-1" if running else None,
        created_at=now,
        started_at=now if running else None,
    )


@pytest.fixture
async def sessions():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _rows(sessions, dedup_key: str) -> list[Task]:
    async with sessions() as session:
        result = await session.execute(
            select(Task).where(Task.dedup_key == dedup_key)
        )
        return list(result.scalars().all())


@pytest.mark.asyncio
async def test_enqueue_reclaims_expired_running_dedup(sessions) -> None:
    dedup_key = new_id()
    stale = _task(dedup_key=dedup_key, status="running", lease_minutes=-5)
    async with sessions() as session:
        session.add(stale)
        await session.commit()

    async with sessions() as session:
        returned = await enqueue(
            session, kind="test_dedup_lease", payload={}, dedup_key=dedup_key,
        )
        await session.commit()

    assert returned is not None
    rows = await _rows(sessions, dedup_key)
    stale_row = next(r for r in rows if r.id == stale.id)
    assert stale_row.status == "dead"
    assert stale_row.locked_by is None
    assert stale_row.lease_expires_at is None
    assert "reclaimed by enqueue" in (stale_row.last_error or "")
    # Exactly one live task now holds the dedup key.
    live = [r for r in rows if r.status in ("pending", "running")]
    assert len(live) == 1
    assert returned.id in {r.id for r in live}


@pytest.mark.asyncio
async def test_enqueue_keeps_live_running_dedup(sessions) -> None:
    dedup_key = new_id()
    live = _task(dedup_key=dedup_key, status="running", lease_minutes=5)
    async with sessions() as session:
        session.add(live)
        await session.commit()

    async with sessions() as session:
        returned = await enqueue(
            session, kind="test_dedup_lease", payload={}, dedup_key=dedup_key,
        )
        await session.commit()

    assert returned is not None
    assert returned.id == live.id
    rows = await _rows(sessions, dedup_key)
    assert len(rows) == 1
    assert rows[0].status == "running"


@pytest.mark.asyncio
async def test_enqueue_keeps_pending_dedup(sessions) -> None:
    dedup_key = new_id()
    pending = _task(dedup_key=dedup_key, status="pending", lease_minutes=None)
    async with sessions() as session:
        session.add(pending)
        await session.commit()

    async with sessions() as session:
        returned = await enqueue(
            session, kind="test_dedup_lease", payload={}, dedup_key=dedup_key,
        )
        await session.commit()

    assert returned is not None
    assert returned.id == pending.id
    rows = await _rows(sessions, dedup_key)
    assert len(rows) == 1
    assert rows[0].status == "pending"


@pytest.mark.asyncio
async def test_enqueue_no_dedup_key_always_inserts(sessions) -> None:
    async with sessions() as session:
        first = await enqueue(session, kind="test_dedup_lease", payload={})
        second = await enqueue(session, kind="test_dedup_lease", payload={})
        await session.commit()

    assert first is not None and second is not None
    assert first.id != second.id
