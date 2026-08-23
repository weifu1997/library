from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from library.db.bootstrap import bootstrap_schema_sync
from library.db.models import File, FileEntry
from library.db.models.tasks import Task
from library.config import Settings
from library.semantic.embeddings import EmbeddingConfigError, get_embedding_client
from library.semantic.embeddings import EmbeddingResult
from library.semantic.index import (
    SQLITE_VEC_INDEX_FILENAME,
    best_semantic_sections,
    build_semantic_index,
    refresh_semantic_index_for_file,
    search_semantic_index,
    search_semantic_index_many,
    semantic_entry_rows,
    semantic_index_dir,
    semantic_index_status,
    sqlite_vec_available,
)
from library.agent.tools.recall_knowledge import load_rerank_documents_by_entry_id
from library.semantic.rerank import _parse_rerank_hits
from library.utils.ids import new_id
from library.tasks.kinds import KIND_REBUILD_SEMANTIC_INDEX


@dataclass
class _FakeEmbeddingClient:
    async def embed(self, texts: list[str], *, text_type: str) -> EmbeddingResult:
        vectors = []
        for text in texts:
            haystack = text.casefold()
            if "rollback" in haystack and "name:" not in haystack:
                vectors.append([0.0, 0.0, 1.0])
            elif (
                "cooking" in haystack or "sourdough" in haystack
            ) and ("name:" not in haystack or "raft" not in haystack):
                vectors.append([0.0, 1.0, 0.0])
            elif "raft" in haystack or "leader" in haystack:
                vectors.append([1.0, 0.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0])
        return EmbeddingResult(vectors=vectors, total_tokens=len(texts))


