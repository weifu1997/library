"""Settings HTTP routes — runtime-mutable subset of `Settings`.

Four endpoints, all under `/v1/settings`:

  GET  /server      — read-only snapshot of resolved settings (no
                      secrets); the GUI uses this to render the
                      "server status" panel on the Settings page.
  GET  /llm         — per-profile resolution (chat / reflect / ingest /
                      vision / audio) with api_keys masked.
  PUT  /llm         — write a subset of LLM fields plus a few runtime
                      knobs to the overlay file. Returns the post-write
                      view so the GUI can refresh without a second GET.
  POST /llm/models  — list the models a profile's provider serves, so
                      the GUI can offer a model picker dropdown. Uses
                      the profile's resolved credentials with any
                      form-provided overrides layered on top.

Writes go through `services.config_overlay`. After a successful PUT we
clear the `get_settings()` lru_cache and the LLM client cache so the
next request sees the new values without a process restart.

Secrets are never echoed: GET masks api_keys to "sk-***" if present;
PUT accepts new api_keys but the response strips them again.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from library.config import (
    _REQUIRED_PROFILES,
    LLM_PROFILES_VISIBLE,
    Settings,
    get_settings,
    has_vision_profile,
    resolve_backup,
    resolve_profile,
)
from library.db.models import File
from library.db.session import get_session
from library.llm.factory import get_chat_client, reset_clients_cache
from library.llm.types import ChatMessage, ChatRequest, ImageBlock, TextBlock
from library.provider_clients import (
    get_anthropic_client, get_openai_compatible_client,
)
from library.repositories import files as files_repo
from library.semantic.index import semantic_index_status
from library.semantic.embeddings import get_embedding_client
from library.semantic.rerank import get_rerank_client, rerank_configured
from library.services.config_overlay import (
    OverlayValidationError, _VALID_PROVIDERS,
    read_overlay, validate_and_normalize, write_overlay,
)
from library.services import worker_lifecycle
from library.services.reprocess import reprocess_file
from library.services.webdav_sync import read_status as read_webdav_status

log = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

# Cap the auto-heal fan-out so a single settings PUT can't kick off an
# unbounded reprocess when a large library failed before a key was set.
_AUTOHEAL_MAX = 500

# Provider errors can be long and may embed the base_url; keep the surfaced
# message short and strip the api_key if it ever appears in the text.
_MAX_ERROR_CHARS = 400

# Wall-clock bound for a single LLM test probe so a stalling endpoint can't
# hang POST /settings/llm/test.
_PROBE_TIMEOUT_SECONDS = 15.0
# Some reasoning and OpenAI-compatible models reject a one-token output cap
# before producing any visible content. This is still tiny, but broadly valid.
_PROBE_MAX_TOKENS = 64
_VISION_PROBE_MAX_TOKENS = 256
_VISION_PROBE_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAIAAAAlC+aJAAAATElEQVR42u3PQQ0AAAgEoNP+"
    "nTWCbzdoQE1+6wgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIHBZ"
    "ShQF/CY4YrwAAAABJRU5ErkJggg=="
)


def _mask(secret: str | None) -> str | None:
    if not secret:
        return None
    if len(secret) <= 6:
        return "***"
    return f"{secret[:3]}***{secret[-2:]}"


def _backup_payload(
    s: Settings,
    profile: str,
    *,
    raw: bool,
) -> dict[str, Any] | None:
    """Resolved or raw backup-profile payload for the GET endpoint.

    ``raw=True`` mirrors the vision profile's opt-in rendering: only
    explicitly-set ``llm_<profile>_backup_*`` fields are shown, so an
    unconfigured backup reads as ``null`` in the UI even when a default
    backup exists. ``raw=False`` uses ``resolve_backup``, which inherits
    the default's backup per-field. The api_key is masked on the way out
    (and never echoed back in plaintext)."""
    if raw:
        model = getattr(s, f"llm_{profile}_backup_model")
        api_key = getattr(s, f"llm_{profile}_backup_api_key")
        if not model:
            return None
        return {
            "provider": getattr(s, f"llm_{profile}_backup_provider"),
            "model": model,
            "base_url": getattr(s, f"llm_{profile}_backup_base_url"),
            "api_key": _mask(api_key),
            "api_key_set": bool(api_key),
        }
    backup = resolve_backup(s, profile)
    if backup is None:
        return None
    return {
        "provider": backup.provider,
        "model": backup.model,
        "base_url": backup.base_url,
        "api_key": _mask(backup.api_key),
        "api_key_set": bool(backup.api_key),
    }


@router.get("/server")
def server_settings() -> dict[str, Any]:
    """Read-only snapshot. GUI renders this in a "Server status" card.

    No secrets, no DSNs, no S3 keys — just identifiers and toggles a
    user might want to verify. The shape is intentionally flat so the
    GUI can render it with a simple key/value list."""
    s = get_settings()
    return {
        "app_env": s.app_env,
        "library_home": s.library_home,
        "db_backend": s.db_backend,
        "postgres_pool_size": s.postgres_pool_size,
        "postgres_max_overflow": s.postgres_max_overflow,
        "postgres_pool_timeout_seconds": s.postgres_pool_timeout_seconds,
        "postgres_prepared_statement_cache_size": (
            s.postgres_prepared_statement_cache_size
        ),
        "runtime_schema_bootstrap_enabled": s.runtime_schema_bootstrap_enabled,
        "readiness_timeout_seconds": s.readiness_timeout_seconds,
        "storage_backend": s.storage_backend,
        "worker_enabled": s.worker_enabled,
        "worker_running": worker_lifecycle.is_running(),
        "worker_scheduler_enabled": s.worker_scheduler_enabled,
        "worker_batch_size": s.worker_batch_size,
        "worker_retry_base_seconds": s.worker_retry_base_seconds,
        "worker_retry_max_seconds": s.worker_retry_max_seconds,
        "bulk_reprocess_page_size": s.bulk_reprocess_page_size,
        "auto_lifecycle_enabled": s.auto_lifecycle_enabled,
        "maintenance_daily_token_budget": s.maintenance_daily_token_budget,
        "relation_background_vetting_enabled": s.relation_background_vetting_enabled,
        "audit_retention_days": s.audit_retention_days,
        "task_retention_days": s.task_retention_days,
        "task_outcome_retention_days": s.task_outcome_retention_days,
        "agent_event_retention_days": s.agent_event_retention_days,
        "prune_batch_size": s.prune_batch_size,
        "prune_max_batches": s.prune_max_batches,
        "relation_mining_entry_page_size": s.relation_mining_entry_page_size,
        "relation_mining_activity_limit": s.relation_mining_activity_limit,
        "relation_mining_eligible_tag_limit": s.relation_mining_eligible_tag_limit,
        "relation_mining_candidate_limit": s.relation_mining_candidate_limit,
        "library_document_limit": s.library_document_limit,
        "library_storage_bytes_limit": s.library_storage_bytes_limit,
        "ingest_backlog_limit": s.ingest_backlog_limit,
        "chat_concurrency_limit": s.chat_concurrency_limit,
        "default_on_conflict": s.default_on_conflict,
        "agent_plan_max_tokens": s.agent_plan_max_tokens,
        "agent_execute_max_tokens": s.agent_execute_max_tokens,
        "agent_execute_max_turns": s.agent_execute_max_turns,
        "agent_max_parallel_tool_calls": s.agent_max_parallel_tool_calls,
        "agent_final_answer_continue_turns": s.agent_final_answer_continue_turns,
        "agent_final_answer_max_chars": s.agent_final_answer_max_chars,
        "agent_turn_timeout_seconds": s.agent_turn_timeout_seconds,
        "agent_cache_slo_min_hit_ratio": s.agent_cache_slo_min_hit_ratio,
        "agent_cache_slo_min_eligible_requests": (
            s.agent_cache_slo_min_eligible_requests
        ),
        "conversation_compaction_enabled": s.conversation_compaction_enabled,
        "conversation_compaction_reserve_tokens": (
            s.conversation_compaction_reserve_tokens
        ),
        "compression_enabled": s.compression_enabled,
        "compression_min_chars": s.compression_min_chars,
        "compression_target_chars": s.compression_target_chars,
        "compression_context_chars": s.compression_context_chars,
        "compression_max_ratio": s.compression_max_ratio,
        "llm_ingest_max_tokens": s.llm_ingest_max_tokens,
        "llm_ingest_concurrency": s.llm_ingest_concurrency,
        "llm_default_tps": s.llm_default_tps,
        "llm_chat_tps": s.llm_chat_tps,
        "llm_reflect_tps": s.llm_reflect_tps,
        "llm_ingest_tps": s.llm_ingest_tps,
        "llm_vision_tps": s.llm_vision_tps,
        "llm_vision_supports_vision": s.llm_vision_supports_vision,
        "embedding_provider": s.embedding_provider,
        "embedding_api_key_set": bool(s.embedding_api_key),
        "embedding_base_url": s.embedding_base_url,
        "embedding_model": s.embedding_model,
        "embedding_dimensions": s.embedding_dimensions,
        "embedding_tps": s.embedding_tps,
        "embedding_batch_size": s.embedding_batch_size,
        "semantic_index_backend": s.semantic_index_backend,
        "semantic_recall_enabled": s.semantic_recall_enabled,
        "semantic_recall_limit": s.semantic_recall_limit,
        "semantic_rebuild_page_size": s.semantic_rebuild_page_size,
        "section_backfill_min_score": s.section_backfill_min_score,
        "section_embedding_max_sections": s.section_embedding_max_sections,
        "semantic_recall_configured": bool(
            s.semantic_recall_enabled and s.embedding_api_key
        ),
        "semantic_index": semantic_index_status(),
        "rerank_enabled": s.rerank_enabled,
        "rerank_api_key_set": bool(s.rerank_api_key),
        "rerank_base_url": s.rerank_base_url,
        "rerank_model": s.rerank_model,
        "rerank_tps": s.rerank_tps,
        "rerank_batch_size": s.rerank_batch_size,
        "rerank_top_n": s.rerank_top_n,
        "rerank_max_doc_chars": s.rerank_max_doc_chars,
        "rerank_concurrency": s.rerank_concurrency,
        "rerank_configured": bool(s.rerank_enabled and s.rerank_api_key),
        "evidence_selection": s.evidence_selection,
        "vision_profile_configured": has_vision_profile(s),
        "document_vision_enabled": s.document_vision_enabled,
        "document_vision_max_images": s.document_vision_max_images,
        "document_vision_question_max_images": s.document_vision_question_max_images,
        "document_vision_min_image_bytes": s.document_vision_min_image_bytes,
        "document_vision_min_image_dimension": s.document_vision_min_image_dimension,
        "document_vision_min_image_area": s.document_vision_min_image_area,
        "webdav": read_webdav_status(s),
    }


@router.get("/llm")
def llm_settings() -> dict[str, Any]:
    """Per-profile resolution + the raw overlay so the GUI can show
    which fields are explicitly overridden vs inherited from defaults.

    api_keys are masked on the way out. The overlay returns the raw
    field dict (also masked) so the editor can prefill only the
    explicitly-set fields rather than every inherited value."""
    s = get_settings()
    profiles: dict[str, dict[str, Any]] = {}
    for p in LLM_PROFILES_VISIBLE:
        resolved = resolve_profile(s, p)
        capabilities = {
            "dialect": resolved.capabilities.dialect,
            "context_window": resolved.capabilities.context_window,
            "tokenizer": resolved.capabilities.tokenizer,
            "supports_vision": resolved.capabilities.supports_vision,
            "supports_tools": resolved.capabilities.supports_tools,
            "supports_temperature": resolved.capabilities.supports_temperature,
            "token_limit_param": resolved.capabilities.token_limit_param,
        }
        if p == "vision":
            # Opt-in profile: don't show the inherited default (the
            # default model is usually text-only and can't actually
            # serve vision). Reflect only what's explicitly set so an
            # unconfigured profile reads as blank in the UI.
            api_key = getattr(s, f"llm_{p}_api_key")
            profiles[p] = {
                "provider": getattr(s, f"llm_{p}_provider"),
                "api_key": _mask(api_key),
                "api_key_set": bool(api_key),
                "base_url": getattr(s, f"llm_{p}_base_url"),
                "model": getattr(s, f"llm_{p}_model"),
                "tps": getattr(s, f"llm_{p}_tps"),
                "capabilities": capabilities,
                "backup": _backup_payload(s, p, raw=True),
            }
            continue
        prof = resolved
        profiles[p] = {
            "provider": prof.provider,
            "api_key": _mask(prof.api_key),
            "api_key_set": bool(prof.api_key),
            "base_url": prof.base_url,
            "model": prof.model,
            "tps": prof.tps,
            "capabilities": capabilities,
            "backup": _backup_payload(s, p, raw=False),
        }

    overlay = read_overlay(s.library_home)
    masked_overlay: dict[str, Any] = {}
    for k, v in overlay.items():
        if (k.endswith("_api_key") or k.endswith("_password")) and isinstance(v, str):
            masked_overlay[k] = _mask(v)
        else:
            masked_overlay[k] = v

    return {
        "profiles": profiles,
        "overlay": masked_overlay,
        "defaults": {
            "provider": s.llm_default_provider,
            "model": s.llm_default_model,
            "base_url": s.llm_default_base_url,
            "api_key": _mask(s.llm_default_api_key),
            "api_key_set": bool(s.llm_default_api_key),
            "tps": s.llm_default_tps,
            "backup": _backup_payload(s, "default", raw=False),
            "capabilities": {
                "dialect": s.llm_default_dialect or (
                    "anthropic" if s.llm_default_provider == "anthropic" else
                    "openai" if s.llm_default_provider == "openai" else
                    "openai-compatible"
                ),
                "context_window": s.llm_default_context_window,
                "tokenizer": s.llm_default_tokenizer,
                "supports_vision": s.llm_default_supports_vision,
                "supports_tools": s.llm_default_supports_tools,
                "supports_temperature": s.llm_default_supports_temperature,
                "token_limit_param": s.llm_default_token_limit_param,
            },
        },
    }


def _safe_error(exc: Exception, api_key: str | None) -> str:
    """Provider message trimmed for the client — redact the api_key if it
    leaked into the text, cap the length. Full detail is logged server-side."""
    msg = str(exc).strip() or exc.__class__.__name__
    if api_key and api_key in msg:
        msg = msg.replace(api_key, "***")
    if len(msg) > _MAX_ERROR_CHARS:
        msg = msg[:_MAX_ERROR_CHARS] + "…"
    return msg


def _probe_duration_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


async def _list_llm_models(
    provider: str,
    base_url: str | None,
    api_key: str,
) -> dict[str, Any]:
    """List the models a provider serves via its model-listing endpoint.

    Returns ``{ok: True, models: [{id, display_name}], provider, base_url}``
    on success or ``{ok: False, error}`` with the (sanitized) provider message
    on failure — same verdict shape as ``_probe_llm_profile``. Anthropic's
    list endpoint defaults to 20 results, so pass ``limit=1000`` to get the
    full catalog; OpenAI returns everything in one page. The api_key is used
    only for the outbound call and is never echoed in the response."""
    started = time.perf_counter()
    try:
        async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):
            if provider == "anthropic":
                client = get_anthropic_client(
                    api_key=api_key, base_url=base_url or None,
                )
                page = await client.models.list(limit=1000)
                models = sorted(
                    (
                        {"id": m.id, "display_name": m.display_name}
                        for m in page.data
                    ),
                    key=lambda m: m["id"],
                )
            else:
                client = get_openai_compatible_client(
                    api_key=api_key, base_url=base_url or None,
                )
                page = await client.models.list()
                models = sorted(
                    ({"id": m.id, "display_name": None} for m in page.data),
                    key=lambda m: m["id"],
                )
        return {
            "ok": True,
            "models": models,
            "provider": provider,
            "base_url": base_url,
            "duration_ms": _probe_duration_ms(started),
        }
    except TimeoutError:
        log.warning("llm models fetch timed out for provider %s", provider)
        return {
            "ok": False,
            "error": f"timed out after {_PROBE_TIMEOUT_SECONDS:g}s",
            "duration_ms": _probe_duration_ms(started),
        }
    except Exception as exc:  # noqa: BLE001 - returned as a local admin diagnostic
        log.warning("llm models fetch failed for provider %s: %s", provider, exc)
        return {
            "ok": False,
            "error": _safe_error(exc, api_key),
            "duration_ms": _probe_duration_ms(started),
        }


async def _probe_llm_profile(profile: str) -> dict[str, Any]:
    """One tiny chat call to confirm a profile's key/base_url/model
    actually work. Returns {ok: True, model, provider} on success or
    {ok: False, error} with the (sanitized) provider message on failure."""
    import anthropic
    import openai

    api_key = resolve_profile(get_settings(), profile).api_key
    started = time.perf_counter()
    try:
        client = get_chat_client(profile)
        # retry=False so a rate-limited probe fails fast instead of the retry
        # wrapper waiting out a 429/Retry-After past the timeout below. Bound
        # the whole thing so a base_url that accepts TCP but never responds
        # can't hang the endpoint.
        async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):
            content: str | list[TextBlock | ImageBlock]
            if profile == "vision":
                content = [
                    TextBlock(text="Name the main color in this image."),
                    ImageBlock(media_type="image/png", data_b64=_VISION_PROBE_PNG_B64),
                ]
            else:
                content = "ping"
            await client.complete(
                ChatRequest(
                    system=None,
                    messages=[ChatMessage(role="user", content=content)],
                    max_tokens=(
                        _VISION_PROBE_MAX_TOKENS
                        if profile == "vision"
                        else _PROBE_MAX_TOKENS
                    ),
                    temperature=0.0,
                ),
                retry=False,
            )
        return {
            "ok": True,
            "model": client.model,
            "provider": client.provider,
            "duration_ms": _probe_duration_ms(started),
            "mode": "image" if profile == "vision" else "text",
        }
    except (openai.RateLimitError, anthropic.RateLimitError):
        # A 429 means the endpoint is reachable and the key is valid — the
        # config works, the account is just being throttled (common when the
        # test probes several same-account profiles back to back).
        log.info("llm test rate-limited for profile %s (treated as reachable)", profile)
        return {
            "ok": True, "model": client.model, "provider": client.provider,
            "note": "rate limited (reachable)",
            "duration_ms": _probe_duration_ms(started),
        }
    except TimeoutError:
        log.warning("llm test timed out for profile %s", profile)
        return {
            "ok": False,
            "error": f"timed out after {_PROBE_TIMEOUT_SECONDS:g}s",
            "duration_ms": _probe_duration_ms(started),
        }
    except Exception as exc:  # noqa: BLE001 - reported per-profile, logged here
        log.warning("llm test failed for profile %s: %s", profile, exc)
        return {
            "ok": False,
            "error": _safe_error(exc, api_key),
            "duration_ms": _probe_duration_ms(started),
        }


async def _probe_embedding() -> dict[str, Any]:
    s = get_settings()
    if not (s.semantic_recall_enabled and s.embedding_api_key):
        return {"ok": None, "configured": False}
    started = time.perf_counter()
    try:
        async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):
            result = await get_embedding_client(s).embed(["ping"], text_type="query")
        vector = result.vectors[0] if result.vectors else []
        if len(vector) != s.embedding_dimensions:
            raise RuntimeError(
                f"embedding dimension mismatch: expected {s.embedding_dimensions}, "
                f"received {len(vector)}"
            )
        return {
            "ok": True,
            "model": s.embedding_model,
            "dimensions": len(vector),
            "duration_ms": _probe_duration_ms(started),
        }
    except TimeoutError:
        return {
            "ok": False,
            "error": f"timed out after {_PROBE_TIMEOUT_SECONDS:g}s",
            "duration_ms": _probe_duration_ms(started),
        }
    except Exception as exc:  # noqa: BLE001 - returned as a local admin diagnostic
        log.warning("embedding connection test failed: %s", exc)
        return {
            "ok": False,
            "error": _safe_error(exc, s.embedding_api_key),
            "duration_ms": _probe_duration_ms(started),
        }


async def _probe_rerank() -> dict[str, Any]:
    s = get_settings()
    if not rerank_configured(s):
        return {"ok": None, "configured": False}
    started = time.perf_counter()
    try:
        async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):
            hits = await get_rerank_client(s).rerank(
                "knowledge search",
                ["knowledge search"],
                top_n=1,
            )
        if not hits or hits[0].index != 0:
            raise RuntimeError("rerank response did not contain the probe document")
        return {
            "ok": True,
            "model": s.rerank_model,
            "duration_ms": _probe_duration_ms(started),
        }
    except TimeoutError:
        return {
            "ok": False,
            "error": f"timed out after {_PROBE_TIMEOUT_SECONDS:g}s",
            "duration_ms": _probe_duration_ms(started),
        }
    except Exception as exc:  # noqa: BLE001 - returned as a local admin diagnostic
        log.warning("rerank connection test failed: %s", exc)
        return {
            "ok": False,
            "error": _safe_error(exc, s.rerank_api_key),
            "duration_ms": _probe_duration_ms(started),
        }


@router.post("/llm/test")
async def test_llm_profiles(
    profile: str | None = None,
) -> dict[str, Any]:
    """Probe each resolved LLM profile with a tiny chat call so a mistyped
    key / base-URL / model is caught here at config time instead of surfacing
    later as a failed ingest or chat turn. Mirrors the WebDAV `POST /test`
    onboarding pattern.

    Returns ``{"profiles": {name: {...}}}`` where each entry is either
    ``{ok: True, model, provider}``, ``{ok: False, error}``, or — for an
    unconfigured optional profile — ``{ok: None, configured: False}``. The
    call always returns 200; per-profile status carries the verdict.

    Pass ``?profile=default`` to probe ONLY the default profile (the one the
    Settings quick-config form edits) and skip embedding/rerank. The default
    profile is not a member of ``LLM_PROFILES``; ``resolve_profile`` accepts
    "default" so its verdict can reuse ``_probe_llm_profile`` directly.
    """
    s = get_settings()
    started = time.perf_counter()
    if profile == "default":
        default_prof = resolve_profile(s, "default")
        if not default_prof.api_key or not default_prof.model:
            return {
                "profiles": {"default": {"ok": None, "configured": False}},
                "duration_ms": _probe_duration_ms(started),
            }
        return {
            "profiles": {"default": await _probe_llm_profile("default")},
            "duration_ms": _probe_duration_ms(started),
        }
    results: dict[str, dict[str, Any]] = {}
    # De-dupe the network calls: chat/reflect/ingest usually resolve to the
    # same endpoint (all inheriting LLM_DEFAULT_*), so probe each distinct
    # (provider, base_url, model, key) once and reuse the verdict.
    seen: dict[tuple[Any, ...], dict[str, Any]] = {}
    for p in LLM_PROFILES_VISIBLE:
        if p == "vision" and not has_vision_profile(s):
            results[p] = {"ok": None, "configured": False}
            continue
        prof = resolve_profile(s, p)
        sig = (
            prof.provider,
            prof.base_url,
            prof.model,
            prof.api_key,
            "image" if p == "vision" else "text",
        )
        verdict = seen.get(sig)
        if verdict is None:
            verdict = await _probe_llm_profile(p)
            seen[sig] = verdict
        results[p] = verdict
    embedding, rerank = await asyncio.gather(
        _probe_embedding(),
        _probe_rerank(),
    )
    return {
        "profiles": results,
        "embedding": embedding,
        "rerank": rerank,
        "duration_ms": _probe_duration_ms(started),
    }


class LlmModelsRequest(BaseModel):
    """Which profile's credentials to list models for.

    ``provider`` / ``base_url`` / ``api_key`` are optional overrides from the
    settings form: when set (non-empty) they replace the resolved value, so an
    unsaved edit can be tested before it is persisted; empty fields fall back
    to the resolved profile. ``backup=True`` resolves the profile's backup
    target instead of the primary, so the backup model field gets the same
    picker."""

    profile: str = "default"
    backup: bool = False
    provider: str | None = None
    base_url: str | None = None
    api_key: str | None = None


@router.post("/llm/models")
async def list_llm_models(
    body: LlmModelsRequest | None = None,
) -> dict[str, Any]:
    """List the models a profile's provider serves.

    Lets the Settings GUI offer a model picker dropdown instead of requiring a
    hand-typed model name. Uses the resolved profile credentials with any
    form-provided overrides layered on top; always returns 200 with a per-call
    ``ok`` verdict (mirrors ``POST /llm/test``)."""
    payload = body or LlmModelsRequest()
    s = get_settings()
    if payload.profile != "default" and payload.profile not in LLM_PROFILES_VISIBLE:
        raise HTTPException(
            status_code=422, detail=f"unknown LLM profile: {payload.profile!r}",
        )
    if payload.backup:
        base = resolve_backup(s, payload.profile)
    else:
        base = resolve_profile(s, payload.profile)

    # A masked placeholder ("sk-***CA") is the stored key rendered for
    # display, never a real credential. Treat it as absent so we fall back
    # to the resolved key instead of calling the provider with the mask.
    raw_override = (payload.api_key or "").strip()
    if "***" in raw_override:
        raw_override = ""
    has_live = bool(
        (payload.provider or "").strip()
        or (payload.base_url or "").strip()
        or raw_override
    )

    if base is None and not has_live:
        # No persisted backup target and no live form override to list
        # against — there is nothing to fetch.
        return {"ok": False, "error": "backup model not configured", "duration_ms": 0.0}

    eff_provider = (payload.provider or "").strip() or (base.provider if base else "")
    eff_base_url = (payload.base_url or "").strip() or ((base.base_url or "") if base else "")
    eff_api_key = raw_override or ((base.api_key or "") if base else "")
    if eff_provider not in _VALID_PROVIDERS:
        raise HTTPException(
            status_code=422, detail=f"unsupported provider: {eff_provider!r}",
        )
    return await _list_llm_models(eff_provider, eff_base_url, eff_api_key)


def _has_required_profiles(s: Settings) -> bool:
    """Whether every required profile now resolves to a usable key + model.
    Gates the post-PUT auto-heal so failed ingests are retried only once the
    config can actually succeed."""
    for p in _REQUIRED_PROFILES:
        prof = resolve_profile(s, p)
        if not prof.api_key or not prof.model:
            return False
    return True


async def _reprocess_failed_ingests(session: AsyncSession) -> int:
    """Re-enqueue files whose ingest failed (typically before a valid key was
    configured). Bounded by _AUTOHEAL_MAX; caller's request owns the txn."""
    file_ids = (
        await files_repo.list_live_ids(session, ingest_status="failed")
    )[:_AUTOHEAL_MAX]
    healed = 0
    for fid in file_ids:
        file_row = await session.get(File, fid)
        if file_row is None or file_row.deleted_at is not None:
            continue
        await reprocess_file(session, file_row, scheduled_by="llm_configured")
        healed += 1
    if healed:
        await session.commit()
    return healed


