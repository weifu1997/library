"""End-to-end checks for multimodal chat (v0.3.3).

Pasting/dragging images into the composer sends them on the current /chat
turn as ImageBlocks (native vision). Images belong to the CURRENT turn only:
they ride the live user message but are NEVER persisted as bytes into
conversation history and NEVER re-sent on later turns.

Covered here:
  (a) a valid PNG produces a current-turn user ChatMessage whose content is
      [TextBlock, ImageBlock] reaching the (fake) chat client;
  (b) an image-only turn (blank query) is accepted;
  (c) over-count and over-size requests return HTTP 413 (before the stream);
  (d) the persisted conversation.user_message carries the '[image attached]'
      placeholder, and a subsequent turn's resumed history contains NO image
      bytes.

Run:
    .venv/bin/pytest tests/test_multimodal_chat_e2e.py -q
"""
from __future__ import annotations

import asyncio
import base64
import os
import sys
from pathlib import Path
from uuid import uuid4

_TEST_PARENT = Path(os.environ.get("LIBRARY_TEST_TMP", Path(__file__).resolve().parent))
_TEST_ROOT = _TEST_PARENT / f"_multimodal_chat_e2e_data_{os.getpid()}_{uuid4().hex[:8]}"
_TEST_ROOT.mkdir(parents=True)

os.environ["LIBRARY_HOME"] = str(_TEST_ROOT)
os.environ["STORAGE_BACKEND"] = "local"
os.environ["WORKER_ENABLED"] = "false"
os.environ["LLM_DEFAULT_API_KEY"] = "sk-fake"
os.environ["LLM_DEFAULT_MODEL"] = "fake-model"
# Small caps so the over-count / over-size checks are cheap to trigger.
os.environ["LIBRARY_CHAT_IMAGE_MAX_COUNT"] = "2"
os.environ["LIBRARY_CHAT_IMAGE_MAX_BYTES"] = "500"
# These e2e cases exercise the direct-send path (images reach the chat model);
# force it so run_turn does not first fire the auto capability probe. The
# probe/fallback logic is covered by test_vision_capability_probe below.
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
    TextBlock,
    TokenUsage,
)
from library.main import app

# A real 1x1 transparent PNG (~70 bytes decoded — well under the 500 cap).
_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


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
            # Plan phase: a normal (non-NO_PLAN) plan so execute runs too.
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


def _first_message_with_image(
    requests: list[ChatRequest],
) -> ChatMessage | None:
    for req in requests:
        for msg in req.messages:
            if isinstance(msg.content, list) and any(
                isinstance(b, ImageBlock) for b in msg.content
            ):
                return msg
    return None


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


# ---- (a) valid PNG reaches the chat client as [TextBlock, ImageBlock] -------

async def test_image_reaches_chat_client() -> None:
    fake = _FakeChat()
    _install(fake)
    async with _client() as client:
        sid = await _new_session(client, "multimodal probe")
        events = await _consume_sse(client, f"/v1/chat/{sid}", {
            "query": "what is in this image",
            "images": [{"media_type": "image/png", "data_b64": _PNG_B64}],
        })

    assert any(e["event"] == "done" for e in events), events
    assert any(e["event"] == "answer" for e in events), events

    msg = _first_message_with_image(fake.requests)
    assert msg is not None, "no ChatMessage with an ImageBlock reached the client"
    assert msg.role == "user"
    assert isinstance(msg.content, list)
    kinds = [type(b).__name__ for b in msg.content]
    assert kinds == ["TextBlock", "ImageBlock"], kinds
    text_block, image_block = msg.content
    assert isinstance(text_block, TextBlock)
    assert text_block.text == "what is in this image"
    assert isinstance(image_block, ImageBlock)
    assert image_block.media_type == "image/png"
    assert image_block.data_b64 == _PNG_B64
    print("[a] image reaches chat client as [TextBlock, ImageBlock]")


# ---- (b) image-only turn (blank query) is accepted --------------------------

async def test_image_only_turn_accepted() -> None:
    fake = _FakeChat()
    _install(fake)
    async with _client() as client:
        sid = await _new_session(client, "image only probe")
        events = await _consume_sse(client, f"/v1/chat/{sid}", {
            "query": "",
            "images": [{"media_type": "image/png", "data_b64": _PNG_B64}],
        })

    assert any(e["event"] == "done" for e in events), events
    assert not any(e["event"] == "error" for e in events), events

    msg = _first_message_with_image(fake.requests)
    assert msg is not None
    # Blank caption => no leading TextBlock, image block only.
    assert isinstance(msg.content, list)
    assert [type(b).__name__ for b in msg.content] == ["ImageBlock"]
    print("[b] image-only (blank query) turn accepted")


# ---- (c) over-count and over-size return 413 --------------------------------

