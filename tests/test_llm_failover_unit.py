"""Unit tests for the primary + backup (failover) chat client.

Two layers are exercised:
  - ``config.resolve_backup``: the per-profile backup resolution (field
    inheritance, provider defaulting, dialect / token_limit_param rules).
  - ``factory._FailoverChatClient`` / ``_build_chat``: the failover wrapper —
    a primary that exhausts its transient-retry budget switches to the backup
    once; permanent errors, ``retry=False``, and missing backups never switch.

Exception construction mirrors ``test_llm_retry_unit.py`` (httpx-backed SDK
errors); backoff and rate pacing are zeroed so the tests are fast and
hermetic."""
from __future__ import annotations

import httpx
import pytest

from library.config import LlmProfile, Settings, resolve_backup
from library.llm import factory
from library.llm.factory import (
    _FailoverChatClient,
    _UsageRecordingChatClient,
    _build_chat,
)
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
    monkeypatch.setattr(factory, "_RETRY_AFTER_MAX_SECONDS", 0.0)

    async def _noop_slot(**_kwargs: object) -> None:
        return None

    monkeypatch.setattr(factory, "acquire_model_call_slot", _noop_slot)


# --- resolve_backup ---------------------------------------------------------


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = dict(
        _env_file=None,
        llm_default_provider="openai-compatible",
        llm_default_api_key="default-key",
        llm_default_base_url="https://default.example",
        llm_default_model="default-model",
        llm_default_dialect="deepseek",
    )
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_backup_none_when_unconfigured() -> None:
    s = _settings()
    assert resolve_backup(s, "chat") is None
    assert resolve_backup(s, "default") is None


def test_backup_none_when_model_blank() -> None:
    s = _settings(llm_default_backup_model="")
    assert resolve_backup(s, "chat") is None


def test_backup_default_profile_resolves_fields() -> None:
    s = _settings(
        llm_default_backup_provider="openai-compatible",
        llm_default_backup_api_key="backup-key",
        llm_default_backup_base_url="https://backup.example",
        llm_default_backup_model="backup-model",
    )
    b = resolve_backup(s, "default")
    assert b is not None
    assert b.name == "default.backup"
    assert b.provider == "openai-compatible"
    assert b.api_key == "backup-key"
    assert b.base_url == "https://backup.example"
    assert b.model == "backup-model"
    # Same provider family as the primary → the primary's dialect is kept.
    assert b.capabilities.dialect == "deepseek"


def test_backup_inherits_default_for_profile() -> None:
    s = _settings(llm_default_backup_model="backup-model")
    b = resolve_backup(s, "chat")
    assert b is not None
    assert b.name == "chat.backup"
    assert b.model == "backup-model"
    assert b.provider == "openai-compatible"  # defaulted, not set explicitly


def test_backup_profile_override_wins() -> None:
    s = _settings(
        llm_default_backup_model="default-backup",
        llm_chat_backup_provider="anthropic",
        llm_chat_backup_api_key="chat-backup-key",
        llm_chat_backup_model="chat-backup",
    )
    b = resolve_backup(s, "chat")
    assert b is not None
    assert b.model == "chat-backup"
    assert b.provider == "anthropic"
    assert b.api_key == "chat-backup-key"


def test_anthropic_backup_re_derives_dialect_and_token_param() -> None:
    s = _settings(
        llm_default_backup_model="backup-model",
        llm_default_backup_provider="anthropic",
    )
    b = resolve_backup(s, "chat")
    assert b is not None
    assert b.capabilities.dialect == "anthropic"  # family differs → re-derive
    assert b.capabilities.token_limit_param == "max_tokens"


def test_non_anthropic_backup_keeps_primary_token_param() -> None:
    s = _settings(
        llm_default_provider="openai",
        llm_default_token_limit_param="max_completion_tokens",
        llm_default_backup_model="backup-model",
        llm_default_backup_provider="openai-compatible",
    )
    b = resolve_backup(s, "chat")
    assert b is not None
    assert b.capabilities.dialect == "openai-compatible"  # family differs → re-derive
    assert b.capabilities.token_limit_param == "max_completion_tokens"


# --- _FailoverChatClient -----------------------------------------------------


def _http_response(status: int) -> httpx.Response:
    req = httpx.Request("POST", "https://api.example.invalid/v1/chat/completions")
    return httpx.Response(status, request=req)


def _server_error() -> Exception:
    import openai

    return openai.APIStatusError("overloaded", response=_http_response(500), body=None)


def _rate_limit() -> Exception:
    import openai

    return openai.RateLimitError("rate limited", response=_http_response(429), body=None)


def _bad_request() -> Exception:
    import openai

    return openai.BadRequestError("bad input", response=_http_response(400), body=None)


class _ScriptedInner:
    """Fake ChatClient inner: raises the queued errors in order, then returns
    the given response. Records how many times complete() was invoked."""

    profile_name = "chat"
    provider = "openai-compatible"

    def __init__(
        self,
        errors: list[Exception],
        result: ChatResponse | None = None,
        *,
        model: str = "fake-model",
    ) -> None:
        self._errors = list(errors)
        self._result = result
        self.calls = 0
        self.model = model

    async def complete(self, request: ChatRequest) -> ChatResponse:
        self.calls += 1
        if self._errors:
            raise self._errors.pop(0)
        assert self._result is not None
        return self._result


def _ok_response(text: str = "final answer") -> ChatResponse:
    return ChatResponse(
        text=text,
        tool_calls=[],
        stop_reason="end_turn",
        usage=TokenUsage(),
    )


_PRIMARY = LlmProfile(
    name="chat",
    provider="openai-compatible",
    api_key="primary-key",
    base_url="https://primary.example",
    model="primary-model",
)


