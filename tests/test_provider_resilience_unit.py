from __future__ import annotations

import asyncio
import random
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from PIL import Image

from library.agent import runtime as agent_runtime
from library.agent.tools import ToolContext
from library.api import routes_settings
from library.config import Settings, resolve_profile
from library.llm.openai_adapter import OpenAIChatClient
from library.llm.types import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ImageBlock,
    TokenUsage,
)
from library.pipelines import pdf as pdf_pipeline
from library.provider_clients import (
    close_provider_clients,
    get_anthropic_client,
    get_openai_compatible_client,
    get_provider_http_client,
)
import library.provider_clients as provider_clients
from library.semantic.embeddings import (
    DashScopeEmbeddingClient,
    EmbeddingProviderError,
    EmbeddingResult,
    _validate_embedding_result,
)
from library.semantic.index import _description_text
from library.semantic.rerank import BailianRerankClient, RerankProviderError


def test_provider_http_client_is_reused_and_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[Any] = []
    sdk_created: list[Any] = []
    anthropic_created: list[Any] = []

    class FakeClient:
        def __init__(self, **_kwargs: Any) -> None:
            self.is_closed = False
            created.append(self)

        async def aclose(self) -> None:
            self.is_closed = True

    class FakeOpenAI:
        def __init__(self, **_kwargs: Any) -> None:
            self.closed = False
            sdk_created.append(self)

        async def close(self) -> None:
            self.closed = True

    class FakeAnthropic(FakeOpenAI):
        def __init__(self, **_kwargs: Any) -> None:
            self.closed = False
            anthropic_created.append(self)

    monkeypatch.setattr(provider_clients.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(provider_clients, "AsyncOpenAI", FakeOpenAI)
    monkeypatch.setattr(provider_clients, "AsyncAnthropic", FakeAnthropic)

    async def scenario() -> None:
        first = get_provider_http_client()
        assert get_provider_http_client() is first
        sdk = get_openai_compatible_client(
            api_key="test-key",
            base_url="https://models.example/v1",
        )
        assert get_openai_compatible_client(
            api_key="test-key",
            base_url="https://models.example/v1/",
        ) is sdk
        anthropic = get_anthropic_client(
            api_key="test-key",
            base_url="https://anthropic.example",
        )
        assert get_anthropic_client(
            api_key="test-key",
            base_url="https://anthropic.example/",
        ) is anthropic
        await close_provider_clients()
        assert first.is_closed
        assert sdk.closed
        assert anthropic.closed
        assert get_provider_http_client() is not first
        await close_provider_clients()

    asyncio.run(scenario())
    assert len(created) == 2
    assert len(sdk_created) == 1
    assert len(anthropic_created) == 1


def test_embedding_validation_rejects_wrong_dimensions() -> None:
    with pytest.raises(EmbeddingProviderError, match="dimension mismatch"):
        _validate_embedding_result(
            EmbeddingResult(vectors=[[1.0, 0.0]]),
            expected=1,
            dimensions=3,
        )


def test_dashscope_embedding_uses_shared_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    class FakeHTTP:
        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]):
            del headers
            texts = list(json["input"]["texts"])
            calls.append(texts)
            return httpx.Response(
                200,
                json={
                    "output": {
                        "embeddings": [
                            {"text_index": index, "embedding": [1.0, 0.0]}
                            for index, _text in enumerate(texts)
                        ]
                    },
                    "usage": {"total_tokens": len(texts)},
                },
                request=httpx.Request("POST", url),
            )

    fake_http = FakeHTTP()
    monkeypatch.setattr(
        "library.semantic.embeddings.get_provider_http_client",
        lambda: fake_http,
    )
    settings = Settings(
        _env_file=None,
        embedding_provider="dashscope",
        embedding_api_key="test-key",
        embedding_dimensions=2,
        embedding_batch_size=2,
    )

    result = asyncio.run(
        DashScopeEmbeddingClient(settings).embed(["a", "b", "c"], text_type="query")
    )

    assert calls == [["a", "b"], ["c"]]
    assert len(result.vectors) == 3
    assert result.total_tokens == 3