async def test_over_count_and_over_size_return_413() -> None:
    fake = _FakeChat()
    _install(fake)
    async with _client() as client:
        sid = await _new_session(client, "cap probe")

        # Over-count: cap is 2, send 3 tiny valid images.
        resp = await client.post(f"/v1/chat/{sid}", json={
            "query": "too many",
            "images": [
                {"media_type": "image/png", "data_b64": _PNG_B64}
                for _ in range(3)
            ],
        })
        assert resp.status_code == 413, resp.text
        assert resp.json()["detail"]["error"] == "too_many_images"

        # Over-size: cap is 500 bytes decoded; 800 bytes exceeds it.
        big = base64.b64encode(b"x" * 800).decode("ascii")
        resp = await client.post(f"/v1/chat/{sid}", json={
            "query": "too big",
            "images": [{"media_type": "image/png", "data_b64": big}],
        })
        assert resp.status_code == 413, resp.text
        assert resp.json()["detail"]["error"] == "image_too_large"

        # Bonus: unsupported media type is a 400 (matches wire contract).
        resp = await client.post(f"/v1/chat/{sid}", json={
            "query": "bad type",
            "images": [{"media_type": "image/tiff", "data_b64": _PNG_B64}],
        })
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"]["error"] == "unsupported_media_type"

    # None of the rejected turns should have driven the LLM.
    assert fake.requests == [], "capped requests must not reach the chat client"
    print("[c] over-count / over-size => 413, bad media_type => 400")


# ---- (d) placeholder persisted; resumed history carries no image bytes ------

async def test_history_stays_text_only() -> None:
    fake = _FakeChat()
    _install(fake)
    async with _client() as client:
        sid = await _new_session(client, "history probe")

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

    # Turn 1 (including its resumed history) must contain NO image bytes...
    assert not _any_image_block(turn1_requests), (
        "resumed history re-sent image bytes on a later turn"
    )
    # ...yet the placeholder text from turn 0 must be present in the replay.
    replay_text = " ".join(
        msg.content
        for req in turn1_requests
        for msg in req.messages
        if isinstance(msg.content, str)
    )
    assert "[image attached]" in replay_text, (
        "resumed history dropped the image placeholder text"
    )
    print("[d] placeholder persisted; resumed history is image-byte-free")


class _ProbeClient:
    """Fake chat client for the capability probe: either accepts image input
    or rejects it with a vision-unsupported 400, counting probe calls."""

    def __init__(self, model: str, *, rejects_images: bool) -> None:
        self.provider = "openai-compatible"
        self.model = model
        self._rejects = rejects_images
        self.calls = 0

    async def complete(self, request: ChatRequest) -> ChatResponse:
        self.calls += 1
        if self._rejects:
            from openai import BadRequestError
            raise BadRequestError(
                "This model does not support image input",
                response=httpx.Response(400, request=httpx.Request("POST", "http://x")),
                body=None,
            )
        return ChatResponse(
            text="ok", tool_calls=[], stop_reason="end_turn",
            usage=TokenUsage(input_tokens=1, output_tokens=1), parsed_json=None,
        )


async def test_vision_capability_probe() -> None:
    # (chat_vision="auto") The probe classifies a model once and caches it.
    import library.agent.runtime as r
    saved = r.get_chat_client
    try:
        r._vision_capability.clear()
        vis = _ProbeClient("vision-model", rejects_images=False)
        r.get_chat_client = lambda profile="chat": vis  # type: ignore[assignment]
        assert await r._chat_model_supports_vision() is True
        assert await r._chat_model_supports_vision() is True  # cached
        assert vis.calls == 1, f"expected one probe then cache, got {vis.calls}"

        r._vision_capability.clear()
        txt = _ProbeClient("text-only-model", rejects_images=True)
        r.get_chat_client = lambda profile="chat": txt  # type: ignore[assignment]
        assert await r._chat_model_supports_vision() is False
        assert await r._chat_model_supports_vision() is False  # cached
        assert txt.calls == 1, f"expected one probe then cache, got {txt.calls}"
    finally:
        r.get_chat_client = saved  # type: ignore[assignment]
        r._vision_capability.clear()

    # Classifier: only image/vision errors degrade to the describe fallback.
    assert r._looks_like_vision_unsupported(Exception("model does not support image input"))
    assert r._looks_like_vision_unsupported(Exception("vision is not enabled for this model"))
    assert not r._looks_like_vision_unsupported(Exception("invalid api key"))
    assert not r._looks_like_vision_unsupported(Exception("rate limit exceeded"))
    print("[e] vision capability probe classifies + caches per model")


async def main() -> None:
    await _create_schema()
    await test_image_reaches_chat_client()
    await test_image_only_turn_accepted()
    await test_over_count_and_over_size_return_413()
    await test_history_stays_text_only()
    await test_vision_capability_probe()
    print("\nALL MULTIMODAL CHAT E2E CHECKS PASSED")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as exc:
        print("FAIL:", exc, file=sys.stderr)
        sys.exit(1)
