"""End-to-end checks for persisted chat image attachments (v0.3.3 follow-up).

Pasted chat images are now saved to disk purely for UI re-display when a
user switches away from a session and back. They are served through a
dedicated endpoint and surfaced on the transcript, but they are NEVER
re-sent to the LLM — history replay stays text-only ('[image attached]').

Covered here:
  (a) a chat turn with an image writes attachments/<conv_id>/1.png and the
      transcript (GET /sessions/{id}/messages) returns that turn with a
      non-empty attachments list;
  (b) GET /conversations/{id}/attachments/1.png returns the bytes + image/png;
  (c) a traversal name (../../etc/passwd) or wrong extension (1.txt) is
      rejected (404 / validation returns None);
  (d) the message tape is unchanged — the persisted user_message is still the
      '[image attached]' placeholder and no image bytes are re-sent on a
      later turn (mirrors tests/test_multimodal_chat_e2e.py conventions).

Run:
    .venv/bin/pytest tests/test_chat_attachments_e2e.py -q
"""
from __future__ import annotations

import asyncio
import base64
import os
import sys
from pathlib import Path
from uuid import uuid4

_TEST_PARENT = Path(os.environ.get("LIBRARY_TEST_TMP", Path(__file__).resolve().parent))
_TEST_ROOT = _TEST_PARENT / f"_chat_attachments_e2e_data_{os.getpid()}_{uuid4().hex[:8]}"
_TEST_ROOT.mkdir(parents=True)

os.environ["LIBRARY_HOME"] = str(_TEST_ROOT)
os.environ["STORAGE_BACKEND"] = "local"
os.environ["WORKER_ENABLED"] = "false"
os.environ["LLM_DEFAULT_API_KEY"] = "sk-fake"
os.environ["LLM_DEFAULT_MODEL"] = "fake-model"
os.environ["LIBRARY_CHAT_IMAGE_MAX_COUNT"] = "4"
os.environ["LIBRARY_CHAT_IMAGE_MAX_BYTES"] = "5000"
# Direct-send path (images reach the chat model): skip the auto probe so the
# saved images are the ones actually passed into run_turn.
os.environ["LIBRARY_CHAT_VISION"] = "on"

import httpx
from httpx import ASGITransport
from sqlalchemy import select

from library.config import get_settings

get_settings.cache_clear()  # type: ignore[attr-defined]

from library.db.bootstrap import bootstrap_schema
from library.db.engine import get_session_factory
from library.db.models import Conversation
from library.llm.types import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ImageBlock,
    TokenUsage,
)
from library.main import app
from library.services.attachments import attachments_root, read_attachment

# A real 1x1 transparent PNG (~70 bytes decoded).
_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
_PNG_BYTES = base64.b64decode(_PNG_B64)


async def _create_schema() -> None:
    await bootstrap_schema()


# ---- fake chat: plan (no tools) then a single execute answer ----------------

