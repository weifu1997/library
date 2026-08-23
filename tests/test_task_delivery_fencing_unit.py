from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from library.config import Settings
from library.db.models.base import Base
from library.db.models.tasks import Task
from library.repositories import tasks as tasks_repo
from library.tasks import runner as runner_module
from library.tasks.runner import TaskRunner
from library.utils.ids import new_id


def _task(*, task_id: str | None = None, owner: str | None = None) -> Task:
    now = datetime.now(timezone.utc)
    return Task(
        id=task_id or new_id(),
        kind="test_delivery_fence",
        payload={},
        status="running" if owner else "pending",
        priority=100,
        attempts=1 if owner else 0,
        max_attempts=5,
        scheduled_at=now,
        lease_expires_at=now + timedelta(minutes=1) if owner else None,
        last_heartbeat_at=now if owner else None,
        locked_by=owner,
        created_at=now,
        started_at=now if owner else None,
    )


def test_retry_backoff_is_exponential_configurable_and_capped() -> None:
    settings = Settings(
        worker_retry_base_seconds=10,
        worker_retry_max_seconds=25,
    )
    assert runner_module._backoff(1, settings) == timedelta(seconds=10)
    assert runner_module._backoff(2, settings) == timedelta(seconds=20)
    assert runner_module._backoff(3, settings) == timedelta(seconds=25)
    assert runner_module._backoff(1000, settings) == timedelta(seconds=25)


@pytest.mark.asyncio
async def test_each_claimed_delivery_gets_a_unique_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    first = _task()
    second = _task()
    async with sessions() as session:
        session.add_all([first, second])
        await session.commit()

    @asynccontextmanager
    async def test_session_scope():
        async with sessions() as session:
            yield session

    monkeypatch.setattr(runner_module, "session_scope", test_session_scope)
    runner = TaskRunner(
        Settings(llm_default_api_key="test-key"),
        worker_id="worker-process",
    )
    try:
        claimed = await runner._claim_batch(2)
        assert set(claimed) == {first.id, second.id}

        owners = {runner._claim_owners[task_id] for task_id in claimed}
        assert len(owners) == 2
        assert all(owner.startswith("worker-process:") for owner in owners)
        assert all(len(owner) <= 64 for owner in owners)

        async with sessions() as session:
            rows = await tasks_repo.list_by_ids(session, claimed)
        assert {row.locked_by for row in rows} == owners
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_stale_delivery_cannot_mutate_a_reclaimed_task() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    current_owner = "current-delivery"
    heartbeat_task = _task(owner=current_owner)
    done_task = _task(owner=current_owner)
    retry_task = _task(owner=current_owner)
    dead_task = _task(owner=current_owner)
    original_lease = heartbeat_task.lease_expires_at
    async with sessions() as session:
        session.add_all([heartbeat_task, done_task, retry_task, dead_task])
        await session.commit()

    now = datetime.now(timezone.utc)
    async with sessions() as session:
        heartbeat_changed = await tasks_repo.heartbeat(
            session,
            task_id=heartbeat_task.id,
            lease_until=now + timedelta(hours=1),
            now=now,
            worker_id="stale-delivery",
        )
        done_changed = await tasks_repo.mark_done(
            session,
            task_id=done_task.id,
            now=now,
            worker_id="stale-delivery",
        )
        retry_changed = await tasks_repo.reschedule_for_retry(
            session,
            task_id=retry_task.id,
            error="stale failure",
            next_run_at=now + timedelta(minutes=5),
            worker_id="stale-delivery",
        )
        dead_changed = await tasks_repo.mark_dead(
            session,
            task_id=dead_task.id,
            now=now,
            error="stale failure",
            worker_id="stale-delivery",
        )
        await session.commit()

    assert not heartbeat_changed
    assert not done_changed
    assert not retry_changed
    assert not dead_changed
    async with sessions() as session:
        rows = await tasks_repo.list_by_ids(
            session,
            [heartbeat_task.id, done_task.id, retry_task.id, dead_task.id],
        )
    by_id = {row.id: row for row in rows}
    assert all(row.status == "running" for row in rows)
    assert all(row.locked_by == current_owner for row in rows)
    assert by_id[heartbeat_task.id].lease_expires_at == original_lease
    assert by_id[retry_task.id].last_error is None
    assert by_id[dead_task.id].last_error is None
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("exhausted", [False, True])
async def test_recovery_snapshot_cannot_steal_a_renewed_lease(
    exhausted: bool,
) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    owner = "live-delivery"
    task = _task(owner=owner)
    selected_at = datetime.now(timezone.utc)
    task.lease_expires_at = selected_at - timedelta(minutes=5)
    task.attempts = task.max_attempts if exhausted else 1
    async with sessions() as session:
        session.add(task)
        await session.commit()

    async with sessions() as session:
        stale_rows = await tasks_repo.list_stale_running(
            session,
            now=selected_at,
            limit=10,
        )
        assert [row.id for row in stale_rows] == [task.id]
        old_lease = stale_rows[0].lease_expires_at
        assert old_lease is not None

        renewed_lease = selected_at + timedelta(hours=1)
        assert await tasks_repo.heartbeat(
            session,
            task_id=task.id,
            lease_until=renewed_lease,
            now=selected_at,
            worker_id=owner,
        )
        if exhausted:
            changed = await tasks_repo.mark_running_dead(
                session,
                task_id=task.id,
                now=selected_at,
                error="stale recovery",
                previous_worker_id=owner,
                previous_lease_expires_at=old_lease,
            )
        else:
            changed = await tasks_repo.revive_running_to_pending(
                session,
                task_id=task.id,
                now=selected_at,
                previous_worker_id=owner,
                previous_lease_expires_at=old_lease,
            )
        await session.commit()

    assert not changed
    async with sessions() as session:
        current = await session.get(Task, task.id)
        assert current is not None
        assert current.status == "running"
        assert current.locked_by == owner
        assert current.lease_expires_at == renewed_lease
        assert current.last_error is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_failed_fenced_heartbeat_cancels_the_old_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Session:
        async def commit(self) -> None:
            return None

    @asynccontextmanager
    async def test_session_scope():
        yield _Session()

    async def lost_heartbeat(*_args, **_kwargs) -> bool:
        return False

    monkeypatch.setattr(runner_module, "session_scope", test_session_scope)
    monkeypatch.setattr(tasks_repo, "heartbeat", lost_heartbeat)
    runner = TaskRunner(Settings(llm_default_api_key="test-key"))
    monkeypatch.setattr(
        runner,
        "_current_settings",
        lambda: SimpleNamespace(
            worker_heartbeat_seconds=0,
            worker_lease_seconds=60,
        ),
    )

    handler_started = asyncio.Event()

    async def blocked_handler() -> None:
        handler_started.set()
        await asyncio.Event().wait()

    handler_task = asyncio.create_task(blocked_handler())
    await handler_started.wait()
    await runner._heartbeat("task-1", "stale-owner", handler_task)

    with pytest.raises(asyncio.CancelledError):
        await handler_task
