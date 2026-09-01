from __future__ import annotations

import os
import sys

import pytest

from library import __version__
from library import server_main


def test_server_main_uses_sys_argv_when_argv_is_omitted() -> None:
    from library.config import get_settings

    get_settings.cache_clear()
    captured: dict[str, object] = {}
    runtime_env: dict[str, str | None] = {}

    def _fake_run(app: str, **kwargs) -> None:
        captured["app"] = app
        captured.update(kwargs)

    real_argv = sys.argv[:]
    real_run = server_main.uvicorn.run
    old_env = {
        key: os.environ.get(key)
        for key in ("LIBRARY_API_HOST", "LIBRARY_API_PORT", "LIBRARY_HTTP_SERVER")
    }
    try:
        server_main.uvicorn.run = _fake_run  # type: ignore[assignment]
        sys.argv = [
            "python -m library",
            "--host",
            "0.0.0.0",
            "--port",
            "8765",
            "--log-level",
            "warning",
        ]

        rc = server_main.main(prog="python -m library")
        for key in ("LIBRARY_API_HOST", "LIBRARY_API_PORT", "LIBRARY_HTTP_SERVER"):
            runtime_env[key] = os.environ.get(key)
    finally:
        server_main.uvicorn.run = real_run  # type: ignore[assignment]
        sys.argv = real_argv
        get_settings.cache_clear()
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    assert rc == 0
    assert captured["app"] == "library.main:app"
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 8765
    assert captured["log_level"] == "warning"
    assert runtime_env["LIBRARY_API_HOST"] == "0.0.0.0"
    assert runtime_env["LIBRARY_API_PORT"] == "8765"
    assert runtime_env["LIBRARY_HTTP_SERVER"] == "1"


def test_server_main_reads_home_env_when_cwd_has_no_env(tmp_path, monkeypatch) -> None:
    from library.config import get_settings

    home = tmp_path / "home"
    work = tmp_path / "work"
    home.mkdir()
    work.mkdir()
    (home / ".env").write_text(
        "LIBRARY_API_HOST=127.0.0.1\n"
        "LIBRARY_API_PORT=8766\n"
        "LLM_DEFAULT_API_KEY=sk-fake\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(work)
    monkeypatch.setenv("LIBRARY_HOME", str(home))
    monkeypatch.delenv("LIBRARY_API_HOST", raising=False)
    monkeypatch.delenv("LIBRARY_API_PORT", raising=False)
    monkeypatch.delenv("LIBRARY_HTTP_SERVER", raising=False)
    get_settings.cache_clear()

    captured: dict[str, object] = {}

    def _fake_run(app: str, **kwargs) -> None:
        captured["app"] = app
        captured.update(kwargs)

    real_run = server_main.uvicorn.run
    try:
        server_main.uvicorn.run = _fake_run  # type: ignore[assignment]

        rc = server_main.main([])
    finally:
        server_main.uvicorn.run = real_run  # type: ignore[assignment]
        get_settings.cache_clear()

    assert rc == 0
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8766


@pytest.mark.asyncio
async def test_health_surface(monkeypatch: pytest.MonkeyPatch) -> None:
    from library.config import get_settings
    from library.main import health

    # AP-12: /health exposes status/version/storage_backend only — the
    # deployment-identity fields (git_sha/build_id/environment) are dropped.
    get_settings.cache_clear()
    try:
        storage_backend = get_settings().storage_backend
        payload = await health()
    finally:
        get_settings.cache_clear()

    assert payload == {
        "status": "ok",
        "version": __version__,
        "storage_backend": storage_backend,
    }
