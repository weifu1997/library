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
