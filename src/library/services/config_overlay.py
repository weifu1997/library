"""Persistent settings overlay — values written via the GUI / API.

`Settings()` loads from `.env` + process env once at startup. This module
adds a second, mutable layer on top: a JSON file at
`<LIBRARY_HOME>/config_overlay.json` whose keys override matching
fields on the resolved `Settings`. The overlay is merged in
`get_settings()` so every consumer sees the same merged view.

Why a separate file instead of editing `.env`:
  - `.env` is the user's secrets file; we don't want the API to rewrite
    it (lossy on comments, may be checked in).
  - The overlay only carries the small whitelist of fields that make
    sense to change at runtime — LLM profiles, retrieval providers,
    conflict policy, agent token budgets, worker concurrency, and
    bounded LLM ingest fan-out. Storage backend, db, and most worker
    cadence still need a restart and stay in `.env`.

Writes are atomic (tmp + rename). The file is created on first PUT.
After a successful write, callers must invalidate the
`get_settings()` lru_cache and any `lru_cache`d clients (factory).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

# Whitelist: only these field names may live in the overlay. Anything
# else gets dropped silently on read and rejected on write — keeps the
# blast radius small if the file is hand-edited or corrupted.
_ALLOWED_FIELDS: frozenset[str] = frozenset({
    "default_on_conflict",
    "agent_plan_max_tokens",
    "agent_execute_max_tokens",
    "agent_execute_max_turns",
    "agent_final_answer_continue_turns",
    "agent_final_answer_max_chars",
    "agent_turn_timeout_seconds",
    "agent_cache_slo_min_hit_ratio",
    "agent_cache_slo_min_eligible_requests",
    "conversation_compaction_enabled",
    "conversation_compaction_reserve_tokens",
    "compression_enabled",
    "compression_min_chars",
    "compression_target_chars",
    "compression_context_chars",
    "compression_max_ratio",
    "llm_ingest_max_tokens",
    "llm_ingest_concurrency",
    "worker_batch_size",
    "bulk_reprocess_page_size",
    "maintenance_daily_token_budget",
    "relation_background_vetting_enabled",
    # WebDAV knowledge-pack publishing
    "webdav_url",
    "webdav_username",
    "webdav_password",
    "webdav_remote_path",
    "webdav_auto_sync_enabled",
    "webdav_auto_sync_interval_minutes",
    # LLM defaults
    "llm_default_provider",
    "llm_default_api_key",
    "llm_default_base_url",
    "llm_default_model",
    "llm_default_tps",
    "llm_default_dialect",
    "llm_default_context_window",
    "llm_default_tokenizer",
    "llm_default_supports_vision",
    "llm_default_supports_tools",
    "llm_default_supports_temperature",
    "llm_default_token_limit_param",
    # Per-profile overrides
    "llm_chat_provider", "llm_chat_api_key", "llm_chat_base_url", "llm_chat_model",
    "llm_chat_tps", "llm_chat_dialect", "llm_chat_context_window",
    "llm_chat_tokenizer", "llm_chat_supports_vision", "llm_chat_supports_tools",
    "llm_chat_supports_temperature", "llm_chat_token_limit_param",
    "llm_reflect_provider", "llm_reflect_api_key", "llm_reflect_base_url", "llm_reflect_model",
    "llm_reflect_tps", "llm_reflect_dialect", "llm_reflect_context_window",
    "llm_reflect_tokenizer", "llm_reflect_supports_vision",
    "llm_reflect_supports_tools", "llm_reflect_supports_temperature",
    "llm_reflect_token_limit_param",
    "llm_ingest_provider", "llm_ingest_api_key", "llm_ingest_base_url", "llm_ingest_model",
    "llm_ingest_tps", "llm_ingest_dialect", "llm_ingest_context_window",
    "llm_ingest_tokenizer", "llm_ingest_supports_vision", "llm_ingest_supports_tools",
    "llm_ingest_supports_temperature", "llm_ingest_token_limit_param",
    "llm_vision_provider", "llm_vision_api_key", "llm_vision_base_url", "llm_vision_model",
    "llm_vision_tps", "llm_vision_dialect", "llm_vision_context_window",
    "llm_vision_tokenizer", "llm_vision_supports_vision", "llm_vision_supports_tools",
    "llm_vision_supports_temperature", "llm_vision_token_limit_param",
    # llm_audio_* fields are intentionally NOT in the allowlist: no
    # pipeline consumes the audio profile yet, so accepting writes
    # would just persist dead config that misleads the user when
    # nothing happens. Re-add when a transcription pipeline lands.
    # Optional semantic recall / rerank
    "embedding_provider",
    "embedding_api_key",
    "embedding_base_url",
    "embedding_model",
    "embedding_dimensions",
    "embedding_tps",
    "embedding_batch_size",
    "semantic_index_backend",
    "semantic_recall_enabled",
    "semantic_recall_limit",
    "semantic_rebuild_page_size",
    "section_backfill_min_score",
    "section_embedding_max_sections",
    "rerank_enabled",
    "rerank_api_key",
    "rerank_base_url",
    "rerank_model",
    "rerank_tps",
    "rerank_batch_size",
    "rerank_top_n",
    "rerank_max_doc_chars",
    "rerank_concurrency",
    "evidence_selection",
    # Embedded document image vision
    "document_vision_enabled",
    "document_vision_max_images",
    "document_vision_question_max_images",
    "document_vision_min_image_bytes",
    "document_vision_min_image_dimension",
    "document_vision_min_image_area",
})

_VALID_PROVIDERS: frozenset[str] = frozenset({"openai", "openai-compatible", "anthropic"})
_VALID_EMBEDDING_PROVIDERS: frozenset[str] = frozenset({"dashscope", "openai-compatible"})
_VALID_SEMANTIC_INDEX_BACKENDS: frozenset[str] = frozenset({"auto", "file", "sqlite-vec"})
_VALID_EVIDENCE_SELECTION: frozenset[str] = frozenset({"quota", "rerank"})
_VALID_TOKEN_LIMIT_PARAMS: frozenset[str] = frozenset({
    "max_tokens", "max_completion_tokens",
})
_VALID_CONFLICT: frozenset[str] = frozenset({"rename", "error", "skip"})


def overlay_path(home: str | os.PathLike[str]) -> Path:
    return Path(home) / "config_overlay.json"


def read_overlay(home: str | os.PathLike[str]) -> dict[str, Any]:
    """Return the on-disk overlay, filtered to the allowed fields.

    Missing file → empty dict. Malformed JSON → empty dict (we don't
    want a typo in the overlay to brick the whole app)."""
    p = overlay_path(home)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return _canonical_overlay(raw)


def _canonical_overlay(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if k not in _ALLOWED_FIELDS:
            continue
        try:
            clean = validate_and_normalize({k: v})
        except OverlayValidationError:
            continue
        # A null (or "") on disk means "no override" — never merge it as
        # None over the .env default.
        out.update({ck: cv for ck, cv in clean.items() if cv is not None})
    return out


def write_overlay(home: str | os.PathLike[str], values: dict[str, Any]) -> None:
    """Replace the overlay file with `values` (already validated).

    Atomic: write to a tmp file in the same directory, then `os.replace`
    so a half-written JSON never appears."""
    p = overlay_path(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=".config_overlay.", suffix=".json", dir=str(p.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(values, f, indent=2, ensure_ascii=False, sort_keys=True)
        try:
            os.replace(tmp_name, p)
        except PermissionError:
            # Some restricted Windows filesystems allow direct writes but
            # deny rename/replace. Keep normal deployments atomic, but
            # still let the settings UI persist in those sandboxes.
            p.write_text(Path(tmp_name).read_text(encoding="utf-8"), encoding="utf-8")
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


class OverlayValidationError(ValueError):
    """One or more fields in a PUT body failed validation."""


def validate_and_normalize(patch: dict[str, Any]) -> dict[str, Any]:
    """Reject unknown fields and bad enum values; coerce ints; turn
    blank strings into ``None`` (so a profile override truly clears).

    Returns the cleaned dict ready to merge into the existing overlay.
    """
    out: dict[str, Any] = {}
    bad: list[str] = []
    for k, v in patch.items():
        if k not in _ALLOWED_FIELDS:
            bad.append(f"{k}: unknown field")
            continue
        if v == "":
            v = None
        if v is None:
            # None means "clear this override" — pass it through untouched
            # so the route can drop the key. The coercions below would
            # otherwise 422 (int(None)/float(None)) or store an explicit
            # False (bool(None)) instead of falling back to .env.
            out[k] = None
            continue
        if k.endswith("_provider") and v is not None:
            valid = (
                _VALID_EMBEDDING_PROVIDERS
                if k == "embedding_provider"
                else _VALID_PROVIDERS
            )
            if v not in valid:
                bad.append(f"{k}: must be one of {sorted(valid)}")
                continue
        if k == "default_on_conflict":
            if v not in _VALID_CONFLICT:
                bad.append(f"{k}: must be one of {sorted(_VALID_CONFLICT)}")
                continue
        if k == "semantic_index_backend":
            if v not in _VALID_SEMANTIC_INDEX_BACKENDS:
                bad.append(
                    f"{k}: must be one of {sorted(_VALID_SEMANTIC_INDEX_BACKENDS)}"
                )
                continue
        if k == "evidence_selection":
            if v not in _VALID_EVIDENCE_SELECTION:
                bad.append(f"{k}: must be one of {sorted(_VALID_EVIDENCE_SELECTION)}")
                continue
        if k.endswith("_token_limit_param"):
            if v not in _VALID_TOKEN_LIMIT_PARAMS:
                bad.append(
                    f"{k}: must be one of {sorted(_VALID_TOKEN_LIMIT_PARAMS)}"
                )
                continue
        if k in (
            "agent_plan_max_tokens",
            "agent_execute_max_tokens",
            "agent_execute_max_turns",
            "agent_final_answer_continue_turns",
            "agent_final_answer_max_chars",
            "agent_cache_slo_min_eligible_requests",
            "conversation_compaction_reserve_tokens",
            "compression_min_chars",
            "compression_target_chars",
            "compression_context_chars",
            "llm_ingest_max_tokens",
            "llm_ingest_concurrency",
            "worker_batch_size",
            "bulk_reprocess_page_size",
            "maintenance_daily_token_budget",
            "webdav_auto_sync_interval_minutes",
            "llm_default_tps",
            "llm_chat_tps",
            "llm_reflect_tps",
            "llm_ingest_tps",
            "llm_vision_tps",
            "llm_default_context_window",
            "llm_chat_context_window",
            "llm_reflect_context_window",
            "llm_ingest_context_window",
            "llm_vision_context_window",
            "embedding_dimensions",
            "embedding_tps",
            "embedding_batch_size",
            "semantic_recall_limit",
            "semantic_rebuild_page_size",
            "section_embedding_max_sections",
            "rerank_tps",
            "rerank_batch_size",
            "rerank_top_n",
            "rerank_max_doc_chars",
            "rerank_concurrency",
            "document_vision_max_images",
            "document_vision_question_max_images",
            "document_vision_min_image_bytes",
            "document_vision_min_image_dimension",
            "document_vision_min_image_area",
        ):
            try:
                v = int(v)
            except (TypeError, ValueError):
                bad.append(f"{k}: must be an integer")
                continue
            lower = (
                0
                if k in ("agent_final_answer_continue_turns", "llm_ingest_max_tokens")
                else 1
            )
            if k == "agent_execute_max_turns":
                lower, upper = 3, 100
            elif k in ("llm_ingest_concurrency", "worker_batch_size"):
                upper = 32
            elif k == "llm_ingest_max_tokens":
                upper = 16_384
            elif k == "bulk_reprocess_page_size":
                lower, upper = 10, 5_000
            elif k == "maintenance_daily_token_budget":
                lower, upper = 0, 200_000_000
            elif k == "webdav_auto_sync_interval_minutes":
                lower, upper = 5, 10_080
            elif k == "embedding_dimensions":
                upper = 8192
            elif k == "embedding_batch_size":
                upper = 10
            elif k in (
                "embedding_tps",
                "rerank_tps",
                "rerank_batch_size",
                "llm_default_tps",
                "llm_chat_tps",
                "llm_reflect_tps",
                "llm_ingest_tps",
                "llm_vision_tps",
            ):
                upper = 10_000
            elif k == "semantic_recall_limit":
                upper = 1000
            elif k == "semantic_rebuild_page_size":
                upper = 1000
            elif k == "section_embedding_max_sections":
                lower, upper = 0, 200
            elif k == "agent_cache_slo_min_eligible_requests":
                upper = 1_000_000
            elif k == "conversation_compaction_reserve_tokens":
                lower, upper = 1024, 1_000_000
            elif k.endswith("_context_window"):
                lower, upper = 1024, 10_000_000
            elif k == "rerank_top_n":
                upper = 1000
            elif k == "rerank_max_doc_chars":
                upper = 200000
            elif k == "rerank_concurrency":
                upper = 64
            elif k == "document_vision_max_images":
                lower, upper = 0, 500
            elif k == "document_vision_question_max_images":
                upper = 50
            elif k == "document_vision_min_image_bytes":
                lower, upper = 0, 100_000_000
            elif k == "document_vision_min_image_dimension":
                lower, upper = 0, 100_000
            elif k == "document_vision_min_image_area":
                lower, upper = 0, 100_000_000
            else:
                upper = 200000
            if v < lower or v > upper:
                bad.append(f"{k}: out of range [{lower}, {upper}]")
                continue
        if k in (
            "agent_turn_timeout_seconds",
            "compression_max_ratio",
            "agent_cache_slo_min_hit_ratio",
            "section_backfill_min_score",
        ):
            try:
                v = float(v)
            except (TypeError, ValueError):
                bad.append(f"{k}: must be a number")
                continue
            if k == "compression_max_ratio":
                lower, upper = 0.05, 1.0
            elif k in ("agent_cache_slo_min_hit_ratio", "section_backfill_min_score"):
                lower, upper = 0.0, 1.0
            else:
                lower, upper = 0.0, 86_400.0
            if v < lower or v > upper:
                bad.append(f"{k}: out of range [{lower:g}, {upper:g}]")
                continue
        if k in (
            "compression_enabled",
            "semantic_recall_enabled",
            "rerank_enabled",
            "relation_background_vetting_enabled",
            "webdav_auto_sync_enabled",
            "document_vision_enabled",
            "llm_vision_supports_vision",
            "llm_default_supports_vision",
            "llm_default_supports_tools",
            "llm_default_supports_temperature",
            "llm_chat_supports_vision",
            "llm_chat_supports_tools",
            "llm_chat_supports_temperature",
            "llm_reflect_supports_vision",
            "llm_reflect_supports_tools",
            "llm_reflect_supports_temperature",
            "llm_ingest_supports_vision",
            "llm_ingest_supports_tools",
            "llm_ingest_supports_temperature",
            "llm_vision_supports_tools",
            "llm_vision_supports_temperature",
            "conversation_compaction_enabled",
        ):
            if isinstance(v, str):
                v = v.strip().lower() in {"1", "true", "yes", "on"}
            else:
                v = bool(v)
        if k in ("webdav_url", "webdav_username", "webdav_password", "webdav_remote_path"):
            if v is not None:
                v = str(v).strip()
                if not v:
                    v = None
        if k == "webdav_url" and v is not None:
            if not (str(v).startswith("http://") or str(v).startswith("https://")):
                bad.append("webdav_url: must start with http:// or https://")
                continue
        if k == "webdav_remote_path" and v is not None:
            if not str(v).startswith("/"):
                v = "/" + str(v)
        out[k] = v
    if bad:
        raise OverlayValidationError("; ".join(bad))
    return out


def merge_overlay_into_settings(settings: Any, overlay: dict[str, Any]) -> None:
    """Apply `overlay` onto `settings` in place.

    Pydantic v2 `BaseSettings` instances are mutable by default unless
    frozen; `Settings` here is not frozen so attribute assignment works.
    Done in place so the lru_cache result holds the merged view.
    """
    for k, v in overlay.items():
        if hasattr(settings, k):
            setattr(settings, k, v)