class LlmPatchBody(BaseModel):
    """Subset of overlay fields a PUT may touch.

    Sent as a flat dict because the GUI builds it from per-profile
    forms; we accept any subset of allowed fields and merge them on
    top of the existing overlay (so partial edits don't wipe other
    profiles)."""
    patch: dict[str, Any] = Field(default_factory=dict)
    # When true, replace the whole overlay with `patch` instead of
    # merging. Useful for a "reset profile" button that needs to clear
    # specific overrides — pass them as None or omit.
    replace: bool = False


@router.put("/llm")
async def update_llm_settings(
    body: LlmPatchBody,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    s = get_settings()
    # Snapshot validity BEFORE the write so we only auto-heal on the edge where
    # required profiles first become valid — not on every unrelated PUT.
    was_valid = _has_required_profiles(s)
    try:
        clean = validate_and_normalize(body.patch)
    except OverlayValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if body.replace:
        merged = clean
    else:
        merged = read_overlay(s.library_home)
        # Drop keys explicitly set to None — that means "clear this
        # override" so the field falls back to .env / default.
        for k, v in clean.items():
            if v is None:
                merged.pop(k, None)
            else:
                merged[k] = v

    write_overlay(s.library_home, merged)

    # Invalidate caches so the next call sees the new values.
    get_settings.cache_clear()  # type: ignore[attr-defined]
    reset_clients_cache()

    payload = llm_settings()

    # A worker_enabled patch is both a persisted preference and a live
    # request to start/stop the in-process runner right now. The write is
    # already durable; a lifecycle failure must not roll it back — surface
    # it via worker_error so the GUI can tell "saved but not applied".
    if "worker_enabled" in clean:
        patch_value = clean["worker_enabled"]
        # A None patch means "clear this override" — the key is dropped from
        # the overlay above, so the EFFECTIVE value is whatever .env / the
        # default says. bool(None) is False, so deriving the desired state
        # from the patch directly would wrongly STOP a running worker when
        # the effective value after clearing is still true. Re-read through
        # get_settings() (already cache-cleared) for the authoritative value.
        desired = (
            get_settings().worker_enabled
            if patch_value is None
            else bool(patch_value)
        )
        try:
            if desired and not worker_lifecycle.is_running():
                await worker_lifecycle.start()
            elif not desired and worker_lifecycle.is_running():
                await worker_lifecycle.stop()
        except Exception:
            log.exception("worker enable/disable after settings PUT failed")
            payload.setdefault("worker_error", "start/stop failed; see server log")

    # Auto-heal: if this PUT is the edge where required profiles first become
    # valid, retry ingests that failed before a key existed — the top-of-funnel
    # case where a user would otherwise conclude "nothing happens". Best-effort:
    # a reprocess error must never fail the settings write itself.
    if not was_valid and _has_required_profiles(get_settings()):
        try:
            healed = await _reprocess_failed_ingests(session)
            if healed:
                payload["reprocessed_failed"] = healed
        except Exception:
            log.exception("auto-heal reprocess after llm settings PUT failed")

    return payload