class _FakeChat:
    profile_name = "chat"
    model = "fake-chat"

    def __init__(self) -> None:
        self.requests: list[ChatRequest] = []

    async def complete(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        if not request.tools:
            return ChatResponse(
                text="Plan: inspect the attached image and answer.",
                tool_calls=[],
                stop_reason="end_turn",
                usage=TokenUsage(input_tokens=30, output_tokens=5),
                parsed_json=None,
            )
        return ChatResponse(
            text="The image shows a tiny test pixel.",
            tool_calls=[],
            stop_reason="end_turn",
            usage=TokenUsage(input_tokens=40, output_tokens=7),
            parsed_json=None,
        )


def _install(fake: _FakeChat) -> None:
    import library.agent.runtime as r
    r.get_chat_client = lambda profile="chat": fake  # type: ignore[assignment]


# ---- helpers ----------------------------------------------------------------

async def _consume_sse(
    client: httpx.AsyncClient, path: str, body: dict,
) -> list[dict]:
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


def _conversation_id(events: list[dict]) -> str:
    for e in events:
        if e["event"] == "conversation" and e["data"]:
            return e["data"]
    raise AssertionError(f"no conversation event in stream: {events}")


def _any_image_block(requests: list[ChatRequest]) -> bool:
    for req in requests:
        for msg in req.messages:
            if isinstance(msg.content, list) and any(
                isinstance(b, ImageBlock) for b in msg.content
            ):
                return True
    return False


async def _new_session(client: httpx.AsyncClient, msg: str) -> str:
    resp = await client.post("/v1/sessions", json={
        "initiating_user_message": msg,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["session_id"]


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
    )


# ---- (a) image saved to disk + surfaced on the transcript -------------------

async def test_image_saved_and_in_transcript() -> None:
    fake = _FakeChat()
    _install(fake)
    async with _client() as client:
        sid = await _new_session(client, "attachment probe")
        events = await _consume_sse(client, f"/v1/chat/{sid}", {
            "query": "what is in this image",
            "images": [{"media_type": "image/png", "data_b64": _PNG_B64}],
        })
        assert any(e["event"] == "done" for e in events), events
        conv_id = _conversation_id(events)

        # File landed under attachments/<conv_id>/1.png with the real bytes.
        path = attachments_root(get_settings()) / conv_id / "1.png"
        assert path.is_file(), f"expected saved attachment at {path}"
        assert path.read_bytes() == _PNG_BYTES

        # Transcript surfaces the attachment on the image-bearing turn.
        resp = await client.get(f"/v1/sessions/{sid}/messages")
        assert resp.status_code == 200, resp.text
        turns = resp.json()["turns"]
        assert len(turns) == 1, turns
        assert turns[0]["attachments"] == [
            {"name": "1.png", "media_type": "image/png"}
        ], turns[0]
    print("[a] image saved to disk and surfaced on the transcript")


# ---- (b) serve endpoint returns bytes + correct Content-Type ----------------

async def test_serve_endpoint_returns_image_bytes() -> None:
    fake = _FakeChat()
    _install(fake)
    async with _client() as client:
        sid = await _new_session(client, "serve probe")
        events = await _consume_sse(client, f"/v1/chat/{sid}", {
            "query": "describe",
            "images": [{"media_type": "image/png", "data_b64": _PNG_B64}],
        })
        conv_id = _conversation_id(events)

        resp = await client.get(f"/v1/conversations/{conv_id}/attachments/1.png")
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == "image/png", resp.headers
        assert resp.content == _PNG_BYTES

        # A missing index is a clean 404.
        missing = await client.get(f"/v1/conversations/{conv_id}/attachments/2.png")
        assert missing.status_code == 404, missing.text
    print("[b] serve endpoint returns bytes + image/png")


# ---- (c) traversal / wrong-extension names are rejected ---------------------

async def test_bad_names_rejected() -> None:
    fake = _FakeChat()
    _install(fake)
    async with _client() as client:
        sid = await _new_session(client, "traversal probe")
        events = await _consume_sse(client, f"/v1/chat/{sid}", {
            "query": "describe",
            "images": [{"media_type": "image/png", "data_b64": _PNG_B64}],
        })
        conv_id = _conversation_id(events)

        # Wrong extension: matches the route but fails strict validation.
        resp = await client.get(f"/v1/conversations/{conv_id}/attachments/1.txt")
        assert resp.status_code == 404, resp.text

    # Direct validation: traversal + wrong-extension names must return None,
    # even though a real "1.png" for this conversation exists on disk.
    assert read_attachment(conv_id, "1.png") is not None
    assert read_attachment(conv_id, "../../etc/passwd") is None
    assert read_attachment(conv_id, "1.txt") is None
    assert read_attachment(conv_id, "../1.png") is None
    assert read_attachment(conv_id, "1/2.png") is None
    print("[c] traversal / wrong-extension names rejected")


# ---- (d) message tape unchanged: placeholder persisted, no bytes re-sent ----

async def test_history_tape_unchanged() -> None:
    fake = _FakeChat()
    _install(fake)
    async with _client() as client:
        sid = await _new_session(client, "tape probe")

        # Turn 0: query + image.
        await _consume_sse(client, f"/v1/chat/{sid}", {
            "query": "describe this",
            "images": [{"media_type": "image/png", "data_b64": _PNG_B64}],
        })

        # Turn 1: text only. Its resumed history replays turn 0 from the DB.
        boundary = len(fake.requests)
        await _consume_sse(client, f"/v1/chat/{sid}", {
            "query": "and now what about it",
        })
        turn1_requests = fake.requests[boundary:]

    # Persisted turn-0 text carries the placeholder, not image bytes.
    factory = get_session_factory()
    async with factory() as s:
        rows = (
            await s.execute(
                select(Conversation.turn_index, Conversation.user_message)
                .where(Conversation.session_id == sid)
                .order_by(Conversation.turn_index)
            )
        ).all()
    by_index = {idx: text for idx, text in rows}
    assert by_index[0] == "describe this [image attached]", by_index
    assert "[image attached]" not in (by_index.get(1) or ""), by_index

    # Turn 1 (including replayed history) must carry NO image bytes...
    assert not _any_image_block(turn1_requests), (
        "saving attachments must not re-send image bytes on a later turn"
    )
    # ...yet the placeholder text from turn 0 must survive the replay.
    replay_text = " ".join(
        msg.content
        for req in turn1_requests
        for msg in req.messages
        if isinstance(msg.content, str)
    )
    assert "[image attached]" in replay_text, (
        "resumed history dropped the image placeholder text"
    )
    print("[d] message tape unchanged: placeholder persisted, byte-free replay")


async def main() -> None:
    await _create_schema()
    await test_image_saved_and_in_transcript()
    await test_serve_endpoint_returns_image_bytes()
    await test_bad_names_rejected()
    await test_history_tape_unchanged()
    print("\nALL CHAT ATTACHMENT E2E CHECKS PASSED")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as exc:
        print("FAIL:", exc, file=sys.stderr)
        sys.exit(1)
