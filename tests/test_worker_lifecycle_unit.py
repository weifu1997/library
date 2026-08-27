"""worker_lifecycle: in-process runner singleton semantics.

The lifecycle manager is the process-wide owner of the TaskRunner. It is
tested with an injected fake runner so the unit tests never touch a real
database or claim real tasks — the DB-facing behavior is covered by the
existing e2e tests (test_worker_e2e.py).
"""
from __future__ import annotations

import asyncio

import pytest

import library.services.worker_lifecycle as wl


class FakeRunner:
    """Minimal stand-in for TaskRunner: tracks start/stop, no I/O."""

    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    @property
    def is_running(self) -> bool:
        return self.started and not self.stopped

    async def start(self) -> None:
        if self.started:
            raise AssertionError("start() must only be called once per instance")
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


@pytest.fixture
def fake_runner(monkeypatch: pytest.MonkeyPatch):
    """Inject a FakeRunner factory and tear the singleton down after each test.

    The fixture also clears the lazy lock so a fresh event loop per test
    never reuses a lock bound to a previous loop.
    """
    instances: list[FakeRunner] = []

    def factory() -> FakeRunner:
        runner = FakeRunner()
        instances.append(runner)
        return runner

    monkeypatch.setattr(wl, "TaskRunner", factory)
    yield instances
    # Direct assignment, not monkeypatch: monkeypatch would record the
    # (possibly running) runner as the value to restore, and its undo would
    # put it right back, leaking state into the next test / module.
    wl._runner = None
    wl._lock = None


async def test_start_is_idempotent_and_stop_drains(fake_runner) -> None:
    assert wl.is_running() is False

    assert await wl.start() is True
    assert wl.is_running() is True
    assert len(fake_runner) == 1

    # Already running → no-op, same instance, no second start.
    assert await wl.start() is False
    assert len(fake_runner) == 1
    assert fake_runner[0].started is True

    assert await wl.stop() is True
    assert wl.is_running() is False
    assert fake_runner[0].stopped is True

    # Not running → no-op.
    assert await wl.stop() is False


async def test_concurrent_starts_create_single_runner(fake_runner) -> None:
    results = await asyncio.gather(*[wl.start() for _ in range(10)])
    # Exactly one call actually started the runner; the rest saw it running.
    assert sum(1 for r in results if r is True) == 1
    assert len(fake_runner) == 1
    assert wl.is_running() is True


async def test_concurrent_stop_is_safe(fake_runner) -> None:
    await wl.start()
    results = await asyncio.gather(*[wl.stop() for _ in range(5)])
    assert sum(1 for r in results if r is True) == 1
    assert wl.is_running() is False
    assert all(r.stopped for r in fake_runner)


async def test_restart_after_stop_creates_fresh_runner(fake_runner) -> None:
    await wl.start()
    await wl.stop()
    await wl.start()
    assert len(fake_runner) == 2
    assert wl.is_running() is True


class _FakeSessionScope:
    """Minimal async context manager stand-in for session_scope()."""

    def __init__(self, counts: dict[str, int]) -> None:
        self._counts = counts

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> bool:
        return False


async def _patch_guard(
    monkeypatch: pytest.MonkeyPatch, pending: int,
) -> None:
    import library.main as main

    async def fake_count(db) -> dict[str, int]:
        return {"running": 0, "pending": pending}

    monkeypatch.setattr(main.tasks_repo, "count_running_and_pending", fake_count)
    monkeypatch.setattr(
        main, "session_scope", lambda: _FakeSessionScope({"pending": pending})
    )


async def test_startup_guard_warns_when_disabled_with_pending(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    import library.main as main

    await _patch_guard(monkeypatch, pending=3)
    with caplog.at_level(logging.WARNING):
        await main._warn_if_worker_disabled_with_pending()
    assert "3 task(s)" in caplog.text
    assert "WORKER_ENABLED=false" in caplog.text
    assert "library-worker" in caplog.text


async def test_startup_guard_silent_when_nothing_pending(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    import library.main as main

    await _patch_guard(monkeypatch, pending=0)
    with caplog.at_level(logging.WARNING):
        await main._warn_if_worker_disabled_with_pending()
    assert "pending and will not be processed" not in caplog.text
