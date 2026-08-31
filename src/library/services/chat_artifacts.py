"""User-visible chat artifacts recovered from persisted tool results.

Tools may attach a ``__user_only__`` payload that the runtime strips
before the model sees the tool result and re-emits as a ``user_artifact``
SSE event. ``Conversation.tool_calls`` keep the full result so session
replay can recover the same payload without feeding it back to the LLM.

This module is the single decoder for that side-channel: public artifact
dicts for ``GET /sessions/{id}/messages``, and authorized CSV export reads
for ``GET /conversations/{id}/exports/{filename}``.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from library.config import get_settings
from library.db.models import Conversation

# Filename must be a single path segment of safe characters AND a CSV.
# The first check rejects separators / traversal; the suffix check rejects
# non-CSV names that would otherwise match the character class (it allows dots).
_EXPORT_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def is_export_filename(name: str) -> bool:
    """True when ``name`` is a safe ``*.csv`` path segment."""
    return bool(_EXPORT_NAME_RE.fullmatch(name)) and name.lower().endswith(".csv")


def exports_dir() -> Path:
    """Configured CSV export directory (``LIBRARY_HOME/exports``)."""
    return Path(get_settings().library_home).expanduser() / "exports"


def public_artifact(payload: object) -> dict[str, Any] | None:
    """Project a ``__user_only__`` blob into the GUI-facing artifact shape.

    Unknown kinds, malformed payloads, and filesystem ``path`` fields are
    dropped — the browser cannot read server paths, and unknown shapes
    must not crash transcript replay.
    """
    if not isinstance(payload, dict):
        return None
    kind = payload.get("kind")
    if kind == "vega_lite":
        chart_id = payload.get("chart_id")
        spec = payload.get("spec")
        if not isinstance(chart_id, str) or not chart_id.strip():
            return None
        if not isinstance(spec, dict):
            return None
        out: dict[str, Any] = {
            "kind": "vega_lite",
            "chart_id": chart_id,
            "spec": spec,
        }
        title = payload.get("title")
        caption = payload.get("caption")
        if isinstance(title, str) and title:
            out["title"] = title
        if isinstance(caption, str) and caption:
            out["caption"] = caption
        return out
    if kind == "data_export":
        filename = payload.get("filename")
        fmt = payload.get("format")
        row_count = payload.get("row_count")
        if fmt != "csv":
            return None
        if not isinstance(filename, str) or not is_export_filename(filename):
            return None
        if not isinstance(row_count, int) or isinstance(row_count, bool):
            return None
        out = {
            "kind": "data_export",
            "format": "csv",
            "filename": filename,
            "row_count": row_count,
        }
        truncated = payload.get("truncated")
        if isinstance(truncated, bool):
            out["truncated"] = truncated
        columns = payload.get("columns")
        if isinstance(columns, list) and all(isinstance(c, str) for c in columns):
            out["columns"] = columns
        return out
    return None


def artifacts_from_tool_calls(tool_calls: object) -> list[dict[str, Any]]:
    """Recover GUI artifacts from persisted ``tool_calls[*].result.__user_only__``."""
    if not isinstance(tool_calls, list):
        return []
    artifacts: list[dict[str, Any]] = []
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        result = tc.get("result")
        if not isinstance(result, dict):
            continue
        artifact = public_artifact(result.get("__user_only__"))
        if artifact is not None:
            artifacts.append(artifact)
    return artifacts


def conversation_export_filenames(conversation: Conversation) -> set[str]:
    """CSV filenames referenced by this conversation's persisted tool results."""
    names: set[str] = set()
    for artifact in artifacts_from_tool_calls(conversation.tool_calls):
        if artifact.get("kind") == "data_export":
            filename = artifact.get("filename")
            if isinstance(filename, str):
                names.add(filename)
    return names


def resolve_conversation_export(
    conversation: Conversation, filename: str,
) -> Path | None:
    """Return the on-disk CSV path if this conversation is allowed to serve it.

    404-equivalent (``None``) when the name is unsafe, the conversation's
    persisted tool result does not reference it, or the file is missing /
    outside the configured exports directory.
    """
    if not is_export_filename(filename):
        return None
    if filename not in conversation_export_filenames(conversation):
        return None
    root = exports_dir().resolve()
    target = (root / filename).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    if not target.is_file():
        return None
    return target
