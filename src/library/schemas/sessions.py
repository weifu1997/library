"""Session HTTP response models."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from library.schemas.base import StrictModel


class SessionCreateResponse(StrictModel):
    session_id: str
    started_at: str | None


class CacheSlo(StrictModel):
    status: Literal["met", "breached", "insufficient_data"]
    minimum_hit_ratio: float
    minimum_eligible_requests: int


class SessionTotalsBody(StrictModel):
    turn_count: int
    input_tokens: int
    output_tokens: int
    prompt_tokens: int
    cache_read: int
    cache_creation: int
    cache_eligible_prompt_tokens: int
    cache_eligible_read_tokens: int
    cache_eligible_estimated_tokens: int
    cache_eligible_requests: int
    cache_prompt_coverage_ratio: float | None
    cache_eligible_hit_ratio: float | None
    cache_eligible_reuse_ratio: float | None
    prompt_prefix_breaks: int
    cache_slo: CacheSlo
    tool_calls: int
    llm_calls: int


class SessionCloseResponse(StrictModel):
    session_id: str
    ended_at: str | None
    end_reason: str | None
    totals: SessionTotalsBody


class SessionListEntry(StrictModel):
    session_id: str
    started_at: str | None
    ended_at: str | None
    end_reason: str | None
    preview: str
    mode: str
    turn_count: int
    total_input_tokens: int
    total_output_tokens: int
    total_tool_calls: int


class SessionListResponse(StrictModel):
    sessions: list[SessionListEntry]
    limit: int
    offset: int
    next_cursor: str | None


class ReplayedToolCall(StrictModel):
    tool_call_id: Any | None = None
    tool_index: Any | None = None
    turn: Any | None = None
    name: str | None
    arguments: dict[str, Any]
    display: str | None = None
    ok: bool
    error: Any | None = None
    duration_ms: Any | None = None
    preview: str | None = None


class TurnAttachment(StrictModel):
    name: str
    media_type: str


class VegaLiteArtifact(StrictModel):
    kind: Literal["vega_lite"]
    chart_id: str
    title: str | None = None
    caption: str | None = None
    spec: dict[str, Any]


class DataExportArtifact(StrictModel):
    kind: Literal["data_export"]
    format: Literal["csv"]
    filename: str
    row_count: int
    truncated: bool | None = None
    columns: list[str] | None = None


UserArtifact = Annotated[
    VegaLiteArtifact | DataExportArtifact,
    Field(discriminator="kind"),
]


class TurnMetrics(StrictModel):
    tokens_in: int
    tokens_out: int
    prompt_tokens: int
    cache_read: int
    cache_creation: int
    cache_eligible_prompt_tokens: int
    cache_eligible_read_tokens: int
    cache_eligible_estimated_tokens: int
    cache_eligible_requests: int
    cache_prompt_coverage_ratio: float | None
    cache_eligible_hit_ratio: float | None
    cache_eligible_reuse_ratio: float | None
    prompt_prefix_breaks: int
    cache_slo: CacheSlo
    tool_calls: int
    llm_calls: int
    duration_ms: int


class ReplayedTurn(StrictModel):
    conversation_id: str
    turn_index: int
    mode: str
    started_at: str | None
    ended_at: str | None
    user_message: str | None
    attachments: list[TurnAttachment]
    agent_response: str | None
    error: str | None
    plan_text: str | None
    tool_calls: list[ReplayedToolCall]
    artifacts: list[UserArtifact]
    metrics: TurnMetrics


class SessionTranscriptResponse(StrictModel):
    session_id: str
    started_at: str | None
    ended_at: str | None
    end_reason: str | None
    mode: str
    metrics: TurnMetrics
    turns: list[ReplayedTurn]
