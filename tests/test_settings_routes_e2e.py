"""GET/PUT /v1/settings — overlay round-trip without secret echo.

The Settings page in the GUI calls these to render server
status, list LLM profiles, and write back per-profile overrides. Two
behaviours we lock in here:

  1. api_keys are masked on the way out (PUT response too — never the
     raw secret).
  2. Writing an override and re-resolving the same profile reflects
     the new model/base_url, AND clears the LLM client cache so the
     next chat call uses the new config without a process restart.

Run:
    .venv/Scripts/python -m pytest tests/test_settings_routes_e2e.py -x -q
"""
from __future__ import annotations

import asyncio
import atexit
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

_TEST_PARENT = Path(os.environ.get(
    "LIBRARY_TEST_TMP",
    str(Path(__file__).resolve().parent),
))
_TEST_PARENT.mkdir(parents=True, exist_ok=True)
_TEST_ROOT = _TEST_PARENT / f"_settings_routes_e2e_{os.getpid()}_{uuid4().hex[:8]}"
_TEST_ROOT.mkdir(parents=True)
atexit.register(lambda: shutil.rmtree(_TEST_ROOT, ignore_errors=True))
os.environ["LIBRARY_HOME"] = str(_TEST_ROOT)
os.environ["STORAGE_BACKEND"] = "local"
os.environ["WORKER_ENABLED"] = "false"
os.environ["AUTO_LIFECYCLE_ENABLED"] = "false"
os.environ["LLM_DEFAULT_API_KEY"] = "sk-default-key-XXXX"
os.environ["LLM_DEFAULT_MODEL"] = "settings-default-model"
os.environ["LLM_DEFAULT_PROVIDER"] = "openai"
# Other test modules may have already exported LLM_DEFAULT_BASE_URL
# pointing at DeepSeek / a real provider — when a profile inherits the
# default api_key it'd then try to reach that host. Clear it.
os.environ.pop("LLM_DEFAULT_BASE_URL", None)
# A developer's local `.env` may pin per-profile fields like
# `LLM_INGEST_MODEL=deepseek-v4-flash`. The PUT handler does
# `get_settings.cache_clear(); llm_settings()` which re-reads `.env`
# via pydantic-settings, so popping env vars or scrubbing the cached
# instance can't survive that round-trip — we have to stop Settings
# from reading the file at all. Cut the env_file binding once at import
# time so every `Settings()` constructed during this test module sees
# only `os.environ`.
from library.config import Settings as _Settings  # noqa: E402

_Settings.model_config["env_file"] = None
# Also drop any LLM_<PROFILE>_* env vars the dev's .env exported into
# os.environ (python-dotenv may have loaded them via app startup),
# so the profiles really do fall back to LLM_DEFAULT_*.
for _opt in ("CHAT", "INGEST", "REFLECT", "VISION", "AUDIO"):
    for _field in ("PROVIDER", "API_KEY", "BASE_URL", "MODEL", "TPS"):
        os.environ.pop(f"LLM_{_opt}_{_field}", None)
    for _field in ("BACKUP_PROVIDER", "BACKUP_API_KEY", "BACKUP_BASE_URL", "BACKUP_MODEL"):
        os.environ.pop(f"LLM_{_opt}_{_field}", None)
for _var in (
    "LLM_DEFAULT_TPS",
    "LLM_DEFAULT_BACKUP_PROVIDER",
    "LLM_DEFAULT_BACKUP_API_KEY",
    "LLM_DEFAULT_BACKUP_BASE_URL",
    "LLM_DEFAULT_BACKUP_MODEL",
    "EMBEDDING_PROVIDER",
    "EMBEDDING_API_KEY",
    "EMBEDDING_BASE_URL",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSIONS",
    "EMBEDDING_TPS",
    "EMBEDDING_BATCH_SIZE",
    "SEMANTIC_INDEX_BACKEND",
    "SEMANTIC_RECALL_ENABLED",
    "SEMANTIC_RECALL_LIMIT",
    "RERANK_ENABLED",
    "RERANK_API_KEY",
    "RERANK_BASE_URL",
    "RERANK_MODEL",
    "RERANK_TPS",
    "RERANK_BATCH_SIZE",
    "RERANK_TOP_N",
    "RERANK_MAX_DOC_CHARS",
    "RERANK_CONCURRENCY",
    "EVIDENCE_SELECTION",
    "DOCUMENT_VISION_ENABLED",
    "DOCUMENT_VISION_MAX_IMAGES",
    "DOCUMENT_VISION_QUESTION_MAX_IMAGES",
    "DOCUMENT_VISION_MIN_IMAGE_BYTES",
    "DOCUMENT_VISION_MIN_IMAGE_DIMENSION",
    "DOCUMENT_VISION_MIN_IMAGE_AREA",
):
    os.environ.pop(_var, None)