def test_rerank_rejects_empty_provider_response(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeHTTP:
        async def post(self, url: str, **_kwargs: Any):
            return httpx.Response(
                200,
                json={"results": []},
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(
        "library.semantic.rerank.get_provider_http_client",
        lambda: FakeHTTP(),
    )
    settings = Settings(
        _env_file=None,
        rerank_enabled=True,
        rerank_api_key="test-key",
    )

    with pytest.raises(RerankProviderError, match="no valid results"):
        asyncio.run(BailianRerankClient(settings).rerank("query", ["document"]))


def test_llm_probe_uses_compatible_output_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeChat:
        model = "test-model"
        provider = "openai-compatible"

        async def complete(self, request: Any, *, retry: bool = True) -> ChatResponse:
            captured["max_tokens"] = request.max_tokens
            captured["retry"] = retry
            return ChatResponse(
                text="pong",
                tool_calls=[],
                stop_reason="end_turn",
                usage=TokenUsage(),
            )

    settings = Settings(
        _env_file=None,
        llm_default_api_key="test-key",
        llm_default_base_url="https://llm.example/v1",
        llm_default_model="test-model",
    )
    monkeypatch.setattr(routes_settings, "get_settings", lambda: settings)
    monkeypatch.setattr(routes_settings, "get_chat_client", lambda _profile: FakeChat())

    result = asyncio.run(routes_settings._probe_llm_profile("chat"))

    assert result["ok"] is True
    assert result["model"] == "test-model"
    assert result["provider"] == "openai-compatible"
    assert result["mode"] == "text"
    assert result["duration_ms"] >= 0
    assert captured == {"max_tokens": 64, "retry": False}


def test_openai_adapter_obeys_explicit_model_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class Completions:
        async def create(self, **kwargs: Any) -> Any:
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content="ok", tool_calls=[]),
                    finish_reason="stop",
                )],
                usage=SimpleNamespace(prompt_tokens=2, completion_tokens=1),
            )

    fake_sdk = SimpleNamespace(
        chat=SimpleNamespace(completions=Completions()),
    )
    monkeypatch.setattr(
        "library.llm.openai_adapter.get_openai_compatible_client",
        lambda **_kwargs: fake_sdk,
    )
    settings = Settings(
        _env_file=None,
        llm_default_provider="openai-compatible",
        llm_default_api_key="test-key",
        llm_default_model="test-model",
        llm_chat_dialect="openrouter",
        llm_chat_supports_temperature=False,
        llm_chat_token_limit_param="max_tokens",
    )
    client = OpenAIChatClient(resolve_profile(settings, "chat"))

    response = asyncio.run(client.complete(ChatRequest(
        system=None,
        messages=[ChatMessage(role="user", content="ping")],
        max_tokens=17,
        temperature=0.3,
    )))

    assert response.text == "ok"
    assert client._compat_dialect == "openrouter"
    assert captured["max_tokens"] == 17
    assert "max_completion_tokens" not in captured
    assert "temperature" not in captured


