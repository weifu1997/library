"""Host allowlist — the DNS-rebinding guard.

With no LIBRARY_API_TOKEN (the default) every endpoint is open to anything
that can reach the port, and a web page the user visits can become one of
those things: the attacker's domain resolves to their server, then rebinds to
127.0.0.1, and the browser then treats http://evil.example:8000 as same-origin
so CORS never participates. Checking the Host header is what closes that,
because the rebound request still announces the attacker's hostname.

The startup warning in _warn_if_unauthenticated_bind does not cover this: the
bind address really is loopback, which is why the attack works at all.
"""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

_TEST_ROOT = Path(__file__).resolve().parent / f"_host_allow_{os.getpid()}_{uuid4().hex[:8]}"
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
from library.main import _host_without_port, _trusted_hosts, app  # noqa: E402


async def _create_schema() -> None:
    """conftest calls this per module; the allowlist-passes cases reach a real
    route and would otherwise fail on a missing table rather than on Host."""
    from library.db.bootstrap import bootstrap_schema

    await bootstrap_schema()


def _client(host: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url=f"http://{host}",
    )


# ---- the guard itself -------------------------------------------------


async def test_rebinding_host_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "library_trusted_hosts", "")
    monkeypatch.setattr(settings, "library_api_token", None)
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)

    async with _client("evil.example") as c:
        r = await c.get("/v1/folders")

    assert r.status_code == 421
    assert "untrusted Host" in r.text


@pytest.mark.parametrize("host", ["127.0.0.1:8000", "localhost:5173", "[::1]:8000"])
async def test_loopback_hosts_pass(
    host: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "library_trusted_hosts", "")
    monkeypatch.setattr(settings, "library_api_token", None)
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)

    async with _client(host) as c:
        r = await c.get("/v1/folders")

    assert r.status_code != 421, r.text


async def test_probe_paths_are_exempt(monkeypatch: pytest.MonkeyPatch) -> None:
    """A liveness probe must not fail closed to withhold a version string."""
    settings = get_settings()
    monkeypatch.setattr(settings, "library_trusted_hosts", "")
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)

    async with _client("some-orchestrator-service") as c:
        r = await c.get("/live")

    assert r.status_code == 200


async def test_empty_host_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """CROSS-M1: missing/empty Host must not skip the allowlist."""
    settings = get_settings()
    monkeypatch.setattr(settings, "library_trusted_hosts", "")
    monkeypatch.setattr(settings, "library_api_token", None)
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)

    async with _client("127.0.0.1") as c:
        r = await c.get("/v1/folders", headers={"host": ""})

    assert r.status_code == 421
    assert "untrusted Host" in r.text


async def test_non_ascii_token_does_not_500(monkeypatch: pytest.MonkeyPatch) -> None:
    """CROSS-M2: compare_digest on str used to TypeError → 500."""
    settings = get_settings()
    monkeypatch.setattr(settings, "library_api_token", "令牌")
    monkeypatch.setattr(settings, "library_trusted_hosts", "")
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)

    async with _client("127.0.0.1") as c:
        r = await c.get("/v1/folders")
        # Wrong/missing bearer must be 401, never TypeError 500.
        assert r.status_code == 401, r.text
        r_ascii = await c.get(
            "/v1/folders",
            headers={"Authorization": "Bearer not-the-token"},
        )
        assert r_ascii.status_code == 401, r_ascii.text


async def test_wildcard_disables_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "library_trusted_hosts", "*")
    monkeypatch.setattr(settings, "library_api_token", None)
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)

    async with _client("anything.example") as c:
        r = await c.get("/v1/folders")

    assert r.status_code != 421, r.text


async def test_explicit_allowlist_entry_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reverse-proxy escape hatch."""
    settings = get_settings()
    monkeypatch.setattr(settings, "library_trusted_hosts", "library.example.com")
    monkeypatch.setattr(settings, "library_api_token", None)
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)

    async with _client("library.example.com") as c:
        r = await c.get("/v1/folders")
    assert r.status_code != 421, r.text

    async with _client("other.example.com") as c:
        r = await c.get("/v1/folders")
    assert r.status_code == 421


async def test_rejection_is_readable_by_the_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rejection must sit inside CORS, or the GUI sees an opaque failure
    instead of a diagnosable 421."""
    settings = get_settings()
    monkeypatch.setattr(settings, "library_trusted_hosts", "")
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)

    async with _client("evil.example") as c:
        r = await c.get("/v1/folders", headers={"Origin": "http://localhost:5173"})

    assert r.status_code == 421
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_middleware_sits_inside_cors_and_outside_auth() -> None:
    """Order lock. Outside CORS the rejection is unreadable; inside auth it
    would run too late to matter for a tokenless deployment."""
    names = [
        m.kwargs["dispatch"].__name__
        if m.cls.__name__ == "BaseHTTPMiddleware"
        else m.cls.__name__
        for m in app.user_middleware
    ]
    assert names[0] == CORSMiddleware.__name__
    assert "host_allowlist" in names
    assert names.index("host_allowlist") < names.index("optional_bearer_auth")


# ---- helpers ----------------------------------------------------------


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("127.0.0.1:8000", "127.0.0.1"),
        ("localhost", "localhost"),
        ("Evil.Example:443", "evil.example"),
        ("[::1]:8000", "[::1]"),
        ("[::1]", "[::1]"),
        ("::1", "::1"),
        ("", ""),
    ],
)
def test_host_without_port(header: str, expected: str) -> None:
    assert _host_without_port(header) == expected


def test_trusted_hosts_composition() -> None:
    class _S:
        library_trusted_hosts = " Proxy.Example , , second.example "
        library_api_host = "192.168.1.50"

    hosts = _trusted_hosts(_S())
    assert hosts is not None
    assert {"localhost", "127.0.0.1", "[::1]", "embedded"} <= hosts
    assert "proxy.example" in hosts and "second.example" in hosts
    # LIBRARY_API_HOST joins the allowlist so a LAN bind keeps working.
    assert "192.168.1.50" in hosts or os.environ.get("LIBRARY_API_HOST")


def test_trusted_hosts_wildcard_returns_none() -> None:
    class _S:
        library_trusted_hosts = "*"
        library_api_host = "127.0.0.1"

    assert _trusted_hosts(_S()) is None


def test_embedded_cli_host_is_trusted() -> None:
    """The in-process CLI and MCP server drive the app over ASGITransport with
    `Host: embedded`. Rejecting that would break `library` itself."""
    class _S:
        library_trusted_hosts = ""
        library_api_host = "127.0.0.1"

    hosts = _trusted_hosts(_S())
    assert hosts is not None and main_module.EMBEDDED_HOST_NAME in hosts