def _scrub_optional_profiles(s) -> None:
    """Wipe vision/audio fields a developer's local .env may have set.

    Pydantic-settings reads `.env` during `Settings()` construction; env
    var pops alone can't defeat it. The "vision is opt-in / blank when
    unconfigured" contract this module locks in only holds if those
    fields are unset, so we null them on the cached instance after
    `get_settings()` returns."""
    for opt in ("vision", "audio"):
        for field in ("provider", "api_key", "base_url", "model"):
            object.__setattr__(s, f"llm_{opt}_{field}", None)
    # vision is the only opt-in profile with a backup; audio has no backup
    # fields (they'd be dead config, mirroring the audio profile itself).
    for field in ("backup_provider", "backup_api_key", "backup_base_url", "backup_model"):
        object.__setattr__(s, f"llm_vision_{field}", None)


def _ensure_test_env() -> None:
    """Re-assert env at the start of each test. Other test files set
    `LLM_DEFAULT_MODEL=fake-model` at import time; in a multi-file run
    those imports fire during collection and clobber ours."""
    os.environ["LIBRARY_HOME"] = str(_TEST_ROOT)
    os.environ["STORAGE_BACKEND"] = "local"
    os.environ["WORKER_ENABLED"] = "false"
    os.environ["AUTO_LIFECYCLE_ENABLED"] = "false"
    os.environ["LLM_DEFAULT_API_KEY"] = "sk-default-key-XXXX"
    os.environ["LLM_DEFAULT_MODEL"] = "settings-default-model"
    os.environ["LLM_DEFAULT_PROVIDER"] = "openai"
    os.environ.pop("LLM_DEFAULT_BASE_URL", None)
    os.environ.pop("LIBRARY_API_TOKEN", None)
    os.environ.pop("RELATION_BACKGROUND_VETTING_ENABLED", None)
    _TEST_ROOT.mkdir(parents=True, exist_ok=True)
    (_TEST_ROOT / ".env").write_text("", encoding="utf-8")
    os.chdir(_TEST_ROOT)
    _Settings.model_config["env_file"] = None
    for var in (
        "EMBEDDING_PROVIDER",
        "EMBEDDING_API_KEY",
        "EMBEDDING_BASE_URL",
        "EMBEDDING_MODEL",
        "EMBEDDING_DIMENSIONS",
        "EMBEDDING_TPS",
        "EMBEDDING_BATCH_SIZE",
        "SEMANTIC_INDEX_BACKEND",
        "SEMANTIC_RECALL_ENABLED",
        "SEMANTIC_RECALL_LIMIT",
        "RERANK_ENABLED",
        "RERANK_API_KEY",
        "RERANK_BASE_URL",
        "RERANK_MODEL",
        "RERANK_TPS",
        "RERANK_BATCH_SIZE",
        "RERANK_TOP_N",
        "RERANK_MAX_DOC_CHARS",
        "RERANK_CONCURRENCY",
        "EVIDENCE_SELECTION",
        "DOCUMENT_VISION_ENABLED",
        "DOCUMENT_VISION_MAX_IMAGES",
        "DOCUMENT_VISION_QUESTION_MAX_IMAGES",
        "DOCUMENT_VISION_MIN_IMAGE_BYTES",
        "DOCUMENT_VISION_MIN_IMAGE_DIMENSION",
        "DOCUMENT_VISION_MIN_IMAGE_AREA",
    ):
        os.environ.pop(var, None)
    # Backup (failover) fields must not leak from a dev .env either.
    for var in (
        "LLM_DEFAULT_BACKUP_PROVIDER",
        "LLM_DEFAULT_BACKUP_API_KEY",
        "LLM_DEFAULT_BACKUP_BASE_URL",
        "LLM_DEFAULT_BACKUP_MODEL",
    ):
        os.environ.pop(var, None)
    for opt in ("CHAT", "INGEST", "REFLECT", "VISION", "AUDIO"):
        for field in (
            "BACKUP_PROVIDER",
            "BACKUP_API_KEY",
            "BACKUP_BASE_URL",
            "BACKUP_MODEL",
        ):
            os.environ.pop(f"LLM_{opt}_{field}", None)
    get_settings.cache_clear()  # type: ignore[attr-defined]
    _scrub_optional_profiles(get_settings())
    # Direct-write reset avoids unlink/rename, which restricted Windows
    # sandboxes may deny. "{}" reads the same as a missing overlay.
    (_TEST_ROOT / "config_overlay.json").write_text("{}", encoding="utf-8")

