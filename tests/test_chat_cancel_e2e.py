"""Stop must cancel the live conversation id, not the session id.

CHAT-H1: POST /v1/conversations/{session_id}/cancel 404s while the durable
turn keeps running. POST /v1/conversations/{conversation_id}/cancel after
the `conversation` SSE event actually cancels `_ACTIVE_TURNS`.

Run:
    uv run pytest tests/test_chat_cancel_e2e.py -q
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from pathlib import Path
from uuid import uuid4

_TEST_PARENT = Path(os.environ.get("LIBRARY_TEST_TMP", Path(__file__).resolve().parent))
_TEST_ROOT = _TEST_PARENT / f"_chat_cancel_e2e_data_{os.getpid()}_{uuid4().hex[:8]}"
_TEST_ROOT.mkdir(parents=True)
os.environ["LIBRARY_HOME"] = str(_TEST_ROOT)
os.environ["STORAGE_BACKEND"] = "local"
os.environ["WORKER_ENABLED"] = "false"
os.environ["LLM_DEFAULT_API_KEY"] = "sk-fake"
os.environ["LLM_DEFAULT_MODEL"] = "fake-model"

import httpx
from httpx import ASGITransport
from sqlalchemy import select

from library.config import get_settings
get_settings.cache_clear()  # type: ignore[attr-defined]

from library.api.routes_chat import CLIENT_STOPPED_MESSAGE, _ACTIVE_TURNS
from library.db.bootstrap import bootstrap_schema
from library.db.engine import get_session_factory
from library.db.models import AgentEvent, Conversation
from library.llm.types import ChatRequest, ChatResponse, TokenUsage
from library.main import app


async def _create_schema() -> None:
    await bootstrap_schema()


class _BarrierChat:
    """Block the plan-phase LLM call until the test releases it."""

    profile_name = "chat"
    model = "fake-chat"

    def __init__(self) -> None:
        self.calls: list[ChatRequest] = []
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def complete(self, request: ChatRequest) -> ChatResponse:
        self.calls.append(request)
        self.entered.set()
        await self.release.wait()
        return ChatResponse(
            text="NO_PLAN: ack",
            tool_calls=[],
            stop_reason="end_turn",
            usage=TokenUsage(input_tokens=10, output_tokens=2),
            parsed_json=None,
        )


def _install(client: _BarrierChat) -> None:
    import library.agent.runtime as r
    r.get_chat_client = lambda profile="chat": client  # type: ignore[assignment]


async def _consume_sse(client: httpx.AsyncClient, path: str, body: dict) -> list[dict]:
    events: list[dict] = []
    async with client.stream("POST", path, json=body) as resp:
        assert resp.status_code == 200, await resp.aread()
        event_type = "message"
        data_lines: list[str] = []
        async for line in resp.aiter_lines():
            if line == "":
                if data_lines or event_type != "message":
                    events.append({
                        "event": event_type, "data": "\n".join(data_lines),
                    })
                event_type = "message"
                data_lines = []
            elif line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
    return events


async def _latest_conversation_id(session_id: str) -> str:
    factory = get_session_factory()
    async with factory() as session:
        row = (
            await session.execute(
                select(Conversation.id)
                .where(Conversation.session_id == session_id)
                .order_by(Conversation.turn_index.desc())
            )
        ).first()
    assert row is not None, f"no conversation for session {session_id}"
    return row[0]


async def _agent_rows(conversation_id: str) -> list[tuple[str, str]]:
    factory = get_session_factory()
    async with factory() as session:
        rows = (
            await session.execute(
                select(AgentEvent.event, AgentEvent.data)
                .where(AgentEvent.conversation_id == conversation_id)
                .order_by(AgentEvent.cursor)
            )
        ).all()
    return [(row[0], row[1]) for row in rows]


async def test_cancel_by_session_id_404s_and_turn_keeps_running() -> None:
    chat = _BarrierChat()
    _install(chat)

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", timeout=30.0,
    ) as client:
        resp = await client.post("/v1/sessions", json={
            "initiating_user_message": "cancel-by-session",
        })
        assert resp.status_code == 201, resp.text
        sid = resp.json()["session_id"]

        pump = asyncio.create_task(
            _consume_sse(client, f"/v1/chat/{sid}", {"query": "hello"}),
        )
        try:
            await asyncio.wait_for(chat.entered.wait(), timeout=5.0)
            conversation_id = await _latest_conversation_id(sid)
            task = _ACTIVE_TURNS.get(conversation_id)
            assert task is not None and not task.done()

            wrong = await client.post(f"/v1/conversations/{sid}/cancel")
            assert wrong.status_code == 404, wrong.text
            assert _ACTIVE_TURNS.get(conversation_id) is task
            assert not task.done()
            names_while_blocked = [name for name, _data in await _agent_rows(conversation_id)]
            assert "error" not in names_while_blocked
            assert "answer" not in names_while_blocked

            chat.release.set()
            events = await asyncio.wait_for(pump, timeout=10.0)
        finally:
            if not chat.release.is_set():
                chat.release.set()
            if not pump.done():
                pump.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await pump

    assert any(e["event"] in {"answer", "done"} for e in events), events
    assert not any(
        e["event"] == "error" and CLIENT_STOPPED_MESSAGE in e["data"]
        for e in events
    ), events
    rows = await _agent_rows(conversation_id)
    names = [name for name, _data in rows]
    assert "answer" in names or "done" in names, rows


async def test_cancel_by_conversation_id_stops_the_durable_turn() -> None:
    chat = _BarrierChat()
    _install(chat)

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", timeout=30.0,
    ) as client:
        resp = await client.post("/v1/sessions", json={
            "initiating_user_message": "cancel-by-conversation",
        })
        assert resp.status_code == 201, resp.text
        sid = resp.json()["session_id"]

        pump = asyncio.create_task(
            _consume_sse(client, f"/v1/chat/{sid}", {"query": "hello"}),
        )
        try:
            await asyncio.wait_for(chat.entered.wait(), timeout=5.0)
            conversation_id = await _latest_conversation_id(sid)
            task = _ACTIVE_TURNS[conversation_id]
            assert not task.done()

            cancelled = await client.post(
                f"/v1/conversations/{conversation_id}/cancel",
            )
            assert cancelled.status_code == 202, cancelled.text
            body = cancelled.json()
            assert body["cancelled"] is True
            assert body["conversation_id"] == conversation_id

            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=5.0)
            assert conversation_id not in _ACTIVE_TURNS
            events = await asyncio.wait_for(pump, timeout=10.0)
        finally:
            if not chat.release.is_set():
                chat.release.set()
            if not pump.done():
                pump.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await pump

    error_idx = next(
        (
            i for i, e in enumerate(events)
            if e["event"] == "error" and CLIENT_STOPPED_MESSAGE in e["data"]
        ),
        None,
    )
    assert error_idx is not None, events
    after_cancel = events[error_idx + 1:]
    assert not any(
        e["event"] in {"answer", "plan", "tool_call", "thinking"}
        for e in after_cancel
    ), after_cancel
    assert not any(e["event"] == "answer" for e in events), events

    rows = await _agent_rows(conversation_id)
    names = [name for name, _data in rows]
    assert "error" in names, rows
    assert "answer" not in names, rows
    assert any(
        name == "error" and CLIENT_STOPPED_MESSAGE in data
        for name, data in rows
    ), rows


async def main() -> None:
    await _create_schema()
    await test_cancel_by_session_id_404s_and_turn_keeps_running()
    await test_cancel_by_conversation_id_stops_the_durable_turn()
    print("\nALL CHAT-CANCEL TESTS PASSED")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as e:
        print("FAIL:", e, file=sys.stderr)
        raise
