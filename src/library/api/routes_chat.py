"""Chat HTTP route — DESIGN.md §12.2 / plan §5.5.

  POST /chat/{session_id}      — run one user turn as SSE event stream

The agent runtime (`library.agent.runtime.run_turn`) is an async
generator yielding AgentEvent frames. This route wraps it as a proper
text/event-stream response. Each frame becomes one SSE event with
`event:` set to event_type and `data:` carrying the payload.

Event types (see AgentEvent docstring): conversation / planning / plan /
thinking / tool_call / tool_result / answer / error / done.

reflect_turn is enqueued by run_turn at finalize time, before the `done`
event is yielded — there's no separate end-of-turn hook.

## Per-session serialisation

`run_turn` is documented (agent/runtime.py module docstring) as assuming
one in-flight turn per session — concurrent calls race on the
`latest_turn_index() + 1` read-modify-write and silently write two
conversations with the same turn_index.

We enforce that here with a per-session asyncio.Lock, held for the
entire lifetime of the SSE stream. Locks live in a plain dict keyed by
session_id. We don't bother evicting — sessions are coarse and
long-lived (one per UI tab open), and a Lock is ~200 bytes; the
process restarts long before this becomes a memory concern.
(WeakValueDictionary was tried first; it doesn't work because the lock
has no other strong reference between requests, so each call sees a
fresh lock and the serialisation collapses.)

Cross-process safety is the database's job: `conversations` carries
UNIQUE(session_id, turn_index), so a multi-worker Postgres deploy still
fails closed (the second writer hits IntegrityError) instead of
producing duplicate rows.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from library.agent.runtime import run_turn
from library.agent.tool_locks import session_execution_lock
from library.agent.types import AgentTurnError, ChatMode, RunOptions
from library.config import get_settings
from library.capacity import CapacityExceeded, enforce_chat_concurrency
from library.llm import ImageBlock
from library.db.models import Conversation, Session as SessionRow
from library.db.session import get_session, session_scope
from library.repositories import sessions as session_service
from library.repositories import agent_events as agent_events_repo
from library.repositories.task_outcomes import record_outcome
from library.schemas.chat import SSE_200_RESPONSE, SSE_OPENAPI_EXTRA
from library.schemas.errors import CHAT_ERROR_RESPONSES, CHAT_RESUME_RESPONSES

router = APIRouter(tags=["chat"])
log = logging.getLogger(__name__)


_SESSION_LOCKS: dict[str, asyncio.Lock] = {}
_CHAT_CAPACITY_LOCK = asyncio.Lock()
_BACKGROUND_TURNS: set[asyncio.Task[None]] = set()
_ACTIVE_TURNS: dict[str, asyncio.Task[None]] = {}
CLIENT_STOPPED_MESSAGE = "Chat turn was stopped by the client."


def _lock_for(session_id: str) -> asyncio.Lock:
    """Return the lock for `session_id`, creating one on first access.

    Single-threaded asyncio loop: get-or-create is race-free without
    any extra synchronisation.
    """
    lock = _SESSION_LOCKS.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _SESSION_LOCKS[session_id] = lock
    return lock


@asynccontextmanager
async def _turn_lock(session_id: str):
    """Serialize a session locally and across PostgreSQL worker processes."""
    async with _lock_for(session_id):
        async with session_scope() as lock_db:
            async with session_execution_lock(lock_db, session_id=session_id):
                yield


_ALLOWED_IMAGE_MEDIA_TYPES: frozenset[str] = frozenset({
    "image/png", "image/jpeg", "image/gif", "image/webp",
})


class ChatImage(BaseModel):
    # Mirrors library.llm.ImageBlock's wire shape. `data_b64` is the RAW
    # image bytes base64-encoded, with no "data:" URI prefix. media_type is a
    # plain str here (not a Literal) so an unsupported value is rejected with
    # an explicit HTTP 400 in post_chat rather than a generic 422 — matching
    # the documented wire contract.
    media_type: str
    data_b64: str


class ChatBody(BaseModel):
    query: str
    mode: ChatMode = "auto"
    # Images belong to the CURRENT turn only. They are never persisted as
    # bytes into conversation history and never re-sent on later turns.
    images: list[ChatImage] = []


def _decoded_len(data_b64: str) -> int:
    """Decoded byte length of a base64 string without allocating the bytes.

    Standard base64 encodes 3 bytes per 4 chars; trailing '=' padding
    shrinks the final group. This over-estimates by at most 2 bytes, which
    is fine for a size cap. We ignore embedded whitespace/newlines the way
    a lenient decoder would, so the cap can't be dodged by padding the
    payload with newlines.
    """
    core = "".join(data_b64.split())
    padding = core.count("=")
    return max(0, (len(core) * 3) // 4 - padding)


def _validate_chat_images(images: list[ChatImage]) -> list[ImageBlock]:
    """Enforce per-turn count + per-image decoded-size caps, then convert to
    the runtime ImageBlock type. Raises HTTPException(413) on over-cap.

    Called eagerly in post_chat before the SSE stream opens so the client
    gets a real HTTP status instead of an in-stream error frame. media_type
    is already constrained to the allowed Literal by pydantic, so an invalid
    type produces a 422 at request parsing (documented as the 400-class
    rejection in the wire contract).
    """
    settings = get_settings()
    if len(images) > settings.chat_image_max_count:
        raise HTTPException(status_code=413, detail={
            "error": "too_many_images",
            "max_count": settings.chat_image_max_count,
            "received": len(images),
        })
    blocks: list[ImageBlock] = []
    for idx, img in enumerate(images):
        if img.media_type not in _ALLOWED_IMAGE_MEDIA_TYPES:
            raise HTTPException(status_code=400, detail={
                "error": "unsupported_media_type",
                "index": idx,
                "media_type": img.media_type,
                "allowed": sorted(_ALLOWED_IMAGE_MEDIA_TYPES),
            })
        size = _decoded_len(img.data_b64)
        if size > settings.chat_image_max_bytes:
            raise HTTPException(status_code=413, detail={
                "error": "image_too_large",
                "index": idx,
                "max_bytes": settings.chat_image_max_bytes,
                "decoded_bytes": size,
            })
        blocks.append(ImageBlock(
            media_type=img.media_type,  # type: ignore[arg-type]
            data_b64=img.data_b64,
        ))
    return blocks


def _timeout_message(timeout_seconds: float) -> str:
    return f"Chat turn exceeded {timeout_seconds:g} seconds and was stopped."


async def _finish_interrupted_turn(
    *,
    session_id: str,
    conversation_id: str | None,
    reason: str,
    message: str,
    fallback_to_latest: bool = False,
) -> None:
    """Finalize an interrupted conversation so replay never shows a stale spinner."""
    async with session_scope() as db:
        conv = None
        if conversation_id:
            conv = await session_service.get_conversation(db, conversation_id)
        if conv is None and fallback_to_latest:
            conv = await session_service.latest_unfinished_conversation(db, session_id)
        if conv is None or conv.session_id != session_id or conv.ended_at is not None:
            return
        await session_service.finalize_conversation(
            db,
            conversation_id=conv.id,
            agent_response=message,
        )
        await record_outcome(
            db,
            task_kind="run_turn",
            object_kind="conversation",
            object_id=conv.id,
            outcome="error",
            detail={
                "session_id": session_id,
                "error": message,
                "interrupted": reason,
            },
        )
        await db.commit()


@router.post(
    "/chat/{session_id}",
    response_class=EventSourceResponse,
    responses={200: SSE_200_RESPONSE, **CHAT_ERROR_RESPONSES},
    openapi_extra=SSE_OPENAPI_EXTRA,
)
async def post_chat(
    session_id: str,
    body: ChatBody,
    db: AsyncSession = Depends(get_session),
) -> Any:
    s = await db.get(SessionRow, session_id)
    if s is None or s.deleted_at is not None:
        raise HTTPException(status_code=404, detail="session not found")
    if s.ended_at is not None:
        await session_service.reopen_session(db, session_id=session_id)
        await db.commit()

    # Validate + convert images eagerly, before the SSE stream opens, so an
    # over-cap request fails with a real HTTP status instead of an in-stream
    # error frame the browser would surface as a "successful" stream.
    images = _validate_chat_images(body.images)

    settings = get_settings()
    stale_seconds = (
        settings.agent_turn_timeout_seconds
        if settings.agent_turn_timeout_seconds > 0
        else 86_400.0
    )
    conversation_ready: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    def start_background(*, capacity_reserved: bool) -> asyncio.Task[None]:
        task = asyncio.create_task(
            _run_durable_turn(
                session_id=session_id,
                user_message=body.query,
                images=images,
                mode=body.mode,
                conversation_ready=conversation_ready,
                capacity_reserved=capacity_reserved,
            ),
            name=f"chat-turn:{session_id}",
        )
        _BACKGROUND_TURNS.add(task)
        task.add_done_callback(_BACKGROUND_TURNS.discard)
        return task

    if settings.chat_concurrency_limit > 0:
        # Hold the local lock and PostgreSQL transaction advisory lock until
        # the reserved conversation has been created. This makes rejection a
        # real HTTP 429, rather than an error frame after SSE headers were sent.
        async with _CHAT_CAPACITY_LOCK:
            await enforce_chat_concurrency(
                db,
                limit=settings.chat_concurrency_limit,
                stale_before=datetime.now(timezone.utc) - timedelta(
                    seconds=max(300.0, stale_seconds)
                ),
            )
            task = start_background(capacity_reserved=True)
            try:
                await asyncio.shield(conversation_ready)
                await db.commit()
            except BaseException:
                await db.rollback()
                if not task.done():
                    task.cancel()
                raise
    else:
        start_background(capacity_reserved=False)

    async def event_stream() -> AsyncIterator[dict[str, str]]:
        try:
            conversation_id = await asyncio.shield(conversation_ready)
        except Exception as exc:
            yield {"event": "error", "data": str(exc)}
            return
        async for frame in _replay_frames(
            conversation_id=conversation_id,
            after_cursor=0,
        ):
            yield frame

    return EventSourceResponse(
        event_stream(),
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


async def _persist_event(
    *,
    conversation_id: str,
    event: str,
    data: str,
) -> None:
    async with session_scope() as db:
        await agent_events_repo.append(
            db,
            conversation_id=conversation_id,
            event=event,
            data=data,
        )
        await db.commit()


async def _run_durable_turn(
    *,
    session_id: str,
    user_message: str,
    images: list[ImageBlock],
    mode: ChatMode,
    conversation_ready: asyncio.Future[str],
    capacity_reserved: bool = False,
) -> None:
    """Run independently from the attached SSE response and persist progress."""
    conversation_id: str | None = None
    timeout_seconds = get_settings().agent_turn_timeout_seconds

    async def execute() -> None:
        nonlocal conversation_id
        async with _turn_lock(session_id):
            async for ev in run_turn(
                session_id=session_id,
                user_message=user_message,
                images=images,
                options=RunOptions(mode=mode),
                capacity_reserved=capacity_reserved,
            ):
                if ev.event_type == "conversation" and ev.data:
                    conversation_id = ev.data
                    _ACTIVE_TURNS[conversation_id] = asyncio.current_task()  # type: ignore[assignment]
                if conversation_id is None:
                    continue
                await _persist_event(
                    conversation_id=conversation_id,
                    event=ev.event_type,
                    data=ev.data,
                )
                if not conversation_ready.done():
                    conversation_ready.set_result(conversation_id)

    try:
        if timeout_seconds > 0:
            async with asyncio.timeout(timeout_seconds):
                await execute()
        else:
            await execute()
    except TimeoutError:
        message = _timeout_message(timeout_seconds)
        await _finish_interrupted_turn(
            session_id=session_id,
            conversation_id=conversation_id,
            reason="timeout",
            message=message,
            fallback_to_latest=True,
        )
        if conversation_id is not None:
            await _persist_event(
                conversation_id=conversation_id, event="error", data=message
            )
    except asyncio.CancelledError:
        await asyncio.shield(_finish_interrupted_turn(
            session_id=session_id,
            conversation_id=conversation_id,
            reason="client_cancelled",
            message=CLIENT_STOPPED_MESSAGE,
            fallback_to_latest=True,
        ))
        if conversation_id is not None:
            await asyncio.shield(_persist_event(
                conversation_id=conversation_id,
                event="error",
                data=CLIENT_STOPPED_MESSAGE,
            ))
    except AgentTurnError as exc:
        message = str(exc)
        await _finish_interrupted_turn(
            session_id=session_id,
            conversation_id=conversation_id,
            reason="agent_error",
            message=message,
        )
        if conversation_id is not None:
            await _persist_event(
                conversation_id=conversation_id, event="error", data=message
            )
        elif not conversation_ready.done():
            conversation_ready.set_exception(exc)
    except CapacityExceeded as exc:
        if not conversation_ready.done():
            conversation_ready.set_exception(exc)
    except Exception as exc:
        log.exception("chat turn failed for session %s", session_id)
        message = str(exc)
        await _finish_interrupted_turn(
            session_id=session_id,
            conversation_id=conversation_id,
            reason="exception",
            message=message,
            fallback_to_latest=True,
        )
        if conversation_id is not None:
            await _persist_event(
                conversation_id=conversation_id, event="error", data=message
            )
        elif not conversation_ready.done():
            conversation_ready.set_exception(exc)
    finally:
        if conversation_id is not None:
            _ACTIVE_TURNS.pop(conversation_id, None)
        if not conversation_ready.done():
            conversation_ready.set_exception(
                AgentTurnError("chat turn ended before a conversation was created")
            )


async def _replay_frames(
    *,
    conversation_id: str,
    after_cursor: int,
) -> AsyncIterator[dict[str, str]]:
    cursor = max(0, int(after_cursor))
    idle_after_terminal = 0
    while True:
        async with session_scope() as db:
            rows = await agent_events_repo.list_after(
                db,
                conversation_id=conversation_id,
                after_cursor=cursor,
            )
            conversation = await db.get(Conversation, conversation_id)
            terminal = conversation is None or conversation.ended_at is not None
            latest_event = await agent_events_repo.latest_event_name(
                db, conversation_id=conversation_id,
            )
        for row in rows:
            cursor = row.cursor
            yield {
                "event": row.event,
                "data": row.data,
                "id": str(row.cursor),
            }
        if terminal and latest_event in {"done", "error"} and not rows:
            return
        if terminal and latest_event is None and not rows:
            return
        if terminal and not rows:
            idle_after_terminal += 1
            # A final conversation commit happens just before the terminal
            # public event is written in its own transaction. Allow that write
            # to catch up; only use the bounded fallback for legacy or damaged
            # turns that genuinely have no terminal ledger row.
            if idle_after_terminal >= 20:
                return
        else:
            idle_after_terminal = 0
        await asyncio.sleep(0.1)


@router.get(
    "/conversations/{conversation_id}/events",
    response_class=EventSourceResponse,
    responses={200: SSE_200_RESPONSE, **CHAT_RESUME_RESPONSES},
    openapi_extra=SSE_OPENAPI_EXTRA,
)
async def resume_chat_events(
    conversation_id: str,
    after_cursor: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    db: AsyncSession = Depends(get_session),
) -> EventSourceResponse:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    cursor = after_cursor
    if last_event_id and last_event_id.isdigit():
        cursor = max(cursor, int(last_event_id))
    return EventSourceResponse(
        _replay_frames(conversation_id=conversation_id, after_cursor=cursor),
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.post("/conversations/{conversation_id}/cancel", status_code=202)
async def cancel_chat_turn(
    conversation_id: str,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    task = _ACTIVE_TURNS.get(conversation_id)
    if task is None or task.done():
        return {"conversation_id": conversation_id, "cancelled": False}
    task.cancel()
    return {"conversation_id": conversation_id, "cancelled": True}