import httpx
from httpx import ASGITransport

from library.config import get_settings
get_settings.cache_clear()  # type: ignore[attr-defined]

from library.main import app


@asynccontextmanager
async def _settings_routes_only_lifespan(_app):
    """Settings endpoints do not touch the database.

    The full app lifespan initializes sqlite with WAL, which is covered by
    dedicated DB tests and can fail in restricted filesystems. Keep this
    route test focused on settings payloads and overlay writes.
    """
    yield


app.router.lifespan_context = _settings_routes_only_lifespan


async def _create_schema() -> None:
    return None


async def test_optional_bearer_auth() -> None:
    _ensure_test_env()
    os.environ["LIBRARY_API_TOKEN"] = "test-token"
    get_settings.cache_clear()  # type: ignore[attr-defined]
    transport = ASGITransport(app=app)
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
                r = await c.get("/health")
                assert r.status_code == 200, r.text

                r = await c.get("/v1/settings/server")
                assert r.status_code == 401, r.text

                r = await c.get(
                    "/v1/settings/server",
                    headers={"Authorization": "Bearer wrong"},
                )
                assert r.status_code == 401, r.text

                r = await c.get(
                    "/v1/settings/server",
                    headers={"Authorization": "Bearer test-token"},
                )
                assert r.status_code == 200, r.text
        print("[0] optional bearer auth gates v1 routes and exempts /health")
    finally:
        os.environ.pop("LIBRARY_API_TOKEN", None)
        get_settings.cache_clear()  # type: ignore[attr-defined]


async def test_server_snapshot_no_secrets() -> None:
    _ensure_test_env()
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.get("/v1/settings/server")
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["storage_backend"] == "local"
            assert body["worker_enabled"] is False
            assert body["runtime_schema_bootstrap_enabled"] is True
            assert body["auto_lifecycle_enabled"] is False
            assert body["maintenance_daily_token_budget"] >= 0
            assert body["relation_background_vetting_enabled"] is False
            assert body["default_on_conflict"] in ("rename", "error", "skip")
            assert body["worker_batch_size"] >= 1
            assert body["task_retention_days"] >= 0
            assert body["llm_ingest_concurrency"] >= 1
            assert body["llm_default_tps"] >= 1
            assert body["agent_turn_timeout_seconds"] >= 0
            assert body["embedding_api_key_set"] is False
            assert body["embedding_provider"] in ("dashscope", "openai-compatible")
            assert body["embedding_tps"] >= 1
            assert 1 <= body["embedding_batch_size"] <= 10
            assert body["semantic_recall_enabled"] is False
            assert body["semantic_recall_configured"] is False
            assert body["rerank_enabled"] is False
            assert body["rerank_api_key_set"] is False
            assert body["rerank_configured"] is False
            assert body["rerank_tps"] >= 1
            assert body["rerank_batch_size"] >= 1
            assert body["evidence_selection"] in ("quota", "rerank")
            assert body["document_vision_enabled"] is True
            # Sanity: no secret keys / DSN-shaped fields snuck in.
            for k, v in body.items():
                if isinstance(v, str):
                    assert "sk-" not in v, f"{k}={v!r}"
                    assert "postgresql" not in v, f"{k}={v!r}"
            print("[1] /v1/settings/server: no secret leakage")


