"""Settings HTTP response models."""
from __future__ import annotations

from typing import Any, Literal

from library.schemas.base import OmitUnsetModel, StrictModel


class SemanticIndexStatus(StrictModel):
    index_name: str
    index_dir: str
    exists: bool
    provider: str | None
    model: str | None
    dimensions: int | None
    entries: int
    documents: int
    section_entries: int
    configured_provider: str
    configured_model: str
    configured_dimensions: int
    rebuild_page_size: int
    compatible: bool
    needs_rebuild: bool


class WebDavStatus(StrictModel):
    configured: bool
    url: str | None
    username: str | None
    password_set: bool
    remote_path: str
    auto_sync_enabled: bool
    auto_sync_interval_minutes: int
    last: dict[str, Any] | None


class ServerSettingsResponse(StrictModel):
    app_env: str
    library_home: str
    db_backend: Literal["sqlite", "postgres"]
    postgres_pool_size: int
    postgres_max_overflow: int
    postgres_pool_timeout_seconds: float
    postgres_prepared_statement_cache_size: int
    runtime_schema_bootstrap_enabled: bool
    readiness_timeout_seconds: float
    storage_backend: Literal["mirror", "local", "s3"]
    worker_enabled: bool
    worker_running: bool
    worker_scheduler_enabled: bool
    worker_batch_size: int
    worker_retry_base_seconds: float
    worker_retry_max_seconds: float
    bulk_reprocess_page_size: int
    auto_lifecycle_enabled: bool
    maintenance_daily_token_budget: int
    relation_background_vetting_enabled: bool
    audit_retention_days: int
    task_retention_days: int
    task_outcome_retention_days: int
    agent_event_retention_days: int
    prune_batch_size: int
    prune_max_batches: int
    relation_mining_entry_page_size: int
    relation_mining_activity_limit: int
    relation_mining_eligible_tag_limit: int
    relation_mining_candidate_limit: int
    library_document_limit: int
    library_storage_bytes_limit: int
    ingest_backlog_limit: int
    chat_concurrency_limit: int
    default_on_conflict: Literal["rename", "error", "skip"]
    agent_plan_max_tokens: int
    agent_execute_max_tokens: int
    agent_execute_max_turns: int
    agent_max_parallel_tool_calls: int
    agent_final_answer_continue_turns: int
    agent_final_answer_max_chars: int
    agent_turn_timeout_seconds: float
    agent_cache_slo_min_hit_ratio: float
    agent_cache_slo_min_eligible_requests: int
    conversation_compaction_enabled: bool
    conversation_compaction_reserve_tokens: int
    compression_enabled: bool
    compression_min_chars: int
    compression_target_chars: int
    compression_context_chars: int
    compression_max_ratio: float
    llm_ingest_max_tokens: int
    llm_ingest_concurrency: int
    llm_default_tps: int
    llm_chat_tps: int
    llm_reflect_tps: int
    llm_ingest_tps: int
    llm_vision_tps: int
    llm_vision_supports_vision: bool
    embedding_provider: Literal["dashscope", "openai-compatible"]
    embedding_api_key_set: bool
    embedding_base_url: str
    embedding_model: str
    embedding_dimensions: int
    embedding_tps: int
    embedding_batch_size: int
    semantic_index_backend: Literal["auto", "file", "sqlite-vec"]
    semantic_recall_enabled: bool
    semantic_recall_limit: int
    semantic_rebuild_page_size: int
    section_backfill_min_score: float
    section_embedding_max_sections: int
    semantic_recall_configured: bool
    semantic_index: SemanticIndexStatus
    rerank_enabled: bool
    rerank_api_key_set: bool
    rerank_base_url: str
    rerank_model: str
    rerank_tps: int
    rerank_batch_size: int
    rerank_top_n: int
    rerank_max_doc_chars: int
    rerank_concurrency: int
    rerank_configured: bool
    evidence_selection: Literal["quota", "rerank"]
    vision_profile_configured: bool
    document_vision_enabled: bool
    document_vision_max_images: int
    document_vision_question_max_images: int
    document_vision_min_image_bytes: int
    document_vision_min_image_dimension: int
    document_vision_min_image_area: int
    webdav: WebDavStatus


class LlmCapabilities(StrictModel):
    dialect: str
    context_window: int
    tokenizer: str
    supports_vision: bool
    supports_tools: bool
    supports_temperature: bool
    token_limit_param: Literal["max_tokens", "max_completion_tokens"]


class LlmBackup(StrictModel):
    provider: str | None
    model: str | None
    base_url: str | None
    api_key: str | None
    api_key_set: bool


class LlmProfileResolved(StrictModel):
    provider: str | None
    api_key: str | None
    api_key_set: bool
    base_url: str | None
    model: str | None
    tps: int
    capabilities: LlmCapabilities
    backup: LlmBackup | None


class LlmVisibleProfiles(StrictModel):
    chat: LlmProfileResolved
    reflect: LlmProfileResolved
    ingest: LlmProfileResolved
    vision: LlmProfileResolved


class LlmDefaults(StrictModel):
    provider: str
    model: str
    base_url: str | None
    api_key: str | None
    api_key_set: bool
    tps: int
    backup: LlmBackup | None
    capabilities: LlmCapabilities


class LlmSettingsResponse(StrictModel):
    profiles: LlmVisibleProfiles
    overlay: dict[str, Any]
    defaults: LlmDefaults


class LlmSettingsPutResponse(OmitUnsetModel):
    profiles: LlmVisibleProfiles
    overlay: dict[str, Any]
    defaults: LlmDefaults
    worker_error: str | None = None
    reprocessed_failed: int | None = None


class LlmProbeVerdict(OmitUnsetModel):
    ok: bool | None
    model: str | None = None
    provider: str | None = None
    duration_ms: float | None = None
    mode: Literal["text", "image"] | None = None
    note: str | None = None
    error: str | None = None
    configured: bool | None = None
    dimensions: int | None = None


class LlmTestResponse(OmitUnsetModel):
    profiles: dict[str, LlmProbeVerdict]
    embedding: LlmProbeVerdict | None = None
    rerank: LlmProbeVerdict | None = None
    duration_ms: float


class LlmModelInfo(StrictModel):
    id: str
    display_name: str | None


class LlmModelsResponse(OmitUnsetModel):
    ok: bool
    models: list[LlmModelInfo] | None = None
    provider: str | None = None
    base_url: str | None = None
    error: str | None = None
    duration_ms: float