def _wrapped(
    inner: _ScriptedInner, *, profile: LlmProfile | None = None
) -> _UsageRecordingChatClient:
    return _UsageRecordingChatClient(inner, profile=profile)


@pytest.mark.asyncio
async def test_transient_exhaustion_fails_over_to_backup() -> None:
    primary_inner = _ScriptedInner([_server_error() for _ in range(10)])
    backup_inner = _ScriptedInner([], result=_ok_response("backup answer"))
    client = _FailoverChatClient(
        _wrapped(primary_inner, profile=_PRIMARY),
        _wrapped(backup_inner, profile=_PRIMARY),
    )

    resp = await client.complete(_REQUEST)

    assert resp.text == "backup answer"
    # Primary burns its whole transient-retry budget; backup gets exactly one
    # attempt (retry=False) and succeeds.
    assert primary_inner.calls == factory._MAX_RETRY_ATTEMPTS + 1
    assert backup_inner.calls == 1


@pytest.mark.asyncio
async def test_rate_limit_fails_over_to_backup() -> None:
    primary_inner = _ScriptedInner([_rate_limit() for _ in range(10)])
    backup_inner = _ScriptedInner([], result=_ok_response("backup answer"))
    client = _FailoverChatClient(
        _wrapped(primary_inner, profile=_PRIMARY),
        _wrapped(backup_inner, profile=_PRIMARY),
    )

    resp = await client.complete(_REQUEST)

    assert resp.text == "backup answer"
    assert backup_inner.calls == 1


@pytest.mark.asyncio
async def test_permanent_4xx_does_not_fail_over() -> None:
    import openai

    primary_inner = _ScriptedInner([_bad_request()])
    backup_inner = _ScriptedInner([], result=_ok_response("backup answer"))
    client = _FailoverChatClient(
        _wrapped(primary_inner, profile=_PRIMARY),
        _wrapped(backup_inner, profile=_PRIMARY),
    )

    with pytest.raises(openai.BadRequestError):
        await client.complete(_REQUEST)

    assert primary_inner.calls == 1  # 4xx propagates immediately
    assert backup_inner.calls == 0  # never fails over


@pytest.mark.asyncio
async def test_retry_false_does_not_fail_over() -> None:
    import openai

    primary_inner = _ScriptedInner([_server_error(), _server_error()])
    backup_inner = _ScriptedInner([], result=_ok_response("backup answer"))
    client = _FailoverChatClient(
        _wrapped(primary_inner, profile=_PRIMARY),
        _wrapped(backup_inner, profile=_PRIMARY),
    )

    with pytest.raises(openai.APIStatusError):
        await client.complete(_REQUEST, retry=False)

    assert primary_inner.calls == 1  # single attempt
    assert backup_inner.calls == 0  # the probe must not touch the backup


@pytest.mark.asyncio
async def test_backup_failure_propagates() -> None:
    import openai

    primary_inner = _ScriptedInner([_server_error() for _ in range(10)])
    backup_inner = _ScriptedInner([_server_error()])
    client = _FailoverChatClient(
        _wrapped(primary_inner, profile=_PRIMARY),
        _wrapped(backup_inner, profile=_PRIMARY),
    )

    with pytest.raises(openai.APIStatusError):
        await client.complete(_REQUEST)

    assert primary_inner.calls == factory._MAX_RETRY_ATTEMPTS + 1
    assert backup_inner.calls == 1  # one attempt on the backup, then raise


@pytest.mark.asyncio
async def test_no_backup_is_pure_primary() -> None:
    import openai

    primary_inner = _ScriptedInner([_server_error() for _ in range(10)])
    client = _FailoverChatClient(_wrapped(primary_inner, profile=_PRIMARY), None)

    with pytest.raises(openai.APIStatusError):
        await client.complete(_REQUEST)

    assert primary_inner.calls == factory._MAX_RETRY_ATTEMPTS + 1


def test_protocol_attributes_delegate_to_primary() -> None:
    backup = LlmProfile(
        name="chat.backup",
        provider="anthropic",
        api_key="backup-key",
        base_url="https://backup.example",
        model="backup-model",
    )
    client = _FailoverChatClient(
        _wrapped(_ScriptedInner([], result=_ok_response(), model="primary-model"), profile=_PRIMARY),
        _wrapped(_ScriptedInner([], result=_ok_response(), model="backup-model"), profile=backup),
    )
    assert client.profile_name == "chat"
    assert client.provider == "openai-compatible"
    assert client.model == "primary-model"  # primary's identity, not the backup's
    assert client.capabilities is not None


# --- _build_chat -------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_chat_wraps_when_backup_present() -> None:
    backup = LlmProfile(
        name="chat.backup",
        provider="anthropic",
        api_key="backup-key",
        base_url="https://backup.example",
        model="backup-model",
    )
    client = _build_chat(_PRIMARY, backup=backup)
    assert isinstance(client, _FailoverChatClient)
    # Identity reports the primary's.
    assert client.provider == "openai-compatible"
    assert client.model == "primary-model"


@pytest.mark.asyncio
async def test_build_chat_broken_backup_disables_failover_only() -> None:
    """A backup profile that cannot be built (bad provider) must not break the
    primary client — failover just degrades to primary-only."""
    bad_backup = LlmProfile(
        name="chat.backup",
        provider="not-a-provider",
        api_key=None,
        base_url=None,
        model="backup-model",
    )
    client = _build_chat(_PRIMARY, backup=bad_backup)
    assert isinstance(client, _UsageRecordingChatClient)
    assert not isinstance(client, _FailoverChatClient)


@pytest.mark.asyncio
async def test_build_chat_no_backup_returns_primary_directly() -> None:
    client = _build_chat(_PRIMARY, backup=None)
    assert isinstance(client, _UsageRecordingChatClient)