async def test_llm_get_masks_keys() -> None:
    _ensure_test_env()
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.get("/v1/settings/llm")
            assert r.status_code == 200, r.text
            body = r.json()
            assert "chat" in body["profiles"]
            chat = body["profiles"]["chat"]
            # Default api_key inherited; should be masked, not raw.
            assert chat["api_key_set"] is True
            assert chat["api_key"] != "sk-default-key-XXXX"
            assert "***" in (chat["api_key"] or "")
            # vision is opt-in: with no explicit override it should
            # read as blank, NOT fall back to the default key. The
            # Settings UI relies on this to show "(unset)" instead of
            # pretending the user inherited a usable config.
            vision = body["profiles"]["vision"]
            assert vision["api_key_set"] is False
            assert vision["api_key"] is None
            assert vision["model"] is None
            assert vision["provider"] is None
            # No backup (failover) configured anywhere → every backup reads null.
            assert body["defaults"]["backup"] is None
            assert body["profiles"]["chat"]["backup"] is None
            assert body["profiles"]["vision"]["backup"] is None
            # audio is hidden from the GUI surface until a transcription
            # pipeline lands — no `audio` key in the response.
            assert "audio" not in body["profiles"]
            print("[2] /v1/settings/llm: api_keys masked, vision blank, audio hidden")


