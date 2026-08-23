"""Opaque keyset cursors shared by growing collection endpoints."""
from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

from fastapi import HTTPException

_CURSOR_VERSION = 1
_MAX_CURSOR_LENGTH = 1024


def encode_desc_cursor(timestamp: datetime, row_id: str) -> str:
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    payload = {
        "v": _CURSOR_VERSION,
        "t": timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "id": str(row_id),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_desc_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        clean = str(cursor or "").strip()
        if not clean or len(clean) > _MAX_CURSOR_LENGTH:
            raise ValueError("cursor length")
        padded = clean + "=" * (-len(clean) % 4)
        payload = json.loads(base64.b64decode(padded, altchars=b"-_", validate=True))
        if not isinstance(payload, dict) or payload.get("v") != _CURSOR_VERSION:
            raise ValueError("cursor version")
        raw_time = payload.get("t")
        row_id = payload.get("id")
        if not isinstance(raw_time, str) or not isinstance(row_id, str) or not row_id:
            raise ValueError("cursor fields")
        timestamp = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("cursor timezone")
        return timestamp, row_id
    except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="invalid pagination cursor") from exc
