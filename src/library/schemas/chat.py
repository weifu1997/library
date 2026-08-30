"""SSE payload models for OpenAPI documentation only.

These are not attached as FastAPI JSON response_model on EventSourceResponse
routes. They describe `data:` payloads of `text/event-stream` frames.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _SsePayload(BaseModel):
    model_config = ConfigDict(extra="allow")


class PlanBudget(_SsePayload):
    mode: str | None = None
    tier: str | None = None
    initial_tier: str | None = None
    limit: int | None = None
    hard_limit: int | None = None
    source: str | None = None
    upgrades: int | None = None


class PlanEvent(_SsePayload):
    text: str
    budget: PlanBudget | None = None


class ThinkingEvent(_SsePayload):
    round: int | None = None
    limit: int | None = None
    hard_limit: int | None = None
    final_continuation: bool | None = None
    mode: str | None = None
    budget_tier: str | None = None
    budget_initial_tier: str | None = None
    budget_upgrades: int | None = None
    budget_upgraded: bool | None = None
    previous_limit: int | None = None
    force_final_answer: bool | None = None
    forced_answer_retry: bool | None = None
    answer_phase: str | None = None
    finalization_attempt: int | None = None


class ToolCallEvent(_SsePayload):
    tool_call_id: str | None = None
    tool_index: int | None = None
    turn: int | None = None
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    display: str | None = None
    entry_names: dict[str, str] | None = None
    tag_names: dict[str, str] | None = None
    folder_names: dict[str, str] | None = None
    catalog_names: dict[str, str] | None = None


class ToolResultEvent(_SsePayload):
    tool_call_id: str | None = None
    tool_index: int | None = None
    turn: int | None = None
    name: str | None = None
    ok: bool | None = None
    error: str | None = None
    preview: str | None = None
    duration_ms: float | int | None = None
    deduped: bool | None = None


class UserArtifactEvent(_SsePayload):
    tool_call_id: str | None = None
    tool_index: int | None = None
    turn: int | None = None
    tool: str
    payload: Any = None


class DoneEvent(_SsePayload):
    session_id: str | None = None
    conversation_id: str | None = None
    tokens_in: int | None = None
    prompt_tokens: int | None = None
    tokens_out: int | None = None
    cache_read: int | None = None
    cache_creation: int | None = None
    cache_eligible_prompt_tokens: int | None = None
    cache_eligible_read_tokens: int | None = None
    cache_eligible_estimated_tokens: int | None = None
    cache_eligible_requests: int | None = None
    cache_prompt_coverage_ratio: float | None = None
    cache_eligible_hit_ratio: float | None = None
    cache_eligible_reuse_ratio: float | None = None
    prompt_prefix_breaks: int | None = None
    tool_calls: int | None = None
    llm_calls: int | None = None
    duration_ms: int | None = None
    truncated: bool | None = None
    error: str | None = None
    session_name: str | None = None
    mode: str | None = None
    budget: dict[str, Any] | None = None


SSE_EVENT_CATALOG: dict[str, dict[str, Any]] = {
    "session": {
        "emitted": False,
        "description": (
            "Documented on AgentEvent but not currently yielded by run_turn. "
            "data would be a session_id string if it is ever emitted."
        ),
        "data": {"type": "string"},
    },
    "conversation": {
        "emitted": True,
        "description": "conversation_id string sent when the turn row opens.",
        "data": {"type": "string"},
    },
    "planning": {
        "emitted": True,
        "description": "Transient marker; planner LLM call started. data may be empty.",
        "data": {"type": "string"},
    },
    "plan": {
        "emitted": True,
        "description": "JSON {text, budget?} after the planner returns.",
        "data": PlanEvent.model_json_schema(),
    },
    "thinking": {
        "emitted": True,
        "description": "Execute LLM call started.",
        "data": ThinkingEvent.model_json_schema(),
    },
    "tool_call": {
        "emitted": True,
        "description": "Tool invocation with resolved display names.",
        "data": ToolCallEvent.model_json_schema(),
    },
    "tool_result": {
        "emitted": True,
        "description": "Tool result preview for the UI; may omit unused keys.",
        "data": ToolResultEvent.model_json_schema(),
    },
    "user_artifact": {
        "emitted": True,
        "description": (
            "Side-channel content shown to the user and not fed back to the model."
        ),
        "data": UserArtifactEvent.model_json_schema(),
    },
    "answer": {
        "emitted": True,
        "description": "Final answer text (single chunk).",
        "data": {"type": "string"},
    },
    "error": {
        "emitted": True,
        "description": "Error message string; also used for timeout and cancel.",
        "data": {"type": "string"},
    },
    "done": {
        "emitted": True,
        "description": "Terminal usage JSON. Stream ends after this or error.",
        "data": DoneEvent.model_json_schema(),
    },
}

SSE_OPENAPI_EXTRA: dict[str, Any] = {"x-sse-events": SSE_EVENT_CATALOG}

SSE_200_RESPONSE: dict[str, Any] = {
    "description": "text/event-stream of AgentEvent frames (event, data, id=cursor).",
    "content": {
        "text/event-stream": {
            "schema": {
                "type": "string",
                "format": "event-stream",
                "description": (
                    "SSE frames: event: <name>\\ndata: <payload>\\nid: <cursor>\\n\\n. "
                    "Unknown event names should be treated as 'message' by clients."
                ),
            }
        }
    },
}