def test_vision_probe_sends_real_image(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeChat:
        model = "vision-model"
        provider = "openai-compatible"

        async def complete(self, request: Any, *, retry: bool = True) -> ChatResponse:
            captured["content"] = request.messages[0].content
            captured["max_tokens"] = request.max_tokens
            captured["retry"] = retry
            return ChatResponse(
                text="white",
                tool_calls=[],
                stop_reason="end_turn",
                usage=TokenUsage(),
            )

    settings = Settings(
        _env_file=None,
        llm_default_api_key="default-key",
        llm_vision_provider="openai-compatible",
        llm_vision_api_key="vision-key",
        llm_vision_base_url="https://vision.example/v1",
        llm_vision_model="vision-model",
    )
    monkeypatch.setattr(routes_settings, "get_settings", lambda: settings)
    monkeypatch.setattr(routes_settings, "get_chat_client", lambda _profile: FakeChat())

    result = asyncio.run(routes_settings._probe_llm_profile("vision"))

    assert result["ok"] is True
    assert result["mode"] == "image"
    assert captured["max_tokens"] == 256
    assert captured["retry"] is False
    assert any(isinstance(block, ImageBlock) for block in captured["content"])


def test_retrieval_provider_diagnostics_validate_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeEmbedding:
        async def embed(self, texts: list[str], *, text_type: str) -> EmbeddingResult:
            assert texts == ["ping"]
            assert text_type == "query"
            return EmbeddingResult(vectors=[[1.0, 0.0]])

    class FakeRerank:
        async def rerank(self, query: str, documents: list[str], *, top_n: int):
            assert query == documents[0]
            assert top_n == 1
            return [SimpleNamespace(index=0)]

    settings = Settings(
        _env_file=None,
        semantic_recall_enabled=True,
        embedding_api_key="embedding-key",
        embedding_dimensions=2,
        embedding_model="embedding-model",
        rerank_enabled=True,
        rerank_api_key="rerank-key",
        rerank_model="rerank-model",
    )
    monkeypatch.setattr(routes_settings, "get_settings", lambda: settings)
    monkeypatch.setattr(routes_settings, "get_embedding_client", lambda _s: FakeEmbedding())
    monkeypatch.setattr(routes_settings, "get_rerank_client", lambda _s: FakeRerank())

    embedding = asyncio.run(routes_settings._probe_embedding())
    rerank = asyncio.run(routes_settings._probe_rerank())

    assert embedding["ok"] is True
    assert embedding["dimensions"] == 2
    assert embedding["model"] == "embedding-model"
    assert rerank["ok"] is True
    assert rerank["model"] == "rerank-model"


def test_tool_dispatch_bounds_parallel_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    active = 0
    maximum = 0

    async def fake_run_tool(_registration: Any, _ctx: Any, tool_call: Any):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep((6 - tool_call.arguments["index"]) * 0.001)
        active -= 1
        return 1, {"index": tool_call.arguments["index"]}, None

    async def fake_persist(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(agent_runtime, "get_tool", lambda _name: object())
    monkeypatch.setattr(agent_runtime, "_run_tool", fake_run_tool)
    monkeypatch.setattr(agent_runtime, "_persist_tool_call", fake_persist)
    monkeypatch.setattr(
        agent_runtime,
        "get_settings",
        lambda: SimpleNamespace(agent_max_parallel_tool_calls=2),
    )
    calls = [
        SimpleNamespace(id=f"call-{index}", name="unit_tool", arguments={"index": index})
        for index in range(6)
    ]

    async def scenario() -> tuple[list[Any], list[Any]]:
        result_blocks: list[Any] = []
        events = [
            event
            async for event in agent_runtime._dispatch_tool_calls(
                tool_calls=calls,
                ctx=ToolContext(session_id="session", conversation_id="conversation"),
                conversation_id="conversation",
                result_blocks=result_blocks,
                guard=agent_runtime._CallGuard(),
            )
        ]
        return events, result_blocks

    events, result_blocks = asyncio.run(scenario())

    assert maximum == 2
    assert len(result_blocks) == 6
    assert sum(event.event_type == "tool_result" for event in events) == 6


class _FakePdfPage:
    def get_size(self) -> tuple[float, float]:
        return 612.0, 792.0

    def get_bbox(self) -> tuple[float, float, float, float]:
        return 0.0, 0.0, 612.0, 792.0

    def get_objects(self, **_kwargs: Any) -> list[Any]:
        return []


def test_pdf_vision_render_scale_is_capped() -> None:
    scale = pdf_pipeline._pdf_vision_render_scale(_FakePdfPage())
    assert scale * 72.0 == pytest.approx(pdf_pipeline.PDF_VISION_MAX_DPI)


def test_pdf_vision_jpeg_fits_request_budget() -> None:
    size = (1_400, 1_400)
    body = random.Random(20260818).randbytes(size[0] * size[1] * 3)
    source = Image.frombytes("RGB", size, body)
    try:
        encoded = pdf_pipeline._encode_pdf_vision_jpeg(source, effective_dpi=150.0)
    finally:
        source.close()

    assert (
        pdf_pipeline._pdf_vision_data_url_chars(encoded)
        <= pdf_pipeline.PDF_VISION_MAX_DATA_URL_CHARS
    )


def test_pdf_vision_batches_by_page_count_and_payload() -> None:
    sizes = [200_000, 200_000, 200_000, 300_000, 300_000, 200_000, 200_000]
    pages = [(index, b"x" * size) for index, size in enumerate(sizes, start=1)]

    batches = pdf_pipeline._pdf_vision_page_batches(pages)

    assert [[page for page, _jpeg in batch] for batch in batches] == [
        [1, 2, 3],
        [4, 5],
        [6, 7],
    ]


def test_pdf_vision_question_is_bounded_after_json_escaping() -> None:
    question = "照明要求\n" * 20_000
    bounded = pdf_pipeline._bounded_pdf_vision_question(question)
    assert len(bounded) < len(question)
    assert (
        pdf_pipeline._json_string_chars(bounded)
        <= pdf_pipeline.PDF_VISION_MAX_QUESTION_CHARS
    )


def test_pdf_multi_image_rejection_falls_back_to_single_pages() -> None:
    class FakeChat:
        def __init__(self) -> None:
            self.calls: list[int] = []

        async def complete(self, request: Any) -> ChatResponse:
            images = sum(
                type(block).__name__ == "ImageBlock"
                for block in request.messages[0].content
            )
            self.calls.append(images)
            if images > 1:
                raise RuntimeError("provider does not accept multiple images")
            return ChatResponse(
                text="visible evidence",
                tool_calls=[],
                stop_reason="end_turn",
                usage=TokenUsage(),
            )

    chat = FakeChat()
    answers, request_count, fallback = asyncio.run(
        pdf_pipeline._answer_pdf_question_pages(
            client=chat,
            pages=[(1, b"one"), (2, b"two"), (3, b"three")],
            question="What is visible?",
        )
    )

    assert chat.calls == [3, 1, 1, 1]
    assert request_count == 4
    assert fallback is True
    assert [answer.splitlines()[0] for answer in answers] == [
        "[Page 1]",
        "[Page 2]",
        "[Page 3]",
    ]


def test_semantic_text_skips_placeholder_titles_but_keeps_named_sections() -> None:
    text = _description_text({
        "sections": [
            {"title": "Document"},
            {"title": "Section 1"},
            {"title": "Page 2"},
            {"title": "OCR Page 3"},
            {"title": "Lines 1-80"},
            {"title": "Section 1: Introduction"},
            {"title": "第一章 安全要求"},
            {"title": "3.2 故障恢复"},
        ]
    })

    assert "section: Document" not in text
    assert "section: Section 1\n" not in f"{text}\n"
    assert "section: OCR Page 3" not in text
    assert "Section 1: Introduction" in text
    assert "第一章 安全要求" in text
    assert "3.2 故障恢复" in text
