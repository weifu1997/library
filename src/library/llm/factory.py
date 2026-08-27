"""LLM client factories. One profile → one cached client (cheap to create,
but pinning lets adapters share connection pools across calls)."""
from __future__ import annotations

import asyncio
import logging
import random
from functools import lru_cache

import anthropic
import openai

from library.config import (
    LlmProfile,
    get_settings,
    has_audio_profile,
    has_vision_profile,
    resolve_backup,
    resolve_profile,
)
from library.llm.anthropic_adapter import AnthropicChatClient
from library.llm.base import AudioClient, ChatClient
from library.llm.model_controls import (
    should_disable_thinking_by_default,
    with_disabled_thinking,
)
from library.llm.openai_adapter import OpenAIAudioClient, OpenAIChatClient
from library.llm.types import ChatRequest, ChatResponse
from library.model_rate_limit import acquire_model_call_slot

log = logging.getLogger(__name__)


# --- transient-failure retry policy -----------------------------------------
# Number of RETRIES (in addition to the first attempt) for transient provider
# failures. Kept small so a genuinely-down provider still fails reasonably
# fast; the SDKs also retry a couple of times internally per attempt, so the
# effective attempt count is bounded and sane.
_MAX_RETRY_ATTEMPTS = 4
_RETRY_BASE_SECONDS = 1.0
_RETRY_MAX_SECONDS = 20.0
# A server-supplied Retry-After is provider backpressure — honor it up to a
# larger ceiling than the exponential-backoff cap (which only bounds our own
# guess), so a 429 asking for e.g. 45s isn't retried prematurely.
_RETRY_AFTER_MAX_SECONDS = 60.0
# HTTP statuses that are safe to retry. 429 is handled via RateLimitError;
# these are transient server-side failures / overload signals (529 = Anthropic
# "Overloaded"). 4xx other than 429 (e.g. a 400 BadRequestError) are NOT here.
_RETRYABLE_STATUS = frozenset({500, 502, 503, 504, 529})
# Exception types from either SDK. APITimeoutError subclasses APIConnectionError
# in both openai and anthropic, so the connection base covers timeouts too.
_CONNECTION_ERRORS: tuple[type[BaseException], ...] = (
    openai.APIConnectionError,
    anthropic.APIConnectionError,
)
_RATE_LIMIT_ERRORS: tuple[type[BaseException], ...] = (
    openai.RateLimitError,
    anthropic.RateLimitError,
)
_STATUS_ERRORS: tuple[type[BaseException], ...] = (
    openai.APIStatusError,
    anthropic.APIStatusError,
)


def _is_transient_error(exc: BaseException) -> bool:
    """True for provider failures worth retrying: rate limits, connection/
    timeout errors, and 5xx/overloaded statuses. BadRequestError and any other
    4xx (a 400/404/422 APIStatusError) are NOT transient and return False, so
    they propagate immediately without discarding the turn on the next try."""
    if isinstance(exc, _CONNECTION_ERRORS):
        return True
    if isinstance(exc, _RATE_LIMIT_ERRORS):
        return True
    if isinstance(exc, _STATUS_ERRORS):
        return getattr(exc, "status_code", None) in _RETRYABLE_STATUS
    return False


