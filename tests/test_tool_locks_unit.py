from __future__ import annotations

import asyncio
from types import SimpleNamespace

from library.agent.tool_locks import (
    _advisory_lock_id,
    session_execution_lock,
    tool_execution_lock,
)


class _PostgresSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, int]]] = []

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    async def execute(self, statement, parameters):  # noqa: ANN001
        self.calls.append((str(statement), parameters))


def test_advisory_lock_id_is_stable_and_session_scoped() -> None:
    first = _advisory_lock_id("session", "session-1", "tool")
    assert first == _advisory_lock_id("session", "session-1", "tool")
    assert first != _advisory_lock_id("session", "session-2", "tool")
    assert -(2**63) <= first < 2**63


def test_session_serial_acquires_transaction_advisory_lock() -> None:
    async def scenario():
        db = _PostgresSession()
        async with tool_execution_lock(
            db,
            concurrency="session_serial",
            session_id="session-1",
            tool_name="generate_chart",
        ):
            pass
        return db.calls

    calls = asyncio.run(scenario())
    assert calls == [(
        "SELECT pg_advisory_xact_lock(:lock_id)",
        {
            "lock_id": _advisory_lock_id(
                "session", "session-1", "generate_chart",
            ),
        },
    )]


def test_parallel_tool_does_not_acquire_advisory_lock() -> None:
    async def scenario():
        db = _PostgresSession()
        async with tool_execution_lock(
            db,
            concurrency="parallel",
            session_id="session-1",
            tool_name="read_files",
        ):
            pass
        return db.calls

    assert asyncio.run(scenario()) == []


def test_agent_turn_acquires_session_advisory_lock() -> None:
    async def scenario():
        db = _PostgresSession()
        async with session_execution_lock(db, session_id="session-1"):
            pass
        return db.calls

    assert asyncio.run(scenario()) == [(
        "SELECT pg_advisory_xact_lock(:lock_id)",
        {"lock_id": _advisory_lock_id("turn", "session-1")},
    )]
