from __future__ import annotations

import pytest
from fastapi import HTTPException

from library.api import routes_user_files as routes


class _TinyStorage:
    def __init__(self, bodies: dict[str, bytes]) -> None:
        self.bodies = bodies

    async def get(self, key: str):
        yield self.bodies[key]


@pytest.mark.asyncio
async def test_folder_zip_raises_413_before_streaming(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes, "FOLDER_ZIP_MAX_UNCOMPRESSED_BYTES", 8)
    storage = _TinyStorage({"a": b"0123456789"})
    with pytest.raises(HTTPException) as exc:
        await routes._build_folder_zip(storage, [("a.txt", "a")])
    assert exc.value.status_code == 413


@pytest.mark.asyncio
async def test_folder_zip_success_path_stays_under_cap() -> None:
    storage = _TinyStorage({"a": b"hello"})
    archive = await routes._build_folder_zip(storage, [("a.txt", "a")])
    assert archive[:2] == b"PK"