def _retry_after_seconds(exc: BaseException) -> float | None:
    """Numeric Retry-After (seconds) off the error's HTTP response, if present.
    Date-form Retry-After values are ignored (caller falls back to backoff)."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


def _retry_delay(exc: BaseException, attempt: int) -> float:
    """Seconds to wait before the next attempt: a server-supplied Retry-After
    when present, else exponential backoff with jitter — both capped."""
    retry_after = _retry_after_seconds(exc)
    if retry_after is not None:
        # Honor server backpressure up to a larger ceiling than our own guess.
        return min(retry_after, _RETRY_AFTER_MAX_SECONDS)
    delay = _RETRY_BASE_SECONDS * (2**attempt) + random.uniform(0, _RETRY_BASE_SECONDS)
    return min(delay, _RETRY_MAX_SECONDS)


class _UsageRecordingChatClient:
    """Transparent wrapper that drops every response.usage into the task-
    bound UsageCounters (if one is bound). When nothing is bound — e.g.
    chat-page calls running outside the TaskRunner — record_chat_use is a
    no-op and the wrapper is invisible.

    Kept as a thin proxy so `isinstance(c, ChatClient)` still holds and
    test code that monkeypatches `complete` keeps working."""

    def __init__(
        self,
        inner: ChatClient,
        *,
        profile: LlmProfile | None = None,
        disable_thinking_by_default: bool = False,
    ) -> None:
        self._inner = inner
        self.profile_name = inner.profile_name
        self.provider = inner.provider
        self.model = inner.model
        self.capabilities = profile.capabilities if profile is not None else None
        self._base_url = profile.base_url if profile is not None else getattr(inner, "base_url", None)
        self._tps = profile.tps if profile is not None else 10
        self._disable_thinking_by_default = disable_thinking_by_default

    async def complete(self, request: ChatRequest, *, retry: bool = True) -> ChatResponse:
        if self._disable_thinking_by_default:
            request = with_disabled_thinking(request)
        # Import here to avoid a circular dep at module import time
        # (tasks.usage doesn't import llm, but tasks.runner does, and
        # tasks.runner imports through this factory).
        from library.tasks.usage import record_chat_use

        # Bounded retry-with-backoff around the single provider call every chat
        # completion flows through. Without this a transient rate-limit / 5xx /
        # overloaded window that outlives the SDK's quick internal retries would
        # propagate out of complete() and discard the whole agent turn (all
        # accumulated tool work). Each attempt re-paces via acquire_model_call_slot
        # and honors a server-supplied Retry-After. Non-transient errors
        # (BadRequestError / other 4xx / ValueError) propagate immediately.
        # retry=False does a single attempt — used by the settings connection
        # probe, which wants a fast yes/no and must NOT retry-storm a 429 into a
        # timeout (a rate-limit there actually proves the endpoint is reachable).
        max_attempts = _MAX_RETRY_ATTEMPTS if retry else 0
        last_exc: BaseException | None = None
        for attempt in range(max_attempts + 1):
            await acquire_model_call_slot(
                kind="chat",
                provider=self.provider,
                base_url=self._base_url,
                model=self.model,
                tps=self._tps,
            )
            try:
                resp = await self._inner.complete(request)
            except Exception as exc:
                if attempt >= max_attempts or not _is_transient_error(exc):
                    raise
                last_exc = exc
                delay = _retry_delay(exc, attempt)
                log.warning(
                    "transient provider error on profile %s (attempt %d/%d): %s; "
                    "retrying in %.2fs",
                    self.profile_name,
                    attempt + 1,
                    _MAX_RETRY_ATTEMPTS + 1,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
                continue
            record_chat_use(resp.usage)
            return resp
        # The loop only exits via return or raise; this keeps type-checkers
        # satisfied that a value is always produced.
        assert last_exc is not None
        raise last_exc


def _build_single(profile: LlmProfile) -> ChatClient:
    """Build one retry-wrapped adapter for a resolved profile (no failover)."""
    if profile.provider in ("openai", "openai-compatible"):
        inner: ChatClient = OpenAIChatClient(profile)
    elif profile.provider == "anthropic":
        inner = AnthropicChatClient(profile)
    else:
        raise ValueError(f"unknown provider for profile {profile.name}: {profile.provider}")
    return _UsageRecordingChatClient(
        inner,
        profile=profile,
        disable_thinking_by_default=should_disable_thinking_by_default(profile),
    )


class _FailoverChatClient:
    """Delegating wrapper that fails over to a backup client ONCE when the
    primary exhausts its transient-retry budget (rate limit / timeout / 5xx /
    overload). Non-transient errors and ``retry=False`` calls (the settings
    probe) never fail over.

    Protocol attributes (profile_name / provider / model / capabilities) are
    delegated to the primary so call sites keep reading the primary's
    identity — e.g. the agent runtime's vision-capability probe
    (agent/runtime.py) and the settings connection probe, which must keep
    reporting the primary model."""

    def __init__(self, primary: ChatClient, backup: ChatClient | None) -> None:
        self._primary = primary
        self._backup = backup
        self.profile_name = primary.profile_name
        self.provider = primary.provider
        self.model = primary.model
        self.capabilities = getattr(primary, "capabilities", None)

    async def complete(self, request: ChatRequest, *, retry: bool = True) -> ChatResponse:
        try:
            return await self._primary.complete(request, retry=retry)
        except Exception as exc:
            if not retry or self._backup is None or not _is_transient_error(exc):
                raise
            log.warning(
                "primary profile %s exhausted retries on a transient error (%s); "
                "failing over to backup %s",
                self.profile_name,
                exc,
                self._backup.model,
            )
            # One attempt on the backup — the primary already consumed the
            # retry budget, so don't double it.
            return await self._backup.complete(request, retry=False)


def _build_chat(profile: LlmProfile, backup: LlmProfile | None = None) -> ChatClient:
    """Build a chat client for the resolved profile, optionally wrapped for
    failover to a backup profile. A broken backup config (e.g. a provider
    typo) only disables failover — it never breaks the primary client."""
    primary = _build_single(profile)
    if backup is None:
        return primary
    try:
        backup_wrapped = _build_single(backup)
    except Exception:
        log.warning(
            "failed to build backup client for profile %s; failover disabled",
            profile.name,
            exc_info=True,
        )
        return primary
    return _FailoverChatClient(primary, backup_wrapped)


@lru_cache(maxsize=8)
def get_chat_client(profile: str = "ingest") -> ChatClient:
    """Get a chat client by profile name.

    Profile names:
      - "chat"    → online agent (plan-execute)
      - "reflect" → reflect_turn (strong model + long context)
      - "ingest"  → ingest_file pipelines AND offline batch tasks
                    (enrich_tags / restructure_catalogs / suggest_*)
      - "vision"  → image_pipeline VLM
      - "audio"   → NOT served here; use get_audio_client()
    """
    if profile == "audio":
        raise ValueError("use get_audio_client() for the audio profile")
    settings = get_settings()
    if profile == "vision" and not has_vision_profile(settings):
        # Don't silently fall back to LLM_DEFAULT_*: the default model
        # is usually text-only and the call would fail with a provider
        # 400 per request. Callers should gate on `has_vision_profile`
        # before reaching here.
        raise ValueError(
            "vision profile is not configured; set LLM_VISION_* "
            "(or guard the call with has_vision_profile())"
        )
    p = resolve_profile(settings, profile)
    backup = resolve_backup(settings, profile)
    return _build_chat(p, backup=backup)


@lru_cache(maxsize=2)
def get_audio_client() -> AudioClient:
    settings = get_settings()
    if not has_audio_profile(settings):
        # Same reasoning as vision: a default chat endpoint won't have
        # /audio/transcriptions, so falling back produces 404s. Force
        # the user to configure LLM_AUDIO_* explicitly.
        raise ValueError(
            "audio profile is not configured; set LLM_AUDIO_* "
            "(or guard the call with has_audio_profile())"
        )
    p = resolve_profile(settings, "audio")
    if p.provider not in ("openai", "openai-compatible"):
        raise ValueError(
            "audio profile requires an OpenAI-compatible provider "
            "(Anthropic does not offer audio transcription)"
        )
    return OpenAIAudioClient(p)


def reset_clients_cache() -> None:
    """Test helper: drop cached clients so a settings change takes effect."""
    get_chat_client.cache_clear()
    get_audio_client.cache_clear()
