from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from library.agent.tools.search_journal import run_search_journal
from library.db.bootstrap import bootstrap_schema_sync
from library.db.models import Conversation, File, FileEntry, Journal, Session
from library.utils.ids import new_id


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_search_journal_marks_and_downgrades_stale_entry_references(
    tmp_path: Path,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'journal.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = _now()

    current_file_id = new_id()
    current_entry_id = new_id()
    reingested_file_id = new_id()
    reingested_entry_id = new_id()
    deleted_file_id = new_id()
    deleted_entry_id = new_id()
    conv_id = new_id()

    try:
        async with engine.begin() as conn:
            await conn.run_sync(bootstrap_schema_sync)

        async with factory() as session:
            session_id = new_id()
            session.add(Session(
                id=session_id,
                started_at=now - timedelta(days=4),
                ended_at=now - timedelta(days=4),
                end_reason="normal",
                initiating_user_message="seed",
                turn_count=1,
                total_input_tokens=0,
                total_output_tokens=0,
                total_cache_read=0,
                total_tool_calls=0,
                total_llm_calls=0,
                total_duration_ms=0,
            ))
            session.add(Conversation(
                id=conv_id,
                session_id=session_id,
                turn_index=0,
                started_at=now - timedelta(days=4),
                ended_at=now - timedelta(days=4),
                user_message="seed",
                agent_response="seed",
                tool_calls=[],
                llm_calls=[],
                total_input_tokens=0,
                total_output_tokens=0,
                total_tool_calls=0,
                total_llm_calls=0,
                total_duration_ms=0,
            ))
            session.add_all([
                File(
                    id=current_file_id,
                    storage_key="aa/current",
                    sha256="a" * 64,
                    size_bytes=10,
                    mime_type="text/plain",
                    original_ext=".txt",
                    kind="text",
                    summary="current",
                    description=None,
                    extra=None,
                    ingest_status="done",
                    ingested_at=now - timedelta(days=4),
                    deleted_at=None,
                    created_at=now - timedelta(days=4),
                    updated_at=now - timedelta(days=4),
                ),
                File(
                    id=reingested_file_id,
                    storage_key="aa/reingested",
                    sha256="b" * 64,
                    size_bytes=10,
                    mime_type="text/plain",
                    original_ext=".txt",
                    kind="text",
                    summary="reingested",
                    description=None,
                    extra=None,
                    ingest_status="done",
                    ingested_at=now,
                    deleted_at=None,
                    created_at=now - timedelta(days=4),
                    updated_at=now,
                ),
                File(
                    id=deleted_file_id,
                    storage_key="aa/deleted",
                    sha256="c" * 64,
                    size_bytes=10,
                    mime_type="text/plain",
                    original_ext=".txt",
                    kind="text",
                    summary="deleted",
                    description=None,
                    extra=None,
                    ingest_status="done",
                    ingested_at=now - timedelta(days=4),
                    deleted_at=None,
                    created_at=now - timedelta(days=4),
                    updated_at=now - timedelta(days=4),
                ),
            ])
            session.add_all([
                FileEntry(
                    id=current_entry_id,
                    folder_id=None,
                    file_id=current_file_id,
                    display_name="current.txt",
                    lifecycle="active",
                    catalog_id=None,
                    extra=None,
                    deleted_at=None,
                    purge_after=None,
                    created_at=now - timedelta(days=4),
                    updated_at=now - timedelta(days=4),
                ),
                FileEntry(
                    id=reingested_entry_id,
                    folder_id=None,
                    file_id=reingested_file_id,
                    display_name="reingested.txt",
                    lifecycle="active",
                    catalog_id=None,
                    extra=None,
                    deleted_at=None,
                    purge_after=None,
                    created_at=now - timedelta(days=4),
                    updated_at=now,
                ),
                FileEntry(
                    id=deleted_entry_id,
                    folder_id=None,
                    file_id=deleted_file_id,
                    display_name="deleted.txt",
                    lifecycle="active",
                    catalog_id=None,
                    extra=None,
                    deleted_at=now,
                    purge_after=now + timedelta(days=30),
                    created_at=now - timedelta(days=4),
                    updated_at=now,
                ),
            ])
            session.add_all([
                Journal(
                    id=new_id(),
                    conversation_id=conv_id,
                    note="consensus stale newer note",
                    entry_ids=[reingested_entry_id, deleted_entry_id],
                    tags=["consensus"],
                    source_kind="insight",
                    created_at=now - timedelta(days=1),
                ),
                Journal(
                    id=new_id(),
                    conversation_id=conv_id,
                    note="consensus current older note",
                    entry_ids=[current_entry_id],
                    tags=["consensus"],
                    source_kind="insight",
                    created_at=now - timedelta(days=2),
                ),
            ])
            await session.commit()

        async with factory() as session:
            result = await run_search_journal(
                session,
                {"text": "consensus", "limit": 10, "since_days": 10},
            )

        notes = result["notes"]
        assert [note["note"] for note in notes] == [
            "consensus current older note",
            "consensus stale newer note",
        ]
        assert notes[0]["entry_validity"]["status"] == "current"
        assert notes[1]["entry_validity"]["status"] == "stale"
        assert notes[1]["validity_note"] == "引用实体已变更"
        stale_entries = {
            item["entry_id"]: item["reason"]
            for item in notes[1]["entry_validity"]["entries"]
        }
        assert stale_entries == {
            reingested_entry_id: "file_reingested_after_note",
            deleted_entry_id: "entry_deleted",
        }
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_soft_delete_invalidates_journals_that_mention_the_entry(
    tmp_path: Path,
) -> None:
    from library.services.entries import soft_delete_entry
    from library.services.folders import (
        resolve_or_create_folder,
        soft_delete_folder,
    )

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'org-m2.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = _now()
    live_file_id = new_id()
    live_entry_id = new_id()
    gone_file_id = new_id()
    gone_entry_id = new_id()
    other_file_id = new_id()
    other_entry_id = new_id()
    conv_id = new_id()
    mentioned_id = new_id()
    untouched_id = new_id()

    try:
        async with engine.begin() as conn:
            await conn.run_sync(bootstrap_schema_sync)

        async with factory() as session:
            session_id = new_id()
            session.add(Session(
                id=session_id,
                started_at=now,
                ended_at=now,
                end_reason="normal",
                initiating_user_message="seed",
                turn_count=1,
                total_input_tokens=0,
                total_output_tokens=0,
                total_cache_read=0,
                total_tool_calls=0,
                total_llm_calls=0,
                total_duration_ms=0,
            ))
            session.add(Conversation(
                id=conv_id,
                session_id=session_id,
                turn_index=0,
                started_at=now,
                ended_at=now,
                user_message="seed",
                agent_response="seed",
                tool_calls=[],
                llm_calls=[],
                total_input_tokens=0,
                total_output_tokens=0,
                total_tool_calls=0,
                total_llm_calls=0,
                total_duration_ms=0,
            ))
            session.add_all([
                File(
                    id=live_file_id, storage_key="aa/live", sha256="a" * 64,
                    size_bytes=10, mime_type="text/plain", original_ext=".txt",
                    kind="text", summary="live", description=None, extra=None,
                    ingest_status="done", ingested_at=now, deleted_at=None,
                    created_at=now, updated_at=now,
                ),
                File(
                    id=gone_file_id, storage_key="aa/gone", sha256="b" * 64,
                    size_bytes=10, mime_type="text/plain", original_ext=".txt",
                    kind="text", summary="gone", description=None, extra=None,
                    ingest_status="done", ingested_at=now, deleted_at=None,
                    created_at=now, updated_at=now,
                ),
                File(
                    id=other_file_id, storage_key="aa/other", sha256="c" * 64,
                    size_bytes=10, mime_type="text/plain", original_ext=".txt",
                    kind="text", summary="other", description=None, extra=None,
                    ingest_status="done", ingested_at=now, deleted_at=None,
                    created_at=now, updated_at=now,
                ),
            ])
            session.add_all([
                FileEntry(
                    id=live_entry_id, folder_id=None, file_id=live_file_id,
                    display_name="live.txt", lifecycle="active",
                    catalog_id=None, extra=None, deleted_at=None,
                    purge_after=None, created_at=now, updated_at=now,
                ),
                FileEntry(
                    id=gone_entry_id, folder_id=None, file_id=gone_file_id,
                    display_name="gone.txt", lifecycle="active",
                    catalog_id=None, extra=None, deleted_at=None,
                    purge_after=None, created_at=now, updated_at=now,
                ),
                FileEntry(
                    id=other_entry_id, folder_id=None, file_id=other_file_id,
                    display_name="other.txt", lifecycle="active",
                    catalog_id=None, extra=None, deleted_at=None,
                    purge_after=None, created_at=now, updated_at=now,
                ),
            ])
            session.add_all([
                Journal(
                    id=mentioned_id, conversation_id=conv_id,
                    note="mentions gone entry",
                    entry_ids=[gone_entry_id],
                    tags=["org"], source_kind="insight", created_at=now,
                ),
                Journal(
                    id=untouched_id, conversation_id=conv_id,
                    note="does not mention gone entry",
                    entry_ids=[other_entry_id],
                    tags=["org"], source_kind="insight", created_at=now,
                ),
            ])
            await session.commit()

        async with factory() as session:
            await soft_delete_entry(session, entry_id=gone_entry_id)
            await session.commit()

        async with factory() as session:
            result = await run_search_journal(
                session, {"text": "entry", "limit": 10, "since_days": 10},
            )
            notes = result["notes"]
            assert [note["id"] for note in notes] == [untouched_id]
            mentioned = await session.get(Journal, mentioned_id)
            assert mentioned is not None
            assert mentioned.invalidated_at is not None
            assert mentioned.invalidated_reason == "entry_deleted"
            assert mentioned.invalidated_by_id is None
            untouched = await session.get(Journal, untouched_id)
            assert untouched is not None
            assert untouched.invalidated_at is None

        folder_file_id = new_id()
        folder_entry_id = new_id()
        folder_journal_id = new_id()
        async with factory() as session:
            folder = await resolve_or_create_folder(session, ["org-m2"])
            assert folder is not None
            session.add(File(
                id=folder_file_id, storage_key="aa/folder-file", sha256="d" * 64,
                size_bytes=10, mime_type="text/plain", original_ext=".txt",
                kind="text", summary="folder", description=None, extra=None,
                ingest_status="done", ingested_at=now, deleted_at=None,
                created_at=now, updated_at=now,
            ))
            session.add(FileEntry(
                id=folder_entry_id, folder_id=folder.id, file_id=folder_file_id,
                display_name="nested.txt", lifecycle="active",
                catalog_id=None, extra=None, deleted_at=None,
                purge_after=None, created_at=now, updated_at=now,
            ))
            session.add(Journal(
                id=folder_journal_id, conversation_id=conv_id,
                note="mentions nested folder entry",
                entry_ids=[folder_entry_id],
                tags=["org"], source_kind="insight", created_at=now,
            ))
            await session.commit()
            folder_id = folder.id

        async with factory() as session:
            await soft_delete_folder(session, folder_id=folder_id)
            await session.commit()

        async with factory() as session:
            nested = await session.get(Journal, folder_journal_id)
            assert nested is not None
            assert nested.invalidated_reason == "entry_deleted"
            leftover = await run_search_journal(
                session, {"text": "nested", "limit": 10, "since_days": 10},
            )
            assert leftover["notes"] == []
    finally:
        await engine.dispose()