@dataclass
class _RejectEmbeddingClient:
    calls: int = 0

    async def embed(self, texts: list[str], *, text_type: str) -> EmbeddingResult:
        self.calls += 1
        raise AssertionError(f"embedding provider should not be called for {texts!r}")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_semantic_index_builds_and_searches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIBRARY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "3")
    if sqlite_vec_available():
        monkeypatch.setenv("SEMANTIC_INDEX_BACKEND", "sqlite-vec")
    from library.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'semantic.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = _now()
    raft_file_id = new_id()
    raft_entry_id = new_id()
    cooking_file_id = new_id()
    cooking_entry_id = new_id()

    try:
        async with engine.begin() as conn:
            await conn.run_sync(bootstrap_schema_sync)

        async with factory() as session:
            session.add(File(
                id=raft_file_id,
                storage_key="00/aa/raft",
                sha256="a" * 64,
                size_bytes=10,
                mime_type="text/plain",
                original_ext=".txt",
                kind="text",
                summary="Raft consensus uses leader election.",
                description={"sections": []},
                extra="",
                ingest_status="done",
                ingested_at=now,
                deleted_at=None,
                created_at=now,
                updated_at=now,
            ))
            session.add(FileEntry(
                id=raft_entry_id,
                folder_id=None,
                file_id=raft_file_id,
                display_name="doc-a.txt",
                lifecycle="active",
                catalog_id=None,
                extra="",
                deleted_at=None,
                purge_after=None,
                created_at=now,
                updated_at=now,
            ))
            session.add(File(
                id=cooking_file_id,
                storage_key="00/aa/cooking",
                sha256="b" * 64,
                size_bytes=10,
                mime_type="text/plain",
                original_ext=".txt",
                kind="text",
                summary="Cooking notes for sourdough bread.",
                description={"sections": []},
                extra="",
                ingest_status="done",
                ingested_at=now,
                deleted_at=None,
                created_at=now,
                updated_at=now,
            ))
            session.add(FileEntry(
                id=cooking_entry_id,
                folder_id=None,
                file_id=cooking_file_id,
                display_name="doc-b.txt",
                lifecycle="active",
                catalog_id=None,
                extra="",
                deleted_at=None,
                purge_after=None,
                created_at=now,
                updated_at=now,
            ))
            await session.commit()

        async with factory() as session:
            result = await build_semantic_index(
                session,
                client=_FakeEmbeddingClient(),
                progress_every=0,
                page_size=1,
            )

        assert result.entries_indexed == 2
        assert result.dimensions == 3
        if sqlite_vec_available():
            assert (semantic_index_dir() / SQLITE_VEC_INDEX_FILENAME).exists()

        hits = await search_semantic_index(
            "leader election",
            limit=2,
            client=_FakeEmbeddingClient(),
        )

        assert [hit.entry_id for hit in hits] == [raft_entry_id, cooking_entry_id]

        many = await search_semantic_index_many(
            ["leader election", "sourdough starter"],
            limit=1,
            client=_FakeEmbeddingClient(),
        )
        assert [[hit.entry_id for hit in group] for group in many] == [
            [raft_entry_id],
            [cooking_entry_id],
        ]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_section_vectors_preserve_match_for_recall_rerank_and_refresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIBRARY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SEMANTIC_RECALL_ENABLED", "true")
    monkeypatch.setenv("EMBEDDING_API_KEY", "fake-key")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "3")
    monkeypatch.setenv("SEMANTIC_INDEX_BACKEND", "file")
    from library.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sections.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = _now()
    file_id = new_id()
    entry_id = new_id()

    try:
        async with engine.begin() as conn:
            await conn.run_sync(bootstrap_schema_sync)
        async with factory() as session:
            session.add(File(
                id=file_id,
                storage_key="00/aa/handbook",
                sha256="c" * 64,
                size_bytes=10,
                mime_type="text/plain",
                original_ext=".txt",
                kind="text",
                summary="Raft operations handbook.",
                description={"sections": [
                    {
                        "id": "election",
                        "title": "Leader Election",
                        "summary": "Raft leader selection.",
                    },
                    {
                        "id": "rollback",
                        "title": "Rollback Procedure",
                        "summary": "Rollback uses a verified snapshot.",
                    },
                    {
                        "id": "placeholder",
                        "title": "Section 3",
                        "summary": "Automatically generated rollback slice.",
                    },
                ]},
                extra="",
                ingest_status="done",
                ingested_at=now,
                deleted_at=None,
                created_at=now,
                updated_at=now,
            ))
            session.add(FileEntry(
                id=entry_id,
                folder_id=None,
                file_id=file_id,
                display_name="handbook.txt",
                lifecycle="active",
                catalog_id=None,
                extra="",
                deleted_at=None,
                purge_after=None,
                created_at=now,
                updated_at=now,
            ))
            await session.commit()

        async with factory() as session:
            built = await build_semantic_index(
                session,
                entry_ids=[entry_id],
                client=_FakeEmbeddingClient(),
                progress_every=0,
            )
        assert built.entries_indexed == 3
        manifest_path = semantic_index_dir() / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["documents"] == 1
        assert manifest["section_entries"] == 2

        hits = await search_semantic_index(
            "rollback procedure",
            limit=5,
            client=_FakeEmbeddingClient(),
        )
        assert [(hit.entry_id, hit.section_id) for hit in hits] == [
            (entry_id, "rollback"),
        ]
        section_matches = await best_semantic_sections(
            "rollback procedure",
            [entry_id],
            client=_FakeEmbeddingClient(),
        )
        assert section_matches[entry_id][0] == "rollback"
        assert section_matches[entry_id][1] == pytest.approx(1.0)

        async with factory() as session:
            rows = await semantic_entry_rows(
                session,
                "rollback procedure",
                limit=5,
                client=_FakeEmbeddingClient(),
            )
            documents = await load_rerank_documents_by_entry_id(
                session,
                [entry_id],
                matched_section_ids={entry_id: "rollback"},
            )
        assert rows[0]["matched_section_id"] == "rollback"
        assert "Rollback Procedure" in documents[entry_id]
        assert "Leader Election" not in documents[entry_id]

        async with factory() as session:
            file_row = await session.get(File, file_id)
            assert file_row is not None
            file_row.description = {"sections": [{
                "id": "starter",
                "title": "Sourdough Starter",
                "summary": "Cooking notes for a sourdough culture.",
            }]}
            file_row.updated_at = _now()
            await session.commit()
        async with factory() as session:
            refreshed = await refresh_semantic_index_for_file(
                session,
                file_id,
                client=_FakeEmbeddingClient(),
            )
        assert refreshed.entries_removed == 3
        assert refreshed.entries_refreshed == 2
        assert refreshed.entries_total == 2
        after = await search_semantic_index(
            "sourdough starter",
            limit=1,
            client=_FakeEmbeddingClient(),
        )
        assert after[0].section_id == "starter"

        manifest["version"] = 1
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        status = semantic_index_status()
        assert status["compatible"] is False
        assert status["needs_rebuild"] is True
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_semantic_index_refresh_updates_reprocessed_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIBRARY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SEMANTIC_RECALL_ENABLED", "true")
    monkeypatch.setenv("EMBEDDING_API_KEY", "fake-key")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "3")
    monkeypatch.setenv("SEMANTIC_INDEX_BACKEND", "file")
    from library.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'refresh.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = _now()
    raft_file_id = new_id()
    raft_entry_id = new_id()
    cooking_file_id = new_id()
    cooking_entry_id = new_id()

    try:
        async with engine.begin() as conn:
            await conn.run_sync(bootstrap_schema_sync)

        async with factory() as session:
            session.add(File(
                id=raft_file_id,
                storage_key="00/aa/raft",
                sha256="a" * 64,
                size_bytes=10,
                mime_type="text/plain",
                original_ext=".txt",
                kind="text",
                summary="Raft consensus uses leader election.",
                description={"sections": []},
                extra="",
                ingest_status="done",
                ingested_at=now,
                deleted_at=None,
                created_at=now,
                updated_at=now,
            ))
            session.add(FileEntry(
                id=raft_entry_id,
                folder_id=None,
                file_id=raft_file_id,
                display_name="doc-a.txt",
                lifecycle="active",
                catalog_id=None,
                extra="",
                deleted_at=None,
                purge_after=None,
                created_at=now,
                updated_at=now,
            ))
            session.add(File(
                id=cooking_file_id,
                storage_key="00/aa/cooking",
                sha256="b" * 64,
                size_bytes=10,
                mime_type="text/plain",
                original_ext=".txt",
                kind="text",
                summary="Cooking notes for sourdough bread.",
                description={"sections": []},
                extra="",
                ingest_status="done",
                ingested_at=now,
                deleted_at=None,
                created_at=now,
                updated_at=now,
            ))
            session.add(FileEntry(
                id=cooking_entry_id,
                folder_id=None,
                file_id=cooking_file_id,
                display_name="doc-b.txt",
                lifecycle="active",
                catalog_id=None,
                extra="",
                deleted_at=None,
                purge_after=None,
                created_at=now,
                updated_at=now,
            ))
            await session.commit()

        async with factory() as session:
            await build_semantic_index(
                session,
                client=_FakeEmbeddingClient(),
                progress_every=0,
            )

        before = await search_semantic_index(
            "leader election",
            limit=1,
            client=_FakeEmbeddingClient(),
        )
        assert [hit.entry_id for hit in before] == [raft_entry_id]

        async with factory() as session:
            file_row = await session.get(File, raft_file_id)
            assert file_row is not None
            file_row.summary = "Reprocessed notes about archival planning."
            file_row.updated_at = _now()
            await session.commit()

        async with factory() as session:
            result = await refresh_semantic_index_for_file(
                session,
                raft_file_id,
                client=_FakeEmbeddingClient(),
            )

        assert result.skipped_reason is None
        assert result.entries_removed == 1
        assert result.entries_refreshed == 1
        assert result.entries_total == 2

        after = await search_semantic_index(
            "leader election",
            limit=1,
            client=_FakeEmbeddingClient(),
        )
        assert [hit.entry_id for hit in after] != [raft_entry_id]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_semantic_refresh_reuses_current_vectors_for_deduplicated_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIBRARY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SEMANTIC_RECALL_ENABLED", "true")
    monkeypatch.setenv("EMBEDDING_API_KEY", "fake-key")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "3")
    monkeypatch.setenv("SEMANTIC_INDEX_BACKEND", "file")
    from library.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'reuse.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = _now()
    file_id = new_id()
    original_entry_id = new_id()
    dedup_entry_id = new_id()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(bootstrap_schema_sync)
        async with factory() as session:
            session.add(File(
                id=file_id,
                storage_key="00/aa/reuse",
                sha256="d" * 64,
                size_bytes=10,
                mime_type="text/plain",
                original_ext=".txt",
                kind="text",
                summary="Raft consensus uses leader election.",
                description={"sections": []},
                extra="",
                ingest_status="done",
                ingested_at=now,
                deleted_at=None,
                created_at=now,
                updated_at=now,
            ))
            session.add(FileEntry(
                id=original_entry_id,
                folder_id=None,
                file_id=file_id,
                display_name="same-name.txt",
                lifecycle="active",
                catalog_id=None,
                extra="",
                deleted_at=None,
                purge_after=None,
                created_at=now,
                updated_at=now,
            ))
            await session.commit()

        async with factory() as session:
            await build_semantic_index(
                session,
                client=_FakeEmbeddingClient(),
                progress_every=0,
            )

        async with factory() as session:
            session.add(FileEntry(
                id=dedup_entry_id,
                folder_id=None,
                file_id=file_id,
                display_name="same-name.txt",
                lifecycle="active",
                catalog_id=None,
                extra="",
                deleted_at=None,
                purge_after=None,
                created_at=now,
                updated_at=now,
            ))
            await session.commit()

        reject = _RejectEmbeddingClient()
        async with factory() as session:
            result = await refresh_semantic_index_for_file(
                session,
                file_id,
                client=reject,
            )

        assert reject.calls == 0
        assert result.entries_removed == 1
        assert result.entries_refreshed == 2
        assert result.vectors_reused == 2
        hits = await search_semantic_index(
            "leader election",
            limit=2,
            client=_FakeEmbeddingClient(),
        )
        assert {hit.entry_id for hit in hits} == {
            original_entry_id,
            dedup_entry_id,
        }
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("setting", "replacement"),
    [("EMBEDDING_MODEL", "replacement-model"), ("EMBEDDING_DIMENSIONS", "4")],
)
async def test_semantic_refresh_enqueues_rebuild_for_incompatible_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    setting: str,
    replacement: str,
) -> None:
    monkeypatch.setenv("LIBRARY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SEMANTIC_RECALL_ENABLED", "true")
    monkeypatch.setenv("EMBEDDING_API_KEY", "fake-key")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "3")
    monkeypatch.setenv("SEMANTIC_INDEX_BACKEND", "file")
    from library.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'mismatch.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = _now()
    file_id = new_id()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(bootstrap_schema_sync)
        async with factory() as session:
            session.add(File(
                id=file_id,
                storage_key="00/aa/mismatch",
                sha256="e" * 64,
                size_bytes=10,
                mime_type="text/plain",
                original_ext=".txt",
                kind="text",
                summary="Raft consensus uses leader election.",
                description={"sections": []},
                extra="",
                ingest_status="done",
                ingested_at=now,
                deleted_at=None,
                created_at=now,
                updated_at=now,
            ))
            session.add(FileEntry(
                id=new_id(),
                folder_id=None,
                file_id=file_id,
                display_name="mismatch.txt",
                lifecycle="active",
                catalog_id=None,
                extra="",
                deleted_at=None,
                purge_after=None,
                created_at=now,
                updated_at=now,
            ))
            await session.commit()
        async with factory() as session:
            await build_semantic_index(
                session,
                client=_FakeEmbeddingClient(),
                progress_every=0,
            )

        monkeypatch.setenv(setting, replacement)
        get_settings.cache_clear()  # type: ignore[attr-defined]
        reject = _RejectEmbeddingClient()
        async with factory() as session:
            result = await refresh_semantic_index_for_file(
                session,
                file_id,
                client=reject,
            )
            tasks = (
                await session.execute(
                    select(Task).where(Task.kind == KIND_REBUILD_SEMANTIC_INDEX)
                )
            ).scalars().all()

        assert reject.calls == 0
        assert result.skipped_reason == "index_config_mismatch_rebuild_enqueued"
        assert len(tasks) == 1
    finally:
        await engine.dispose()


def test_embedding_client_does_not_reuse_vision_key() -> None:
    settings = Settings(
        embedding_provider="openai-compatible",
        embedding_api_key=None,
        llm_vision_api_key="vision-key",
        llm_vision_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    with pytest.raises(EmbeddingConfigError):
        get_embedding_client(settings)


def test_parse_rerank_hits_handles_bailian_response() -> None:
    hits = _parse_rerank_hits({
        "results": [
            {"index": 2, "relevance_score": 0.91},
            {"index": "0", "relevance_score": "0.42"},
        ],
    })

    assert [(hit.index, hit.score, hit.rank) for hit in hits] == [
        (2, 0.91, 1),
        (0, 0.42, 2),
    ]
