"""Upload HTTP response models."""
from __future__ import annotations

from library.schemas.base import StrictModel


class UploadResponse(StrictModel):
    file_id: str
    entry_id: str
    folder_id: str | None
    display_name: str
    deduped: bool
    auto_renamed: bool
    skipped: bool
