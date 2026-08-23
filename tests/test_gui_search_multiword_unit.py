"""GUI/desktop file-search tokenization (audit 二.9).

`user_files.search_entries` used to pass the raw box query as a single
substring to the repository, so a 2+ word query only matched when the whole
phrase (spaces included) occurred contiguously in a metadata field, with no
relevance ordering. It now routes the query through the same
`normalize_text_queries` tokenizer the agent tools use and orders by FTS rank
via `search_filtered`. These tests pin that behaviour: multi-word queries match
when the words appear separately, results come back ranked, and single-word +
CJK recall keep working.

Run:
    .venv/bin/python -m pytest tests/test_gui_search_multiword_unit.py -q
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from library.db.bootstrap import bootstrap_schema_sync
from library.db.fts import ENTRY_METADATA_FTS_TABLE
from library.db.models import File, FileEntry
from library.services.user_files import search_entries
from library.utils.ids import new_id


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _add_entry(session, *, display_name: str, summary: str, now: datetime) -> str:
    """Insert a File + live FileEntry pair and return the entry id."""
    file_id = new_id()
    entry_id = new_id()
    session.add(File(
        id=file_id,
        storage_key=f"00/aa/{file_id}",
        sha256=hashlib.sha256(file_id.encode()).hexdigest(),
        size_bytes=10,
        mime_type="text/plain",
        original_ext=".txt",
        kind="text",
        summary=summary,
        description=None,
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
        display_name=display_name,
        lifecycle="active",
        catalog_id=None,
        extra="",
        deleted_at=None,
        purge_after=None,
        created_at=now,
        updated_at=now,
    ))
    return entry_id


async def _require_fts(session) -> None:
    has_fts = (
        await session.execute(
            text(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = :name"
            ),
            {"name": ENTRY_METADATA_FTS_TABLE},
        )
    ).scalar_one_or_none()
    if not has_fts:
        pytest.skip("SQLite build does not provide FTS5 trigram")


@pytest.mark.asyncio
async def test_gui_multiword_search_matches_separate_words_and_ranks(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'gui_multiword.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = _now()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(bootstrap_schema_sync)

        async with factory() as session:
            await _require_fts(session)
            # "both" has the two query words but NEVER as the contiguous phrase
            # "transformer survey"; "one" has only "survey"; "neither" has none.
            both_id = _add_entry(
                session,
                display_name="notes.txt",
                summary="A transformer architecture and a broad survey of benchmarks.",
                now=now,
            )
            one_id = _add_entry(
                session,
                display_name="methods.txt",
                summary="A survey of classical statistical methods.",
                now=now,
            )
            neither_id = _add_entry(
                session,
                display_name="recipes.txt",
                summary="Baking bread and pastry techniques.",
                now=now,
            )
            await session.commit()

        async with factory() as session:
            results = await search_entries(session, query="transformer survey")

        ids = [row["entry_id"] for row in results]
        # The old single-phrase LIKE returned nothing here: neither summary
        # contains the contiguous string "transformer survey".
        assert both_id in ids
        assert one_id in ids
        assert neither_id not in ids
        # Ranked by relevance: the entry matching BOTH terms comes first.
        assert ids[0] == both_id
        assert ids.index(both_id) < ids.index(one_id)

        # Single-word recall still works and is scoped to the matching doc.
        async with factory() as session:
            single = await search_entries(session, query="transformer")
        assert [row["entry_id"] for row in single] == [both_id]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_gui_search_matches_cjk_multiword_query(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'gui_cjk.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = _now()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(bootstrap_schema_sync)

        async with factory() as session:
            await _require_fts(session)
            # "机器学习" and "笔记" appear separately (not as one phrase); "笔记"
            # is a 2-char term that rides the short-term LIKE rescue path.
            target_id = _add_entry(
                session,
                display_name="ml.txt",
                summary="本文介绍机器学习的核心方法，并附有详细的复习笔记。",
                now=now,
            )
            noise_id = _add_entry(
                session,
                display_name="food.txt",
                summary="关于烹饪的食谱与面包制作说明。",
                now=now,
            )
            await session.commit()

        async with factory() as session:
            results = await search_entries(session, query="机器学习 笔记")

        ids = {row["entry_id"] for row in results}
        assert target_id in ids
        assert noise_id not in ids
    finally:
        await engine.dispose()
