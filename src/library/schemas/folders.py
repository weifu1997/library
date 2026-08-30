"""Folder HTTP response models."""
from __future__ import annotations

from library.schemas.base import ExtraAllowModel, StrictModel


class FolderIngestSummary(StrictModel):
    total: int
    pending: int
    processing: int
    done: int
    failed: int
    incomplete: int
    status: str | None


class FolderResponse(StrictModel):
    id: str
    parent_id: str | None
    name: str
    created_at: str | None
    updated_at: str | None
    ingest_summary: FolderIngestSummary | None = None


class FileEntrySummary(StrictModel):
    id: str
    folder_id: str | None
    file_id: str
    display_name: str
    lifecycle: str
    ingest_status: str | None = None
    ingest_error: str | None = None
    created_at: str | None = None


class FolderListingResponse(StrictModel):
    folders: list[FolderResponse]
    entries: list[FileEntrySummary]


class FolderDetailResponse(FolderResponse):
    children: list[FolderResponse]
    entries: list[FileEntrySummary]


class FolderPatchResponse(ExtraAllowModel):
    id: str | None = None
    parent_id: str | None = None
    name: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    ingest_summary: FolderIngestSummary | None = None
    folder_id: str | None = None


class FolderDeletedResponse(StrictModel):
    folder_id: str
    deleted_at: str | None
