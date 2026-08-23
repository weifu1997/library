"""Bounded, deterministic scheduling for one model-emitted tool-call list."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Generic, Literal, TypeVar


ToolConcurrency = Literal["parallel", "session_serial", "global_serial"]
T = TypeVar("T")
R = TypeVar("R")


@dataclass(frozen=True, slots=True)
class ScheduledTool(Generic[T]):
    """One call in the exact order emitted by the model."""

    index: int
    cache_key: str
    concurrency: ToolConcurrency
    value: T


@dataclass(frozen=True, slots=True)
class ToolScheduleResult(Generic[R]):
    """Ordered results plus calls left unstarted after a stop signal."""

    results: tuple[R | None, ...]
    stopped_indices: tuple[int, ...]


def schedule_waves(
    calls: Sequence[ScheduledTool[T]],
) -> tuple[tuple[ScheduledTool[T], ...], ...]:
    """Partition calls into parallel waves separated by serial barriers.

    A repeated cache key also starts a new wave, so equivalent calls can never
    overlap even when a caller has not pre-deduplicated the model response.
    """
    waves: list[tuple[ScheduledTool[T], ...]] = []
    current: list[ScheduledTool[T]] = []
    current_keys: set[str] = set()
    for call in calls:
        if call.concurrency != "parallel":
            if current:
                waves.append(tuple(current))
                current = []
                current_keys = set()
            waves.append((call,))
            continue
        if call.cache_key in current_keys:
            waves.append(tuple(current))
            current = []
            current_keys = set()
        current.append(call)
        current_keys.add(call.cache_key)
    if current:
        waves.append(tuple(current))
    return tuple(waves)


async def run_tool_schedule(
    calls: Sequence[ScheduledTool[T]],
    *,
    max_parallelism: int,
    execute: Callable[[ScheduledTool[T]], Awaitable[R]],
    should_stop: Callable[[ScheduledTool[T]], Awaitable[bool]] | None = None,
) -> ToolScheduleResult[R]:
    """Execute a bounded rolling pool while retaining model-call order."""
    if max_parallelism < 1:
        raise ValueError("max_parallelism must be positive")
    ordered = tuple(calls)
    if [call.index for call in ordered] != list(range(len(ordered))):
        raise ValueError("scheduled tool indices must be contiguous and ordered")

    results: list[R | None] = [None] * len(ordered)
    stopped: set[int] = set()
    stop_seen = False
    waves = schedule_waves(ordered)
    for wave_number, wave in enumerate(waves):
        if stop_seen:
            stopped.update(call.index for call in wave)
            continue

        running: dict[asyncio.Task[R], ScheduledTool[T]] = {}
        cursor = 0
        limit = 1 if wave[0].concurrency != "parallel" else max_parallelism
        while cursor < len(wave) or running:
            while not stop_seen and cursor < len(wave) and len(running) < limit:
                call = wave[cursor]
                if should_stop is not None and await should_stop(call):
                    stop_seen = True
                    stopped.update(item.index for item in wave[cursor:])
                    for later_wave in waves[wave_number + 1:]:
                        stopped.update(item.index for item in later_wave)
                    break
                cursor += 1
                task = asyncio.create_task(execute(call))
                running[task] = call
            if not running:
                break
            done, _pending = await asyncio.wait(
                running,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in sorted(done, key=lambda item: running[item].index):
                call = running.pop(task)
                results[call.index] = task.result()

    return ToolScheduleResult(
        results=tuple(results),
        stopped_indices=tuple(sorted(stopped)),
    )


__all__ = [
    "ScheduledTool",
    "ToolConcurrency",
    "ToolScheduleResult",
    "run_tool_schedule",
    "schedule_waves",
]
