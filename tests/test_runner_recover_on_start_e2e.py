"""WORKER-H1: TaskRunner.start recovers expired-lease running rows.

Recover used to run only as a periodic_tick fan-out. A crashed tick left
status=running with an expired lease, bootstrap treated it as inflight, and
the dispatcher never came back. Scheduler-disabled workers had the same hole
for ingest_file.

These tests drive start() with `_run` idled so the polling loop cannot claim
the recovered rows before we inspect them. The runner is always stopped.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from library.config import get_settings
from library.db.engine import dispose_engine, get_engine
from library.db.models import Base, Task
from library.db.session import session_scope
from library.repositories import tasks as tasks_repo
from library.tasks.handlers.periodic_tick import (
    TICK_INTERVAL_SECONDS,
    bootstrap_periodic_tick,
    periodic_tick_dedup_key,
)
from library.tasks.kinds import KIND_INGEST_FILE, KIND_PERIODIC_TICK
from library.tasks.runner import TaskRunner
from library.utils.ids import new_id


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _prepare_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    *,
    scheduler_enabled: bool = True,
) -> None:
    monkeypatch.setenv("LIBRARY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("WORKER_ENABLED", "false")
    monkeypatch.setenv(
        "WORKER_SCHEDULER_ENABLED",
        "true" if scheduler_enabled else "false",
    )
    monkeypatch.setenv("LLM_DEFAULT_API_KEY", "sk-fake")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "fake-model")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    await dispose_engine()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _stuck_task(
    *,
    kind: str,
    lease_expires_at: datetime | None,
    dedup_key: str | None = None,
    attempts: int = 1,
) -> Task:
    now = _now()
    return Task(
        id=new_id(),
        kind=kind,
        payload={},
        dedup_key=dedup_key,
        status="running",
        priority=50,
        attempts=attempts,
        max_attempts=5,
        scheduled_at=now - timedelta(minutes=10),
        lease_expires_at=lease_expires_at,
        locked_by="dead-worker",
        created_at=now - timedelta(minutes=15),
        started_at=now - timedelta(minutes=10),
        last_heartbeat_at=lease_expires_at,
    )


async def _start_without_claiming(runner: TaskRunner) -> None:
    async def _idle() -> None:
        await runner._stop.wait()  # type: ignore[attr-defined]

    runner._run = _idle  # type: ignore[method-assign]
    await runner.start()


async def _get_task(task_id: str) -> Task:
    async with session_scope() as session:
        row = await session.get(Task, task_id)
        assert row is not None
        session.expunge(row)
        return row


@pytest.mark.asyncio
async def test_start_recovers_expired_periodic_tick(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    await _prepare_home(monkeypatch, tmp_path)
    now = _now()
    stuck = _stuck_task(
        kind=KIND_PERIODIC_TICK,
        lease_expires_at=now - timedelta(seconds=120),
        dedup_key=periodic_tick_dedup_key(now - timedelta(seconds=TICK_INTERVAL_SECONDS)),
    )
    async with session_scope() as session:
        session.add(stuck)
        await session.commit()
        stuck_id = stuck.id

    runner = TaskRunner()
    try:
        await _start_without_claiming(runner)
        recovered = await _get_task(stuck_id)
        assert recovered.status == "pending"
        assert recovered.locked_by is None
        assert recovered.lease_expires_at is None

        async with session_scope() as session:
            ticks = (
                await session.execute(
                    select(Task).where(Task.kind == KIND_PERIODIC_TICK)
                )
            ).scalars().all()
        pending_or_running = [
            t for t in ticks if t.status in ("pending", "running")
        ]
        assert pending_or_running, "start must recover the tick or enqueue a successor"
        assert all(
            t.status != "running" or (
                t.lease_expires_at is not None and t.lease_expires_at >= _now()
            )
            for t in pending_or_running
        )
    finally:
        await runner.stop()


@pytest.mark.asyncio
async def test_start_recovers_expired_ingest_when_scheduler_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    await _prepare_home(monkeypatch, tmp_path, scheduler_enabled=False)
    stuck = _stuck_task(
        kind=KIND_INGEST_FILE,
        lease_expires_at=_now() - timedelta(seconds=120),
        dedup_key=f"{KIND_INGEST_FILE}:stuck",
    )
    async with session_scope() as session:
        session.add(stuck)
        await session.commit()
        stuck_id = stuck.id

    runner = TaskRunner()
    try:
        await _start_without_claiming(runner)
        recovered = await _get_task(stuck_id)
        assert recovered.status == "pending"
        assert recovered.locked_by is None
        assert recovered.lease_expires_at is None

        async with session_scope() as session:
            ticks = (
                await session.execute(
                    select(Task.id).where(Task.kind == KIND_PERIODIC_TICK)
                )
            ).scalars().all()
        assert ticks == [], "scheduler-disabled start must not bootstrap a tick"
    finally:
        await runner.stop()


@pytest.mark.asyncio
async def test_start_does_not_recover_live_lease(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    await _prepare_home(monkeypatch, tmp_path, scheduler_enabled=False)
    live = _stuck_task(
        kind=KIND_INGEST_FILE,
        lease_expires_at=_now() + timedelta(minutes=5),
        dedup_key=f"{KIND_INGEST_FILE}:live",
    )
    async with session_scope() as session:
        session.add(live)
        await session.commit()
        live_id = live.id
        live_lease = live.lease_expires_at
        live_locked = live.locked_by

    runner = TaskRunner()
    try:
        await _start_without_claiming(runner)
        row = await _get_task(live_id)
        assert row.status == "running"
        assert row.locked_by == live_locked
        assert row.lease_expires_at == live_lease
    finally:
        await runner.stop()


@pytest.mark.asyncio
async def test_has_inflight_ignores_expired_running_lease(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    await _prepare_home(monkeypatch, tmp_path)
    now = _now()
    expired = _stuck_task(
        kind=KIND_PERIODIC_TICK,
        lease_expires_at=now - timedelta(seconds=30),
        dedup_key="tick:expired",
    )
    live = _stuck_task(
        kind=KIND_INGEST_FILE,
        lease_expires_at=now + timedelta(minutes=5),
        dedup_key="ingest:live",
    )
    null_lease = _stuck_task(
        kind="normalize_tags",
        lease_expires_at=None,
        dedup_key="normalize:null-lease",
    )
    pending = Task(
        id=new_id(),
        kind="prune",
        payload={},
        dedup_key="prune:pending",
        status="pending",
        priority=100,
        attempts=0,
        max_attempts=5,
        scheduled_at=now,
        created_at=now,
    )
    async with session_scope() as session:
        session.add_all([expired, live, null_lease, pending])
        await session.commit()

        assert await tasks_repo.has_inflight_for_kind(
            session, KIND_PERIODIC_TICK, now=now,
        ) is False
        assert await tasks_repo.has_inflight_for_kind(
            session, KIND_INGEST_FILE, now=now,
        ) is True
        assert await tasks_repo.has_inflight_for_kind(
            session, "normalize_tags", now=now,
        ) is True
        assert await tasks_repo.has_inflight_for_kind(
            session, "prune", now=now,
        ) is True
        assert await tasks_repo.has_inflight_for_kind(
            session, "no_such_kind", now=now,
        ) is False


@pytest.mark.asyncio
async def test_bootstrap_enqueues_when_only_tick_lease_is_expired(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    await _prepare_home(monkeypatch, tmp_path)
    now = _now()
    stuck = _stuck_task(
        kind=KIND_PERIODIC_TICK,
        lease_expires_at=now - timedelta(seconds=120),
        dedup_key=periodic_tick_dedup_key(
            now - timedelta(seconds=TICK_INTERVAL_SECONDS),
        ),
    )
    async with session_scope() as session:
        session.add(stuck)
        await session.commit()
        stuck_id = stuck.id

    await bootstrap_periodic_tick()

    async with session_scope() as session:
        ticks = (
            await session.execute(
                select(Task).where(Task.kind == KIND_PERIODIC_TICK)
            )
        ).scalars().all()
    assert any(t.id != stuck_id and t.status == "pending" for t in ticks), (
        "bootstrap must enqueue a successor when the only tick lease is expired"
    )
    stuck_row = next(t for t in ticks if t.id == stuck_id)
    assert stuck_row.status == "running"
