# Quality Guidelines

> Code quality standards for backend development.

---

## Overview

<!--
Document your project's quality standards here.

Questions to answer:
- What patterns are forbidden?
- What linting rules do you enforce?
- What are your testing requirements?
- What code review standards apply?
-->

(To be filled by the team)

---

## Forbidden Patterns

<!-- Patterns that should never be used and why -->

(To be filled by the team)

---

## Required Patterns

### Ingest persist is write-once on `ingested_at`

`ingest_file._persist` only writes `summary` / `description` / `kind` / `extra`
when `File.ingested_at is None`. Any path that must re-index an existing file
(Finder in-place edit, user reprocess) has to clear `ingested_at` and enqueue
with `dedup_key=f"ingest_file:{file_id}"`. Reuse `reprocess_file` — do not add
a third half-reset. `apply_modified` is a caller of `reprocess_file` after it
updates sha256/size.

Regression: `tests/test_sync_modified_reingest_e2e.py`.

### TaskRunner.start recovers expired leases before bootstrap

`TaskRunner.start` must call `handle_recover_stuck_tasks` unconditionally
(not gated on LLM key or scheduler) **before** `bootstrap_periodic_tick`.
`has_inflight_for_kind` treats only `pending` and still-leased `running` as
inflight; an expired-lease `running` row must not block a successor tick.
Do not recover still-heartbeating leases (existing CAS + grace window).

Regression: `tests/test_runner_recover_on_start_e2e.py`.

### Process-wide owned resources live in a lifecycle singleton

Any resource that is process-scoped and must be startable/stoppable at runtime
(not just at process start/end) — the in-process `TaskRunner` is the canonical
example — must NOT be constructed ad-hoc inside `main.py`'s lifespan. It lives
in a module-level singleton with idempotent, lock-guarded entry points.

See `src/library/services/worker_lifecycle.py`:

```python
_runner: TaskRunner | None = None
_lock: asyncio.Lock | None = None

async def start() -> bool:
    global _runner
    async with _get_lock():
        if _runner is not None and _runner.is_running:
            return False          # idempotent — no-op when already running
        runner = TaskRunner()
        await runner.start()
        _runner = runner
        return True

async def stop() -> bool:
    global _runner
    async with _get_lock():
        if _runner is None:
            return False          # no-op when not running
        runner = _runner
        _runner = None
        await runner.stop()       # drain in-flight work, never abandon it
        return True

def is_running() -> bool:
    runner = _runner
    return runner is not None and runner.is_running
```

Rules:
- `start()` / `stop()` are **idempotent** — concurrent callers race on an
  `asyncio.Lock`, exactly one call actually starts/stops.
- The singleton must expose a `reset()` test hook and be torn down in
  `tests/conftest.py::_restore_module_test_state` (see Testing Requirements).
- Toggle-on/off from an API handler maps 1:1 onto `start()`/`stop()`; a live
  status getter (`is_running()`) is separate from the *configured* intent
  (`worker_enabled`).

---

## Testing Requirements

### Tear down process-wide singletons at module boundaries

`worker_lifecycle._runner` (and any future process-wide singleton) must be
reset in `tests/conftest.py::_restore_module_test_state`, which already runs at
the start and end of every module. Without this, a runner left running by one
test module makes the next module see `is_running() == True` and fail
web-toggle baselines.

```python
# inside _restore_module_test_state()
runner = worker_lifecycle._runner
worker_lifecycle._runner = None
worker_lifecycle._lock = None
if runner is not None and runner.is_running:
    asyncio.run(runner.stop())
```

Note the `_lock` reset: a lock bound to a previous event loop must not leak into
the next module either.

### Never reset a running singleton via monkeypatch teardown

**Forbidden**: using `monkeypatch.setattr` in a fixture's teardown to "clear" a
singleton attribute. `monkeypatch` records the value present at teardown time as
the thing to restore — if that value is a *running* runner, monkeypatch's undo
puts it right back, leaking state into the next test/module.

```python
# BAD — the running FakeRunner is captured as the "original" and re-restored
@pytest.fixture
def runner(monkeypatch):
    ...
    yield
    monkeypatch.setattr(wl, "_runner", None)   # undo restores the runner!

# GOOD — direct assignment; nothing to re-restore
@pytest.fixture
def runner(monkeypatch):
    ...
    yield
    wl._runner = None
    wl._lock = None
```

The same rule applies to any process-wide singleton fixture, not just
`worker_lifecycle`.

### Cross-loop teardown: `stop()` awaits a loop-bound lock/task

`tests/conftest.py::_restore_module_test_state` runs in a fresh event loop
(`asyncio.run`). If a test leaves a *real* `TaskRunner` running, that runner's
polling-loop task and internal lock are bound to the test's (now-closed) loop.
Calling `runner.stop()` from the fresh loop awaits that dead loop's lock/task
and raises `asyncio.CancelledError`.

Two layers of defense (both needed):

1. **Tests stop their own runner** before returning — leave the module with the
   runner stopped so teardown never joins a loop-bound task.
2. **`reset()` swallows the stop failure** — catch
   `(asyncio.CancelledError, Exception)` (CancelledError is a `BaseException`,
   so `except Exception` alone will NOT catch it). The globals are already
   cleared before the stop, so the stop is best-effort.

```python
# worker_lifecycle.reset()
_runner = None
if runner is not None:
    try:
        await runner.stop()
    except (asyncio.CancelledError, Exception):
        log.warning("runner stop failed across loops", exc_info=True)
```

---

## Code Review Checklist

<!-- What reviewers should check -->

(To be filled by the team)
