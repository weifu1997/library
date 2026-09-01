from __future__ import annotations

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from library.semantic.index import _resume_state
from library.tasks.handlers import rebuild_semantic_index as handler_module


def test_resume_state_is_bound_to_embedding_configuration(tmp_path) -> None:
    metadata = tmp_path / "entries.jsonl.tmp"
    vectors = tmp_path / "vectors.f32.tmp"
    rows = [
        {
            "record_id": f"entry-{index}",
            "text_hash": str(index),
            "embedding_provider": "openai-compatible",
            "embedding_model": "embedding-model",
            "embedding_dimensions": 3,
        }
        for index in range(2)
    ]
    metadata.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    vectors.write_bytes(b"\x00" * (2 * 3 * 4))

    accepted = _resume_state(
        metadata,
        vectors,
        requested_ids=None,
        resume=True,
        expected_provider="openai-compatible",
        expected_model="embedding-model",
        expected_dimensions=3,
    )
    rejected = _resume_state(
        metadata,
        vectors,
        requested_ids=None,
        resume=True,
        expected_provider="openai-compatible",
        expected_model="different-model",
        expected_dimensions=3,
    )

    assert accepted == (2, 3, {"entry-0", "entry-1"})
    assert rejected == (0, 0, set())


def test_resume_state_self_heals_truncated_jsonl(tmp_path) -> None:
    metadata = tmp_path / "entries.jsonl.tmp"
    vectors = tmp_path / "vectors.f32.tmp"
    row = {
        "record_id": "entry-0",
        "text_hash": "0",
        "embedding_provider": "openai-compatible",
        "embedding_model": "embedding-model",
        "embedding_dimensions": 3,
    }
    metadata.write_text(json.dumps(row)[:20], encoding="utf-8")
    vectors.write_bytes(b"\x00" * 12)

    assert _resume_state(
        metadata,
        vectors,
        requested_ids=None,
        resume=True,
        expected_provider="openai-compatible",
        expected_model="embedding-model",
        expected_dimensions=3,
    ) == (0, 0, set())


@pytest.mark.asyncio
async def test_background_rebuild_uses_task_scoped_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeSession:
        async def commit(self) -> None:
            return None

    @asynccontextmanager
    async def fake_session_scope():
        yield FakeSession()

    async def fake_build(_session, **kwargs):  # noqa: ANN001, ANN003
        captured.update(kwargs)
        return SimpleNamespace(
            index_name="default",
            index_dir="index",
            entries_indexed=2,
            model="embedding-model",
            dimensions=3,
            elapsed_ms=10,
            total_tokens=20,
        )

    async def fake_audit_append(*_args, **_kwargs):  # noqa: ANN002, ANN003
        return None

    monkeypatch.setattr(handler_module, "session_scope", fake_session_scope)
    monkeypatch.setattr(handler_module, "build_semantic_index", fake_build)
    monkeypatch.setattr(
        handler_module.audit_events_repo,
        "append",
        fake_audit_append,
    )

    await handler_module.handle_rebuild_semantic_index({
        "_task_id": "task-123",
        "index_name": "default",
    })

    assert captured["resume"] is True
    assert captured["resume_key"] == "task-123"


@pytest.mark.asyncio
async def test_build_restarts_when_resume_ids_have_vanished(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from library.config import get_settings
    from library.semantic import index as idx
    from library.semantic.index import SemanticIndexBuildResult

    monkeypatch.setenv("LIBRARY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "3")
    monkeypatch.setenv("SEMANTIC_INDEX_BACKEND", "file")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    try:
        settings = get_settings()
        out_dir = idx.semantic_index_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        row = {
            "record_id": "gone-record",
            "entry_id": "gone-entry",
            "text_hash": "x",
            "embedding_provider": settings.embedding_provider,
            "embedding_model": settings.embedding_model,
            "embedding_dimensions": 3,
        }
        (out_dir / "entries.jsonl.tmp").write_text(
            json.dumps(row) + "\n", encoding="utf-8",
        )
        (out_dir / "vectors.f32.tmp").write_bytes(b"\x00" * 12)

        accepted = _resume_state(
            out_dir / "entries.jsonl.tmp",
            out_dir / "vectors.f32.tmp",
            requested_ids=None,
            resume=True,
            expected_provider=settings.embedding_provider,
            expected_model=settings.embedding_model,
            expected_dimensions=3,
        )
        assert accepted[2] == {"gone-record"}

        async def empty_pages(*_args, **_kwargs):  # noqa: ANN002, ANN003
            if False:
                yield []

        restarts: list[bool] = []

        async def fake_restart(session, **kwargs):  # noqa: ANN001, ANN003
            restarts.append(bool(kwargs.get("resume")))
            return SemanticIndexBuildResult(
                index_name="default",
                index_dir=out_dir,
                entries_indexed=0,
                dimensions=0,
                model=settings.embedding_model,
                elapsed_ms=0,
                total_tokens=0,
                skipped_reason="restarted",
            )

        monkeypatch.setattr(idx, "_iter_semantic_input_pages", empty_pages)
        real_build = idx._build_semantic_index
        monkeypatch.setattr(idx, "_build_semantic_index", fake_restart)

        result = await real_build(
            SimpleNamespace(),
            resume=True,
            client=SimpleNamespace(),
        )
        assert restarts == [False]
        assert result.skipped_reason == "restarted"
        assert not (out_dir / "entries.jsonl.tmp").exists()
        assert not (out_dir / "vectors.f32.tmp").exists()
    finally:
        get_settings.cache_clear()  # type: ignore[attr-defined]
