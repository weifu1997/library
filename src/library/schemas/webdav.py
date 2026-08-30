"""WebDAV sync HTTP response models."""
from __future__ import annotations

from typing import Any

from library.schemas.base import ExtraAllowModel, StrictModel
from library.schemas.settings import WebDavStatus


class WebDavPublishResponse(StrictModel):
    ok: bool
    task_id: str | None


class WebDavTestResponse(ExtraAllowModel):
    ok: bool
    remote_path: str | None = None
    latest: Any = None


class WebDavRemoteStatusResponse(ExtraAllowModel):
    ok: bool
    remote_path: str | None = None
    status: str | None = None
    checked_at: str | None = None
    latest: Any = None
    manifest: Any = None


class WebDavPlanItem(ExtraAllowModel):
    entry_id: str
    display_name: str
    folder_id: str | None = None
    folder_path: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    updated_at: str | None = None
    reason: str


class WebDavPlanResponse(ExtraAllowModel):
    ok: bool
    remote_path: str | None = None
    snapshot_id: str | None = None
    remote_updated_at: str | None = None
    app_version: str | None = None
    count: int | None = None
    items: list[WebDavPlanItem] | None = None


class WebDavPullResponse(ExtraAllowModel):
    ok: bool
    remote_path: str | None = None
    snapshot_id: str | None = None
    folders: int | None = None
    catalogs: int | None = None
    views: int | None = None
    tags: int | None = None
    tag_aliases: int | None = None
    entries: int | None = None
    entry_tags: int | None = None
    relations: int | None = None
    remote_files: int | None = None
    downloaded_files: int | None = None
    failed_files: int | None = None
    errors: list[Any] | None = None


class WebDavPublishSelectedResponse(ExtraAllowModel):
    ok: bool
    status: str | None = None
    selected_entries: int | None = None
    started_at: str | None = None
    finished_at: str | None = None
    snapshot_id: str | None = None
    remote_path: str | None = None
    latest_snapshot: str | None = None
    selected_files: int | None = None
    total_blobs: int | None = None
    processed_blobs: int | None = None
    uploaded_blobs: int | None = None
    skipped_blobs: int | None = None
    total_metadata_files: int | None = None
    uploaded_metadata_files: int | None = None
    entry_count: int | None = None
    blob_count: int | None = None
    blob_bytes: int | None = None
    error: str | None = None


class WebDavHydrateResponse(ExtraAllowModel):
    ok: bool
    entry_id: str | None = None
    file_id: str | None = None
    hydrated: bool | None = None
    already_local: bool | None = None
    storage_key: str | None = None


__all__ = (
    "WebDavHydrateResponse",
    "WebDavPlanResponse",
    "WebDavPublishResponse",
    "WebDavPublishSelectedResponse",
    "WebDavPullResponse",
    "WebDavRemoteStatusResponse",
    "WebDavStatus",
    "WebDavTestResponse",
)
