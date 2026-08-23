"""Unit tests for the bounded retry-with-backoff wrapper around chat
completions in ``_UsageRecordingChatClient`` (audit 二.3). Transient provider
failures (rate limits, 5xx/overloaded, connection/timeout) are retried; a
BadRequestError / other 4xx is not, and a persistent failure exhausts retries
and re-raises so the caller sees the real error."""
from __future__ import annotations

import httpx
import pytest

from library.llm import factory
from library.llm.factory import _UsageRecordingChatClient
from library.llm.types import ChatMessage, ChatRequest, ChatResponse, TokenUsage

_REQUEST = ChatRequest(
    system=None,
    messages=[ChatMessage(role="user", content="hello")],
    max_tokens=32,
)


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make backoff instant and rate-pacing a no-op so the tests are fast and
    hermetic (the token bucket carries process-global state otherwise)."""
    monkeypatch.setattr(factory, "_RETRY_BASE_SECONDS", 0.0)
    monkeypatch.setattr(factory, "_RETRY_MAX_SECONDS", 0.0)
    # Retry-After is capped separately now; zero it too so a loop test with a
    # Retry-After header doesn't actually sleep.
    monkeypatch.setattr(factory, "_RETRY_AFTER_MAX_SECONDS", 0.0)

    async def _noop_slot(**_kwargs: object) -> None:
        return None

    monkeypatch.setattr(factory, "acquire_model_call_slot", _noop_slot)


def _http_response(status: int, *, headers: dict[str, str] | None = None) -> httpx.Response:
    req = httpx.Request("POST", "https://api.example.invalid/v1/chat/completions")
    return httpx.Response(status, headers=headers or {}, request=req)


def _rate_limit(headers: dict[str, str] | None = None) -> Exception:
    import openai

    return openai.RateLimitError(
        "rate limited", response=_http_response(429, headers=headers), body=None
    )


def _server_error() -> Exception:
    import openai

    return openai.APIStatusError("overloaded", response=_http_response(500), body=None)


def _bad_request() -> Exception:
    import openai

    return openai.BadRequestError("bad input", response=_http_response(400), body=None)


class _ScriptedInner:
    """Fake ChatClient inner: raises the queued errors in order, then returns
    the given response. Records how many times complete() was invoked."""

    profile_name = "chat"
    provider = "openai-compatible"
    model = "fake-model"

    def __init__(self, errors: list[Exception], result: ChatResponse | None = None) -> None:
        self._errors = list(errors)
        self._result = result
        self.calls = 0

    async def complete(self, request: ChatRequest) -> ChatResponse:
        self.calls += 1
        if self._errors:
            raise self._errors.pop(0)
        assert self._result is not None
        return self._result


def _ok_response() -> ChatResponse:
    return ChatResponse(
        text="final answer",
        tool_calls=[],
        stop_reason="end_turn",
        usage=TokenUsage(),
    )


@pytest.mark.asyncio
async def test_rate_limit_twice_then_success_is_retried() -> None:
    inner = _ScriptedInner([_rate_limit(), _rate_limit()], result=_ok_response())
    wrapped = _UsageRecordingChatClient(inner)

    resp = await wrapped.complete(_REQUEST)

    assert resp.text == "final answer"
    assert inner.calls == 3  # two failures + one success


@pytest.mark.asyncio
async def test_retry_false_does_a_single_attempt() -> None:
    """The settings connection probe passes retry=False so a rate-limited
    endpoint fails fast instead of retry-storming a 429 into a timeout."""
    import openai

    inner = _ScriptedInner([_rate_limit(), _rate_limit()], result=_ok_response())
    wrapped = _UsageRecordingChatClient(inner)

    with pytest.raises(openai.RateLimitError):
        await wrapped.complete(_REQUEST, retry=False)

    assert inner.calls == 1  # no retry — the first 429 surfaces immediately


@pytest.mark.asyncio
async def test_bad_request_is_not_retried() -> None:
    import openai

    inner = _ScriptedInner([_bad_request()], result=_ok_response())
    wrapped = _UsageRecordingChatClient(inner)

    with pytest.raises(openai.BadRequestError):
        await wrapped.complete(_REQUEST)

    assert inner.calls == 1  # 4xx propagates immediately, no retry


@pytest.mark.asyncio
async def test_persistent_server_error_exhausts_retries_and_raises() -> None:
    import openai

    # More errors than we could ever retry, so the wrapper must give up.
    inner = _ScriptedInner([_server_error() for _ in range(10)])
    wrapped = _UsageRecordingChatClient(inner)

    with pytest.raises(openai.APIStatusError):
        await wrapped.complete(_REQUEST)

    assert inner.calls == factory._MAX_RETRY_ATTEMPTS + 1


@pytest.mark.asyncio
async def test_anthropic_overloaded_status_is_retried() -> None:
    """529 (Anthropic "Overloaded") from the anthropic SDK is transient too."""
    import anthropic

    overloaded = anthropic.APIStatusError(
        "overloaded", response=_http_response(529), body=None
    )
    inner = _ScriptedInner([overloaded], result=_ok_response())
    wrapped = _UsageRecordingChatClient(inner)

    resp = await wrapped.complete(_REQUEST)

    assert resp.text == "final answer"
    assert inner.calls == 2


@pytest.mark.asyncio
async def test_connection_timeout_is_retried() -> None:
    import openai

    req = httpx.Request("POST", "https://api.example.invalid/v1/chat/completions")
    timeout = openai.APITimeoutError(request=req)
    inner = _ScriptedInner([timeout], result=_ok_response())
    wrapped = _UsageRecordingChatClient(inner)

    resp = await wrapped.complete(_REQUEST)

    assert resp.text == "final answer"
    assert inner.calls == 2


def test_retry_after_header_is_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    """A numeric Retry-After drives the delay, honored up to its own (larger)
    ceiling rather than the exponential-backoff cap."""
    monkeypatch.setattr(factory, "_RETRY_AFTER_MAX_SECONDS", 30.0)
    exc = _rate_limit(headers={"retry-after": "7"})
    assert factory._retry_after_seconds(exc) == 7.0
    # Retry-After (7s) is preferred over backoff and honored below the ceiling.
    assert factory._retry_delay(exc, attempt=0) == 7.0
    # An excessive Retry-After is capped at the Retry-After ceiling.
    big = _rate_limit(headers={"retry-after": "9999"})
    assert factory._retry_delay(big, attempt=0) == 30.0


def test_no_retry_after_header_returns_none() -> None:
    assert factory._retry_after_seconds(_server_error()) is None
    assert factory._retry_after_seconds(_rate_limit()) is None


def test_bad_request_is_not_classified_transient() -> None:
    assert factory._is_transient_error(_bad_request()) is False
    assert factory._is_transient_error(_server_error()) is True
    assert factory._is_transient_error(_rate_limit()) is True
