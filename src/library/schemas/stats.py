"""Stats HTTP response models."""
from __future__ import annotations

from library.schemas.base import StrictModel


class StatsRecentEntry(StrictModel):
    entry_id: str
    display_name: str
    folder_path: str | None
    created_at: str | None
    ingest_status: str | None


class StatsTotals(StrictModel):
    entries: int
    folders: int
    tags: int


class StatsTasks(StrictModel):
    running: int
    pending: int


class StatsSemantic(StrictModel):
    enabled: bool
    configured: bool
    index_ready: bool


class StatsOverviewResponse(StrictModel):
    totals: StatsTotals
    tasks: StatsTasks
    recent: list[StatsRecentEntry]
    storage_backend: str
    semantic: StatsSemantic
