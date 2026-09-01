"""Process-wide lifecycle manager for the in-process TaskRunner.

The single-process deployment runs the task runner inside the
API process (uvicorn). ``main.py`` used to construct a ``TaskRunner``
directly in its lifespan, which made it impossible to start or stop the
worker from the Settings page without a process restart. This module owns
the one ``TaskRunner`` instance for the process and exposes idempotent,
lock-guarded ``start``/``stop`` so an API call can toggle it live.

Split deployments (an external ``library-worker`` daemon) are unaffected:
the web toggle only ever controls this process's in-process runner. Two
workers coexisting is safe — they coordinate through the tasks table's
claim / lease protocol.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from library.tasks.runner import TaskRunner

log = logging.getLogger(__name__)

_runner: TaskRunner | None = None
_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


async def start() -> bool:
    """Start the in-process runner. No-op (returns False) if already running
    or if another process already holds a fresh queue claim."""
    global _runner
    async with _get_lock():
        if _runner is not None and _runner.is_running:
            return False
        if await queue_claimed():
            log.info(
                "skipping in-process task runner; another worker already holds "
                "a fresh queue claim"
            )
            return False
        runner = TaskRunner()
        await runner.start()
        _runner = runner
        log.info("in-process task runner started")
        return True


async def stop() -> bool:
    """Stop the in-process runner, draining in-flight tasks. No-op otherwise.

    Draining (awaiting the in-flight handlers) means a toggle-off never
    abandons work mid-run; pending tasks simply stay queued for the next
    start.
    """
    global _runner
    async with _get_lock():
        if _runner is None:
            return False
        runner = _runner
        _runner = None
        await runner.stop()
        log.info("in-process task runner stopped")
        return True


def is_running() -> bool:
    """True while this process's runner is alive and polling."""
    runner = _runner
    return runner is not None and runner.is_running


def _fresh_claim_cutoff() -> datetime:
    from library.config import get_settings

    seconds = max(1, int(get_settings().worker_heartbeat_seconds or 20))
    return datetime.now(timezone.utc) - timedelta(seconds=seconds * 3)


async def queue_claimed() -> bool:
    """True when a running task has a recent heartbeat from some worker."""
    from library.db.session import session_scope
    from library.repositories import tasks as tasks_repo

    try:
        async with session_scope() as session:
            return await tasks_repo.has_fresh_claim(
                session, since=_fresh_claim_cutoff(),
            )
    except Exception:
        log.exception("failed to inspect queue claim heartbeat")
        return False


async def status_running() -> bool:
    """True if this process's runner is up, or a daemon still holds a claim."""
    return is_running() or await queue_claimed()


async def reset() -> None:
    """Test hook: tear the singleton down so a fresh test starts clean.

    Called by ``tests/conftest.py::_restore_module_test_state`` at module
    boundaries. The lock is cleared unconditionally (NOT acquired) first: a
    lock bound to a previous event loop must never leak into the next module,
    and there is no shared-state to serialize here anyway.
    """
    global _runner, _lock
    _lock = None
    runner = _runner
    _runner = None
    if runner is not None:
        try:
            await runner.stop()
        except (asyncio.CancelledError, Exception):
            # The runner's polling-loop task (and its lock) may be bound to
            # an event loop that has already closed — a test left a live
            # runner across a module boundary, and _restore_module_test_state
            # runs in a fresh loop. Awaiting that lock/task raises
            # CancelledError (a BaseException, hence the explicit tuple).
            # There is nothing drainable left — the globals are already
            # cleared — so the stop is best-effort.
            log.warning(
                "worker_lifecycle.reset(): runner stop failed across loops",
                exc_info=True,
            )
