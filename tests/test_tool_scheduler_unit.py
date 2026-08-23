from __future__ import annotations

import asyncio

from library.agent.tool_scheduler import (
    ScheduledTool,
    run_tool_schedule,
    schedule_waves,
)


def _call(
    index: int,
    key: str,
    concurrency: str = "parallel",
) -> ScheduledTool[str]:
    return ScheduledTool(
        index=index,
        cache_key=key,
        concurrency=concurrency,  # type: ignore[arg-type]
        value=key,
    )


def test_schedule_waves_make_serial_and_duplicate_calls_barriers() -> None:
    calls = [
        _call(0, "a"),
        _call(1, "b"),
        _call(2, "a"),
        _call(3, "serial", "session_serial"),
        _call(4, "c"),
        _call(5, "global", "global_serial"),
    ]

    waves = schedule_waves(calls)

    assert [[call.index for call in wave] for wave in waves] == [
        [0, 1],
        [2],
        [3],
        [4],
        [5],
    ]


def test_tool_schedule_is_bounded_and_returns_model_order() -> None:
    async def scenario():
        active = 0
        maximum = 0

        async def execute(call: ScheduledTool[str]) -> str:
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep((6 - call.index) * 0.001)
            active -= 1
            return f"result-{call.index}"

        result = await run_tool_schedule(
            [_call(index, f"key-{index}") for index in range(6)],
            max_parallelism=2,
            execute=execute,
        )
        return result, maximum

    result, maximum = asyncio.run(scenario())

    assert maximum == 2
    assert result.results == tuple(f"result-{index}" for index in range(6))
    assert result.stopped_indices == ()


def test_tool_schedule_stop_drains_started_calls_without_starting_more() -> None:
    async def scenario():
        failed = asyncio.Event()
        started: list[int] = []
        completed: list[int] = []

        async def should_stop(_call: ScheduledTool[str]) -> bool:
            return failed.is_set()

        async def execute(call: ScheduledTool[str]) -> int:
            started.append(call.index)
            if call.index == 0:
                failed.set()
            await asyncio.sleep(0.001)
            completed.append(call.index)
            return call.index

        result = await run_tool_schedule(
            [
                _call(0, "a"),
                _call(1, "b"),
                _call(2, "serial", "session_serial"),
            ],
            max_parallelism=2,
            execute=execute,
            should_stop=should_stop,
        )
        return result, started, completed

    result, started, completed = asyncio.run(scenario())

    assert started == [0, 1]
    assert completed == [0, 1]
    assert result.results == (0, 1, None)
    assert result.stopped_indices == (2,)


def test_duplicate_cache_keys_never_overlap() -> None:
    async def scenario():
        active_keys: set[str] = set()
        overlaps: list[str] = []

        async def execute(call: ScheduledTool[str]) -> int:
            if call.cache_key in active_keys:
                overlaps.append(call.cache_key)
            active_keys.add(call.cache_key)
            await asyncio.sleep(0.001)
            active_keys.remove(call.cache_key)
            return call.index

        result = await run_tool_schedule(
            [_call(0, "same"), _call(1, "other"), _call(2, "same")],
            max_parallelism=3,
            execute=execute,
        )
        return result, overlaps

    result, overlaps = asyncio.run(scenario())

    assert overlaps == []
    assert result.results == (0, 1, 2)