async def test_put_writes_overlay_and_invalidates_cache() -> None:
    _ensure_test_env()
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.put(
                "/v1/settings/llm",
                json={
                    "patch": {
                        "llm_chat_model": "gpt-4o-2026",
                        "llm_chat_base_url": "https://example.test/v1",
                        "llm_chat_tps": 7,
                        "agent_final_answer_continue_turns": 5,
                        "agent_final_answer_max_chars": 180000,
                        "agent_turn_timeout_seconds": 2400,
                        "worker_batch_size": 3,
                        "llm_ingest_concurrency": 6,
                        "maintenance_daily_token_budget": 123456,
                        "relation_background_vetting_enabled": True,
                        "embedding_provider": "dashscope",
                        "embedding_api_key": "emb-secret-XXXX",
                        "embedding_base_url": "https://emb.example.test/v1",
                        "embedding_model": "embed-model",
                        "embedding_dimensions": 512,
                        "embedding_tps": 9,
                        "embedding_batch_size": 8,
                        "semantic_index_backend": "file",
                        "semantic_recall_enabled": True,
                        "semantic_recall_limit": 42,
                        "rerank_enabled": True,
                        "rerank_api_key": "rerank-secret-XXXX",
                        "rerank_base_url": "https://rerank.example.test/v1",
                        "rerank_model": "rerank-model",
                        "rerank_tps": 3,
                        "rerank_batch_size": 24,
                        "rerank_top_n": 12,
                        "rerank_max_doc_chars": 1600,
                        "rerank_concurrency": 4,
                        "evidence_selection": "rerank",
                        "document_vision_enabled": False,
                        "document_vision_max_images": 6,
                        "document_vision_question_max_images": 2,
                        "document_vision_min_image_bytes": 1024,
                        "document_vision_min_image_dimension": 16,
                        "document_vision_min_image_area": 512,
                    },
                },
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["profiles"]["chat"]["model"] == "gpt-4o-2026"
            assert body["profiles"]["chat"]["base_url"] == "https://example.test/v1"
            assert body["profiles"]["chat"]["tps"] == 7
            assert body["overlay"]["agent_final_answer_continue_turns"] == 5
            assert body["overlay"]["agent_final_answer_max_chars"] == 180000
            assert body["overlay"]["agent_turn_timeout_seconds"] == 2400.0
            assert body["overlay"]["worker_batch_size"] == 3
            assert body["overlay"]["llm_ingest_concurrency"] == 6
            assert body["overlay"]["maintenance_daily_token_budget"] == 123456
            assert body["overlay"]["relation_background_vetting_enabled"] is True
            assert body["overlay"]["embedding_provider"] == "dashscope"
            assert body["overlay"]["embedding_api_key"] != "emb-secret-XXXX"
            assert "***" in body["overlay"]["embedding_api_key"]
            assert body["overlay"]["embedding_model"] == "embed-model"
            assert body["overlay"]["embedding_tps"] == 9
            assert body["overlay"]["semantic_recall_enabled"] is True
            assert body["overlay"]["semantic_recall_limit"] == 42
            assert body["overlay"]["rerank_enabled"] is True
            assert body["overlay"]["rerank_api_key"] != "rerank-secret-XXXX"
            assert "***" in body["overlay"]["rerank_api_key"]
            assert body["overlay"]["rerank_model"] == "rerank-model"
            assert body["overlay"]["rerank_tps"] == 3
            assert body["overlay"]["rerank_batch_size"] == 24
            assert body["overlay"]["evidence_selection"] == "rerank"
            assert body["overlay"]["document_vision_enabled"] is False
            # Other profiles are not overwritten by the chat override.
            assert body["profiles"]["ingest"]["model"] != "gpt-4o-2026"

            overlay_file = _TEST_ROOT / "config_overlay.json"
            assert overlay_file.exists(), "overlay file not created"
            disk = overlay_file.read_text(encoding="utf-8")
            assert "gpt-4o-2026" in disk
            assert "sk-default-key" not in disk, "PUT must not write defaults"

            # PUT response must not echo the raw key either.
            assert "sk-default-key-XXXX" not in r.text
            assert "emb-secret-XXXX" not in r.text
            assert "rerank-secret-XXXX" not in r.text

            # And get_settings() now sees the new model.
            s = get_settings()
            assert s.llm_chat_model == "gpt-4o-2026"
            assert s.llm_chat_tps == 7
            assert s.agent_final_answer_continue_turns == 5
            assert s.agent_final_answer_max_chars == 180000
            assert s.agent_turn_timeout_seconds == 2400.0
            assert s.worker_batch_size == 3
            assert s.llm_ingest_concurrency == 6
            assert s.maintenance_daily_token_budget == 123456
            assert s.relation_background_vetting_enabled is True
            assert s.embedding_provider == "dashscope"
            assert s.embedding_api_key == "emb-secret-XXXX"
            assert s.embedding_base_url == "https://emb.example.test/v1"
            assert s.embedding_model == "embed-model"
            assert s.embedding_dimensions == 512
            assert s.embedding_tps == 9
            assert s.embedding_batch_size == 8
            assert s.semantic_index_backend == "file"
            assert s.semantic_recall_enabled is True
            assert s.semantic_recall_limit == 42
            assert s.rerank_enabled is True
            assert s.rerank_api_key == "rerank-secret-XXXX"
            assert s.rerank_base_url == "https://rerank.example.test/v1"
            assert s.rerank_model == "rerank-model"
            assert s.rerank_tps == 3
            assert s.rerank_batch_size == 24
            assert s.rerank_top_n == 12
            assert s.rerank_max_doc_chars == 1600
            assert s.rerank_concurrency == 4
            assert s.evidence_selection == "rerank"
            assert s.document_vision_enabled is False
            assert s.document_vision_max_images == 6
            assert s.document_vision_question_max_images == 2
            assert s.document_vision_min_image_bytes == 1024
            assert s.document_vision_min_image_dimension == 16
            assert s.document_vision_min_image_area == 512

            r = await c.get("/v1/settings/server")
            assert r.status_code == 200, r.text
            server = r.json()
            assert server["embedding_api_key_set"] is True
            assert server["semantic_recall_configured"] is True
            assert server["rerank_api_key_set"] is True
            assert server["rerank_configured"] is True
            assert "emb-secret-XXXX" not in r.text
            assert "rerank-secret-XXXX" not in r.text
            print("[3] PUT /v1/settings/llm: overlay written, cache invalidated")


async def test_put_clear_with_none() -> None:
    """Setting an override to null removes it from the overlay."""
    _ensure_test_env()
    # First, plant the override that test 4 will clear.
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.put(
                "/v1/settings/llm",
                json={
                    "patch": {
                        "llm_chat_model": "gpt-4o-2026",
                        "llm_chat_base_url": "https://example.test/v1",
                    },
                },
            )
            assert r.status_code == 200, r.text

    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.put(
                "/v1/settings/llm",
                json={"patch": {"llm_chat_model": None}},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["profiles"]["chat"]["model"] == "settings-default-model"
            overlay_file = _TEST_ROOT / "config_overlay.json"
            disk = overlay_file.read_text(encoding="utf-8")
            assert "llm_chat_model" not in disk
            # The other override we set in test 3 stays.
            assert "https://example.test/v1" in disk
            print("[4] PUT with null clears one override, leaves others")


async def test_put_rejects_unknown_field() -> None:
    _ensure_test_env()
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.put(
                "/v1/settings/llm",
                json={"patch": {"db_backend": "postgres"}},
            )
            assert r.status_code == 422, r.text
            print("[5] PUT rejects unknown field with 422")


async def test_put_rejects_bad_provider() -> None:
    _ensure_test_env()
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.put(
                "/v1/settings/llm",
                json={"patch": {"llm_chat_provider": "groq-typo"}},
            )
            assert r.status_code == 422, r.text
            print("[6] PUT rejects unknown provider with 422")


async def test_put_merge_refuses_unreadable_overlay() -> None:
    """SET-M1: truncated overlay must not be replaced by a one-key merge."""
    _ensure_test_env()
    overlay_file = _TEST_ROOT / "config_overlay.json"
    overlay_file.write_text('{"llm_chat_tps": 7, "llm_chat_model":', encoding="utf-8")
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.put(
                "/v1/settings/llm",
                json={"patch": {"llm_default_tps": 3}},
            )
            assert r.status_code == 422, r.text
            assert "unreadable" in r.text.lower()
    disk = overlay_file.read_text(encoding="utf-8")
    assert "llm_default_tps" not in disk
    assert disk.startswith('{"llm_chat_tps"')
    print("[6b] PUT merge refuses unreadable overlay")


async def test_put_rejects_masked_api_key() -> None:
    """SET-M2: GET mask must not persist as the real key."""
    _ensure_test_env()
    overlay_file = _TEST_ROOT / "config_overlay.json"
    overlay_file.write_text(
        '{"llm_default_api_key": "sk-real-secret-XXXX"}',
        encoding="utf-8",
    )
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.put(
                "/v1/settings/llm",
                json={"patch": {"llm_default_api_key": "sk-***XX"}},
            )
            assert r.status_code == 422, r.text
            assert "masked" in r.text.lower() or "***" in r.text
    disk = overlay_file.read_text(encoding="utf-8")
    assert "sk-real-secret-XXXX" in disk
    assert "sk-***XX" not in disk
    print("[6c] PUT rejects masked API key")


async def test_put_backup_round_trip() -> None:
    """Backup fields persist to the overlay, mask on the way out, and
    resolve per-profile (chat inherits the default's backup provider/key;
    vision reflects only its explicit raw fields)."""
    _ensure_test_env()
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.put(
                "/v1/settings/llm",
                json={
                    "patch": {
                        "llm_default_backup_provider": "anthropic",
                        "llm_default_backup_api_key": "sk-backup-secret-XXXX",
                        "llm_default_backup_model": "claude-backup",
                        "llm_chat_backup_model": "chat-backup-model",
                        "llm_vision_backup_model": "vis-backup-model",
                    },
                },
            )
            assert r.status_code == 200, r.text
            body = r.json()
            # Defaults backup resolves + masks.
            dflt = body["defaults"]["backup"]
            assert dflt is not None
            assert dflt["provider"] == "anthropic"
            assert dflt["model"] == "claude-backup"
            assert dflt["api_key_set"] is True
            assert dflt["api_key"] != "sk-backup-secret-XXXX"
            assert "***" in (dflt["api_key"] or "")
            # chat inherits the default backup provider + key, overrides model.
            chat = body["profiles"]["chat"]["backup"]
            assert chat is not None
            assert chat["provider"] == "anthropic"
            assert chat["model"] == "chat-backup-model"
            assert chat["api_key_set"] is True
            # vision reflects only its explicit raw fields (provider unset → null).
            vis = body["profiles"]["vision"]["backup"]
            assert vis is not None
            assert vis["model"] == "vis-backup-model"
            assert vis["provider"] is None
            assert vis["api_key_set"] is False
            # PUT response must not echo the raw backup key.
            assert "sk-backup-secret-XXXX" not in r.text

            overlay_file = _TEST_ROOT / "config_overlay.json"
            disk = overlay_file.read_text(encoding="utf-8")
            assert "llm_default_backup_model" in disk
            assert "llm_default_backup_provider" in disk
            assert "llm_chat_backup_model" in disk
            assert "llm_vision_backup_model" in disk

            # get_settings() now sees the merged backup fields.
            s = get_settings()
            assert s.llm_default_backup_provider == "anthropic"
            assert s.llm_default_backup_api_key == "sk-backup-secret-XXXX"
            assert s.llm_default_backup_model == "claude-backup"
            assert s.llm_chat_backup_model == "chat-backup-model"
            assert s.llm_vision_backup_model == "vis-backup-model"

            # A fresh GET reflects the same masked payload.
            r = await c.get("/v1/settings/llm")
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["defaults"]["backup"]["model"] == "claude-backup"
            assert body["profiles"]["chat"]["backup"]["model"] == "chat-backup-model"
            assert body["profiles"]["vision"]["backup"]["model"] == "vis-backup-model"
            assert "sk-backup-secret-XXXX" not in r.text
            print("[6b] PUT/GET backup: masked, inherited, raw-vision, persisted")


async def test_put_rejects_bad_backup_provider() -> None:
    """The generic `_provider` whitelist covers backup providers too."""
    _ensure_test_env()
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.put(
                "/v1/settings/llm",
                json={"patch": {"llm_default_backup_provider": "groq-typo"}},
            )
            assert r.status_code == 422, r.text
            assert "llm_default_backup_provider" in r.text
            print("[6c] PUT rejects unknown backup provider with 422")


async def test_put_backup_clear_with_null() -> None:
    """Nulling the backup model removes it from the overlay, so the resolved
    backup falls back to unconfigured (None) again."""
    _ensure_test_env()
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.put(
                "/v1/settings/llm",
                json={"patch": {"llm_default_backup_model": "claude-backup"}},
            )
            assert r.status_code == 200, r.text

            r = await c.put(
                "/v1/settings/llm",
                json={"patch": {"llm_default_backup_model": None}},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["defaults"]["backup"] is None
            overlay_file = _TEST_ROOT / "config_overlay.json"
            disk = overlay_file.read_text(encoding="utf-8")
            assert "llm_default_backup_model" not in disk
            print("[6d] PUT null clears the backup override")


async def test_put_rejects_embedding_batch_above_ten() -> None:
    _ensure_test_env()
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.put(
                "/v1/settings/llm",
                json={"patch": {"embedding_batch_size": 11}},
            )
            assert r.status_code == 422, r.text
            assert "embedding_batch_size" in r.text
            print("[7] PUT rejects embedding_batch_size above 10")


async def test_llm_test_profile_default_unconfigured() -> None:
    """`?profile=default` short-circuits with `{ok: None, configured: False}`
    when the default profile has no key or model — no LLM network call, and
    embedding/rerank are skipped entirely."""
    _ensure_test_env()
    # Simulate a fresh install: no default key or model configured.
    os.environ.pop("LLM_DEFAULT_API_KEY", None)
    os.environ.pop("LLM_DEFAULT_MODEL", None)
    os.environ.pop("LLM_DEFAULT_PROVIDER", None)
    get_settings.cache_clear()  # type: ignore[attr-defined]
    try:
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
                r = await c.post("/v1/settings/llm/test?profile=default")
                assert r.status_code == 200, r.text
                body = r.json()
                assert list(body["profiles"].keys()) == ["default"]
                assert body["profiles"]["default"] == {
                    "ok": None,
                    "configured": False,
                }
                # The profile=default path must not probe embedding/rerank.
                assert "embedding" not in body
                assert "rerank" not in body
        print("[8] test?profile=default short-circuits when unconfigured")
    finally:
        _ensure_test_env()


async def test_llm_test_profile_default_returns_verdict() -> None:
    """With a configured default, `?profile=default` runs exactly one probe
    and returns its verdict verbatim under `profiles.default`."""
    import library.api.routes_settings as rs

    _ensure_test_env()
    calls: list[str] = []

    async def _fake_probe(profile: str) -> dict[str, Any]:
        calls.append(profile)
        return {
            "ok": True,
            "model": "settings-default-model",
            "provider": "openai",
            "duration_ms": 12.3,
        }

    original = rs._probe_llm_profile
    rs._probe_llm_profile = _fake_probe
    try:
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
                r = await c.post("/v1/settings/llm/test?profile=default")
                assert r.status_code == 200, r.text
                body = r.json()
                assert calls == ["default"], f"expected one default probe, got {calls}"
                verdict = body["profiles"]["default"]
                assert verdict["ok"] is True
                assert verdict["model"] == "settings-default-model"
                assert verdict["provider"] == "openai"
                assert "embedding" not in body
                assert "rerank" not in body
        print("[9] test?profile=default returns the default verdict")
    finally:
        rs._probe_llm_profile = original
        _ensure_test_env()


async def test_llm_models_endpoint_lists_models() -> None:
    """POST /v1/settings/llm/models returns the provider's model list. The
    network call is stubbed; profile resolution and form-override layering
    run for real, and the api_key never leaks into the response."""
    import library.api.routes_settings as rs

    _ensure_test_env()
    seen: list[tuple[str, str | None, str]] = []

    async def _fake_list_models(
        provider: str, base_url: str | None, api_key: str,
    ) -> dict[str, Any]:
        seen.append((provider, base_url, api_key))
        return {
            "ok": True,
            "models": [{"id": "gpt-4o", "display_name": None}],
            "provider": provider,
            "base_url": base_url,
            "duration_ms": 1.0,
        }

    original = rs._list_llm_models
    rs._list_llm_models = _fake_list_models
    try:
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
                r = await c.post(
                    "/v1/settings/llm/models",
                    json={
                        "profile": "default",
                        "provider": "openai",
                        "base_url": "https://api.openai.com/v1",
                    },
                )
                assert r.status_code == 200, r.text
                body = r.json()
                assert body["ok"] is True
                assert body["models"][0]["id"] == "gpt-4o"
                # The form override for base_url won; api_key fell back to the
                # resolved (saved) key.
                assert seen == [
                    ("openai", "https://api.openai.com/v1", "sk-default-key-XXXX"),
                ]
                assert "sk-default-key-XXXX" not in r.text

                # A masked placeholder ("sk-***XXXX") is the stored key
                # rendered for display, never a real credential — it must not
                # override the resolved key (the bug that 401'd OneHub).
                seen.clear()
                r = await c.post(
                    "/v1/settings/llm/models",
                    json={
                        "profile": "default",
                        "provider": "openai",
                        "base_url": "https://api.openai.com/v1",
                        "api_key": "sk-***XXXX",
                    },
                )
                assert r.status_code == 200, r.text
                assert seen == [
                    ("openai", "https://api.openai.com/v1", "sk-default-key-XXXX"),
                ]

                # Backup fetch with live form overrides works even though no
                # backup is persisted (_ensure_test_env scrubs backup env):
                # the endpoint lists against the form values instead of
                # short-circuiting to "backup model not configured".
                seen.clear()
                r = await c.post(
                    "/v1/settings/llm/models",
                    json={
                        "profile": "default",
                        "backup": True,
                        "provider": "openai",
                        "base_url": "https://api.openai.com/v1",
                        "api_key": "sk-live-backup-key",
                    },
                )
                assert r.status_code == 200, r.text
                assert seen == [
                    ("openai", "https://api.openai.com/v1", "sk-live-backup-key"),
                ]
        print("[10] POST /llm/models returns the provider model list")
    finally:
        rs._list_llm_models = original
        _ensure_test_env()


async def test_llm_models_validation_and_unconfigured_backup() -> None:
    """Unknown profile → 422; unsupported provider → 422; an unconfigured
    backup short-circuits to ok:false. None of these needs a network call."""
    _ensure_test_env()
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.post(
                "/v1/settings/llm/models",
                json={"profile": "nope"},
            )
            assert r.status_code == 422, r.text

            r = await c.post(
                "/v1/settings/llm/models",
                json={"profile": "default", "provider": "foo"},
            )
            assert r.status_code == 422, r.text

            # _ensure_test_env scrubs LLM_DEFAULT_BACKUP_*, so the default
            # backup is unconfigured and the fetch short-circuits.
            r = await c.post(
                "/v1/settings/llm/models",
                json={"profile": "default", "backup": True},
            )
            assert r.status_code == 200, r.text
            assert r.json()["ok"] is False
            assert r.json()["error"] == "backup model not configured"
    print("[11] POST /llm/models validates profile/provider and short-circuits unconfigured backup")


async def main() -> None:
    await _create_schema()
    await test_server_snapshot_no_secrets()
    await test_llm_get_masks_keys()
    await test_put_writes_overlay_and_invalidates_cache()
    await test_put_clear_with_none()
    await test_put_rejects_unknown_field()
    await test_put_rejects_bad_provider()
    await test_put_merge_refuses_unreadable_overlay()
    await test_put_rejects_masked_api_key()
    await test_put_backup_round_trip()
    await test_put_rejects_bad_backup_provider()
    await test_put_backup_clear_with_null()
    await test_put_rejects_embedding_batch_above_ten()
    await test_llm_test_profile_default_unconfigured()
    await test_llm_test_profile_default_returns_verdict()
    await test_llm_models_endpoint_lists_models()
    await test_llm_models_validation_and_unconfigured_backup()
    print("\nALL SETTINGS-ROUTES TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
