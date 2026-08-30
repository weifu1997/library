"""Task introspection HTTP response models."""
from __future__ import annotations

from typing import Any

from library.schemas.base import StrictModel


class RunningCountResponse(StrictModel):
    running: int
    pending: int


class ActiveTaskItem(StrictModel):
    id: str
    kind: str
    label: str
    file_id: Any | None = None
    entry_id: Any | None = None
    attempts: int
    age_s: int


class ActiveTasksResponse(StrictModel):
    running: list[ActiveTaskItem]
    pending: list[ActiveTaskItem]


class RecentTaskItem(StrictModel):
    id: str
    kind: str
    status: str
    label: str
    file_id: Any | None = None
    entry_id: Any | None = None
    started_at: str | None
    finished_at: str | None
    last_error: str | None
    duration_ms: float | int | None = None
    tokens_in: int | None = None
    prompt_tokens: int | None = None
    tokens_out: int | None = None
    cache_read: int | None = None
    cache_creation: int | None = None
    llm_calls: int | None = None
    stages_ms: dict[str, Any]


class RecentTasksResponse(StrictModel):
    items: list[RecentTaskItem]
    next_cursor: str | None


class TaskThroughputKindRow(StrictModel):
    kind: str
    pending: int
    running: int
    done: int
    failed: int
    oldest_pending_age_seconds: int
    average_duration_seconds: float | None
    success_rate: float | None
    completed_per_minute: float


class TaskThroughputQueue(StrictModel):
    pending: int
    running: int
    total: int
    oldest_pending_age_seconds: int


class TaskThroughputCompleted(StrictModel):
    done: int
    failed: int
    success_rate: float | None
    files_per_minute: float


class TaskThroughputResponse(StrictModel):
    window_minutes: int
    since: str
    queue: TaskThroughputQueue
    completed: TaskThroughputCompleted
    by_kind: list[TaskThroughputKindRow]
