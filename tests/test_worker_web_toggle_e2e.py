"""Web toggle for the background worker — live start/stop + persistence.

Regression for the silent "waiting forever" trap: `library serve` with
`WORKER_ENABLED=false` never starts a runner, so pending tasks pile up
with no warning. This locks in the Settings-page path:

  - `worker_enabled` is writable through the existing overlay PUT and
    persists across a cache invalidation / re-resolve.
  - `GET /settings/server` reports `worker_running` (live state) next to
    `worker_enabled` (configured intent), so the UI can tell "configured
    on but not actually running" apart.
  - PUT `{worker_enabled: false}` stops a live in-process runner.

Run:
    .venv/bin/python -m pytest tests/test_worker_web_toggle_e2e.py -q
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

_TEST_PARENT = Path(os.environ.get(
    "LIBRARY_TEST_TMP",
    str(Path(__file__).resolve().parent),
))
_TEST_PARENT.mkdir(parents=True, exist_ok=True)
_TEST_ROOT = _TEST_PARENT / f"_worker_web_toggle_e2e_{os.getpid()}_{uuid4().hex[:8]}"
_TEST_ROOT.mkdir(parents=True)
atexit = __import__("atexit")
atexit.register(lambda: shutil.rmtree(_TEST_ROOT, ignore_errors=True))
os.environ["LIBRARY_HOME"] = str(_TEST_ROOT)
os.environ["STORAGE_BACKEND"] = "local"
os.environ["WORKER_ENABLED"] = "false"
os.environ["WORKER_SCHEDULER_ENABLED"] = "false"
os.environ["AUTO_LIFECYCLE_ENABLED"] = "false"
os.environ["LLM_DEFAULT_API_KEY"] = "sk-web-toggle-key-XXXX"
os.environ["LLM_DEFAULT_MODEL"] = "toggle-test-model"
os.environ["LLM_DEFAULT_PROVIDER"] = "openai"
os.environ.pop("LLM_DEFAULT_BASE_URL", None)
# Stop Settings from reading a developer's local `.env` (see the sibling
# test_settings_routes_e2e module for the same dance).
from library.config import Settings as _Settings  # noqa: E402
from library.db.engine import get_engine  # noqa: E402
from library.db.models import Base  # noqa: E402

_Settings.model_config["env_file"] = None


async def _create_schema() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def test_overlay_accepts_worker_enabled() -> None:
    from library.services.config_overlay import validate_and_normalize

    assert validate_and_normalize({"worker_enabled": True}) == {"worker_enabled": True}
    assert validate_and_normalize({"worker_enabled": "false"}) == {
        "worker_enabled": False,
    }
    assert validate_and_normalize({"worker_enabled": None}) == {"worker_enabled": None}


async def test_worker_toggle_roundtrip() -> None:
    from library.config import get_settings
    from library.main import app as api_app
    from library.services import worker_lifecycle

    transport = httpx.ASGITransport(app=api_app)
    async with api_app.router.lifespan_context(api_app):
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            # Baseline: worker disabled, nothing running.
            r = await c.get("/v1/settings/server")
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["worker_enabled"] is False
            assert body["worker_running"] is False

            # Turn the worker on — persisted AND running live.
            r = await c.put(
                "/v1/settings/llm",
                json={"patch": {"worker_enabled": True}},
            )
            assert r.status_code == 200, r.text
            assert r.json().get("worker_error") is None
            assert get_settings().worker_enabled is True
            assert worker_lifecycle.is_running() is True

            r = await c.get("/v1/settings/server")
            body = r.json()
            assert body["worker_enabled"] is True
            assert body["worker_running"] is True

            # Turn it off — stopped live, persisted off.
            r = await c.put(
                "/v1/settings/llm",
                json={"patch": {"worker_enabled": False}},
            )
            assert r.status_code == 200, r.text
            assert get_settings().worker_enabled is False
            assert worker_lifecycle.is_running() is False

            r = await c.get("/v1/settings/server")
            body = r.json()
            assert body["worker_enabled"] is False
            assert body["worker_running"] is False

            # Overlay file reflects the last write.
            from library.services.config_overlay import read_overlay

            overlay = read_overlay(os.environ["LIBRARY_HOME"])
            assert overlay.get("worker_enabled") is False


async def test_worker_enabled_null_clear_follows_effective_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`worker_enabled: null` clears the override, so the LIVE state must
    follow the effective (.env/default) value — not `bool(None)`.

    Regression: with WORKER_ENABLED=true in env and a running runner, PUT
    `{worker_enabled: null}` used to derive desired from the patch value
    (bool(None) -> False) and STOP the runner even though clearing the
    override leaves the effective value true. The runner must keep running.
    """
    from library.config import get_settings
    from library.main import app as api_app
    from library.services import worker_lifecycle

    monkeypatch.setenv("WORKER_ENABLED", "true")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    transport = httpx.ASGITransport(app=api_app)
    async with api_app.router.lifespan_context(api_app):
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            # Bring the runner up and persist an explicit on.
            r = await c.put(
                "/v1/settings/llm",
                json={"patch": {"worker_enabled": True}},
            )
            assert r.status_code == 200, r.text
            assert worker_lifecycle.is_running() is True

            # Clear the override — effective value falls back to env true,
            # so the runner must stay live.
            r = await c.put(
                "/v1/settings/llm",
                json={"patch": {"worker_enabled": None}},
            )
            assert r.status_code == 200, r.text
            assert get_settings().worker_enabled is True
            assert worker_lifecycle.is_running() is True

            r = await c.get("/v1/settings/server")
            body = r.json()
            assert body["worker_enabled"] is True
            assert body["worker_running"] is True

            # Override key removed from the overlay file.
            from library.services.config_overlay import read_overlay

            overlay = read_overlay(os.environ["LIBRARY_HOME"])
            assert "worker_enabled" not in overlay

            # Clean up: leave the module with the runner stopped, so the
            # module-scoped teardown never joins a polling-loop task that is
            # bound to this (about-to-close) event loop.
            await worker_lifecycle.stop()
