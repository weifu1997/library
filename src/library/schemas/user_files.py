"""User-file HTTP response models (search)."""
from __future__ import annotations

from library.schemas.base import StrictModel


class SearchRelatedEntry(StrictModel):
    entry_id: str
    display_name: str
    score: float


class SearchEntry(StrictModel):
    entry_id: str
    display_name: str
    folder_id: str | None
    folder_path: str | None
    lifecycle: str
    mime_type: str | None
    size_bytes: int | None
    ingest_status: str | None
    created_at: str | None
    updated_at: str | None
    related_entries: list[SearchRelatedEntry]


class SearchResponse(StrictModel):
    q: str
    count: int
    entries: list[SearchEntry]
