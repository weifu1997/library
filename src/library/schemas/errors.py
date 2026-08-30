"""OpenAPI documentation models for existing error payloads.

These do not change runtime exception handling. They only describe JSON
bodies the code already returns.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class BearerAuthError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    detail: str = "missing or invalid bearer token"


class UploadTooLargeError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: str = "upload_too_large"
    max_bytes: int


class DisplayNameConflictError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: str = "display_name_conflict"
    folder_id: str | None = None
    display_name: str
    existing_entry_id: str
    existing_file_id: str


class CapacityExceededError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: str = "capacity_exceeded"
    resource: str
    limit: int
    current: int


class InvalidDestinationError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: str = "invalid_destination"
    hint: str


class AmbiguousRemotePathError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: str = "ambiguous_remote_path"
    remote_path: str
    hint: str


class FastAPIDetail(BaseModel):
    """FastAPI HTTPException `detail` may be a string or an object."""

    model_config = ConfigDict(extra="allow")
    detail: Any


OPTIONAL_AUTH_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {
        "description": (
            "Missing or invalid bearer token. Only raised when "
            "LIBRARY_API_TOKEN is configured. Tokenless loopback is the default."
        ),
        "model": BearerAuthError,
        "headers": {
            "WWW-Authenticate": {
                "schema": {"type": "string", "example": "Bearer"},
            }
        },
    }
}

UPLOAD_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    **OPTIONAL_AUTH_RESPONSES,
    400: {"description": "Invalid or ambiguous destination", "model": FastAPIDetail},
    404: {"description": "Folder not found", "model": FastAPIDetail},
    409: {"description": "Display name conflict", "model": FastAPIDetail},
    413: {"description": "Upload exceeds upload_max_bytes", "model": FastAPIDetail},
    422: {"description": "Validation error"},
    429: {"description": "Capacity exceeded", "model": FastAPIDetail},
}

CHAT_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    **OPTIONAL_AUTH_RESPONSES,
    400: {"description": "Unsupported image media type", "model": FastAPIDetail},
    404: {"description": "Session not found", "model": FastAPIDetail},
    413: {"description": "Too many images or image too large", "model": FastAPIDetail},
    422: {"description": "Validation error"},
    429: {"description": "Chat concurrency capacity exceeded", "model": FastAPIDetail},
}

CHAT_RESUME_RESPONSES: dict[int | str, dict[str, Any]] = {
    **OPTIONAL_AUTH_RESPONSES,
    404: {"description": "Conversation not found", "model": FastAPIDetail},
    422: {"description": "Validation error"},
}

SETTINGS_WRITE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **OPTIONAL_AUTH_RESPONSES,
    422: {"description": "Overlay or body validation error", "model": FastAPIDetail},
}

__all__ = (
    "AmbiguousRemotePathError",
    "BearerAuthError",
    "CHAT_ERROR_RESPONSES",
    "CHAT_RESUME_RESPONSES",
    "CapacityExceededError",
    "DisplayNameConflictError",
    "FastAPIDetail",
    "InvalidDestinationError",
    "OPTIONAL_AUTH_RESPONSES",
    "SETTINGS_WRITE_RESPONSES",
    "UPLOAD_ERROR_RESPONSES",
    "UploadTooLargeError",
)
