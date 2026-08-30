"""CORS must be the outermost middleware.

Starlette's `add_middleware` inserts at position 0, so registration order is
the reverse of execution order. Registered first, CORSMiddleware ends up
innermost and every short-circuited response — an auth 401, an upload 413 —
goes out without `Access-Control-Allow-Origin`. The browser then surfaces an
opaque CORS failure instead of the real status, so the GUI cannot tell the
user "your token expired" or "that file is too large".

The bug is invisible by inspection (the registration reads top-to-bottom but
executes bottom-to-top), which is why the position is asserted here rather
than left to a comment.
"""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

_TEST_ROOT = Path(__file__).resolve().parent / f"_cors_order_{os.getpid()}_{uuid4().hex[:8]}"
_TEST_ROOT.mkdir(parents=True, exist_ok=True)
os.environ["LIBRARY_HOME"] = str(_TEST_ROOT)
os.environ["WORKER_ENABLED"] = "false"
os.environ["LLM_DEFAULT_API_KEY"] = "sk-fake"
os.environ["LLM_DEFAULT_MODEL"] = "fake-model"

from library.config import Settings as _Settings  # noqa: E402

_Settings.model_config["env_file"] = None

import httpx  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from httpx import ASGITransport  # noqa: E402

from library import main as main_module  # noqa: E402
from library.config import get_settings  # noqa: E402
from library import upload_limits  # noqa: E402
from library.main import _cors_origins, app  # noqa: E402

_ORIGIN = "http://localhost:5173"


def test_cors_is_the_outermost_middleware() -> None:
    """Regression lock: anything registered after CORSMiddleware sits outside
    it and reintroduces the missing-header bug."""
    stack = app.user_middleware
    assert stack, "no middleware registered"
    assert stack[0].cls is CORSMiddleware, (
        "CORSMiddleware must be registered LAST so it is outermost; "
        f"outermost is currently {stack[0].cls.__name__}"
    )


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://t",
    )


async def test_invalid_token_401_carries_cors_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "library_api_token", "correct-token")
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)

    async with _client() as c:
        r = await c.get(
            "/v1/folders",
            headers={"Origin": _ORIGIN, "Authorization": "Bearer wrong-token"},
        )

    assert r.status_code == 401
    # Without this header the browser rejects the response before the app can
    # read the status, and the 401 is indistinguishable from a network error.
    assert r.headers.get("access-control-allow-origin") == _ORIGIN


async def test_upload_too_large_413_carries_cors_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other middleware that short-circuits ahead of the router."""
    settings = get_settings()
    monkeypatch.setattr(settings, "library_api_token", None)
    monkeypatch.setattr(settings, "upload_max_bytes", 64)
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(upload_limits, "get_settings", lambda: settings)

    # The middleware admits max_bytes + MULTIPART_NON_FILE_BUDGET before it
    # needs to parse multipart parts, so exceed that raw ceiling directly.
    body = b"x" * (64 + upload_limits.MULTIPART_NON_FILE_BUDGET + 1024)
    async with _client() as c:
        r = await c.post(
            "/v1/upload",
            headers={
                "Origin": _ORIGIN,
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(body)),
            },
            content=body,
        )

    assert r.status_code == 413, r.text
    assert r.headers.get("access-control-allow-origin") == _ORIGIN


async def test_preflight_still_works() -> None:
    async with _client() as c:
        r = await c.options(
            "/v1/folders",
            headers={
                "Origin": _ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )

    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == _ORIGIN


def test_cors_origins_defaults_and_override() -> None:
    settings = get_settings()

    class _S:
        library_cors_origins = ""

    assert _cors_origins(_S()) == [
        "http://localhost:5173", "http://127.0.0.1:5173",
    ]

    class _Custom:
        library_cors_origins = "https://library.example.com/, http://10.0.0.5:8080"

    assert _cors_origins(_Custom()) == [
        "https://library.example.com", "http://10.0.0.5:8080",
    ]

    # A real Settings instance exposes the field with the documented default.
    assert settings.library_cors_origins == ""
