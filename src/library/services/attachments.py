"""Chat image attachment persistence — UI-only re-display.

Pasted chat images are written to disk purely so the GUI can re-render a
thumbnail when the user reopens a past session. They are NEVER re-sent to
the LLM: history replay reads only the ``[image attached]`` placeholder from
``conversations.user_message`` (see ``agent.runtime._persisted_user_message``).
Saving + serving here is completely decoupled from the model message tape —
the LLM-token invariant does not touch these files.

Layout::

    <LIBRARY_HOME>/attachments/<conversation_id>/<idx>.<ext>

  - ``idx`` is 1-based, in paste order for the turn.
  - ``ext`` is derived from the ImageBlock media_type
    (image/png->png, image/jpeg->jpg, image/gif->gif, image/webp->webp).
"""
from __future__ import annotations

import base64
import binascii
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from library.config import Settings, get_settings

if TYPE_CHECKING:
    from library.llm.types import ImageBlock

log = logging.getLogger(__name__)

# media_type -> canonical on-disk extension.
_EXT_BY_MEDIA_TYPE: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
}

# extension -> canonical media_type (used when scanning / serving files back).
_MEDIA_TYPE_BY_EXT: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}

# Strict filename shape: 1-based numeric index + one allowed extension. This
# alone rejects any traversal attempt ("../x", "1/2.png") and any non-image
# name ("1.txt") because it forbids slashes, dots-dots, and other extensions.
_NAME_RE = re.compile(r"^\d+\.(png|jpe?g|gif|webp)$")


def attachments_root(settings: Settings) -> Path:
    """Root directory holding every conversation's attachment folder."""
    return Path(settings.library_home).expanduser() / "attachments"


def _conversation_dir(conversation_id: str) -> Path:
    return attachments_root(get_settings()) / conversation_id


def save_turn_attachments(
    conversation_id: str, images: list["ImageBlock"],
) -> list[dict[str, str]]:
    """Persist a turn's pasted images under ``<root>/<conversation_id>/``.

    Each image is written as ``<idx>.<ext>`` (1-based, paste order). Returns
    the ``[{"name": "1.png", "media_type": "image/png"}, ...]`` manifest for
    the images that were saved. Best-effort per image: an undecodable or
    unknown-media-type block is logged and skipped rather than aborting the
    whole save (the caller further shields the turn from any hard failure).
    """
    if not images:
        return []
    conv_dir = _conversation_dir(conversation_id)
    conv_dir.mkdir(parents=True, exist_ok=True)
    saved: list[dict[str, str]] = []
    for idx, image in enumerate(images, start=1):
        media_type = getattr(image, "media_type", "")
        ext = _EXT_BY_MEDIA_TYPE.get(media_type)
        if ext is None:
            log.warning(
                "skipping attachment %d for conversation %s: unsupported "
                "media_type %r", idx, conversation_id, media_type,
            )
            continue
        try:
            data = base64.b64decode(image.data_b64, validate=True)
        except (binascii.Error, ValueError):
            log.warning(
                "skipping attachment %d for conversation %s: invalid base64",
                idx, conversation_id,
            )
            continue
        name = f"{idx}.{ext}"
        (conv_dir / name).write_bytes(data)
        saved.append({"name": name, "media_type": media_type})
    return saved


def list_turn_attachments(conversation_id: str) -> list[dict[str, str]]:
    """Return the stored attachment manifest for a conversation, sorted by idx.

    Empty list when the conversation has no attachment directory (the common,
    text-only case) or when it holds no recognizable image files.
    """
    conv_dir = _conversation_dir(conversation_id)
    if not conv_dir.is_dir():
        return []
    items: list[tuple[int, dict[str, str]]] = []
    for entry in conv_dir.iterdir():
        if not entry.is_file():
            continue
        name = entry.name
        if not _NAME_RE.match(name):
            continue
        idx_str, ext = name.rsplit(".", 1)
        media_type = _MEDIA_TYPE_BY_EXT.get(ext.lower())
        if media_type is None:
            continue
        try:
            idx = int(idx_str)
        except ValueError:
            continue
        items.append((idx, {"name": name, "media_type": media_type}))
    items.sort(key=lambda item: item[0])
    return [manifest for _, manifest in items]


def read_attachment(
    conversation_id: str, name: str,
) -> tuple[bytes, str] | None:
    """Read one stored attachment, returning ``(bytes, media_type)`` or None.

    STRICT validation: ``name`` must match ``^\\d+\\.(png|jpe?g|gif|webp)$``
    and the resolved path must stay inside the conversation's attachment
    directory. Any traversal attempt, unknown extension, or missing file
    yields None (the route maps that to a 404).
    """
    if not _NAME_RE.match(name):
        return None
    ext = name.rsplit(".", 1)[1].lower()
    media_type = _MEDIA_TYPE_BY_EXT.get(ext)
    if media_type is None:
        return None
    conv_dir = _conversation_dir(conversation_id).resolve()
    target = (conv_dir / name).resolve()
    # Defence in depth: even though _NAME_RE forbids separators, confirm the
    # resolved path did not escape the conversation directory.
    try:
        target.relative_to(conv_dir)
    except ValueError:
        return None
    if not target.is_file():
        return None
    return target.read_bytes(), media_type
