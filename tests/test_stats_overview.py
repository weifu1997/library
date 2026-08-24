"""Unit tests for GET /v1/stats/overview (`routes_stats.stats_overview`).

Covers: empty-library zero values, seeded counts, recent ordering by
created_at desc, task running/pending counts, and read-only behaviour
(no dirty objects left behind on the session).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from library.api.routes_stats import stats_overview
from library.config import get_settings
from library.db.models import Base, File, FileEntry, Folder, Tag, Task
from library.tasks.kinds import KIND_INGEST_FILE


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _shift(dt: datetime, seconds: int) -> datetime:
    return dt + timedelta(seconds=seconds)


def _folder(folder_id: str, *, name: str, parent_id: str | None = None) -> Folder:
    now = _now()
    return Folder(
        id=folder_id,
        name=name,
        parent_id=parent_id,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


def _file(file_id: str, *, status: str = "done") -> File:
    now = _now()
    return File(
        id=file_id,
        storage_key=f"store/{file_id}",
        sha256=file_id.replace("-", "")[:64].ljust(64, "0"),
        size_bytes=10,
        mime_type="text/plain",
        original_ext=".txt",
        kind=None,
        summary=None,
        description=None,
        extra=None,
        ingest_status=status,
        ingested_at=now if status == "done" else None,
        deleted_at=None,
        created_at=now,
        updated_at=now,
    )


def _entry(
    entry_id: str,
    *,
    file_id: str,
    name: str,
    folder_id: str | None,
    created_at: datetime,
) -> FileEntry:
    return FileEntry(
        id=entry_id,
        folder_id=folder_id,
        file_id=file_id,
        display_name=name,
        lifecycle="active",
        created_at=created_at,
        updated_at=created_at,
        deleted_at=None,
        purge_after=None,
    )


def _tag(tag_id: str, *, name: str) -> Tag:
    return Tag(id=tag_id, name=name, facet="topic")


def _task(task_id: str, *, status: str) -> Task:
    now = _now()
    return Task(
        id=task_id,
        kind=KIND_INGEST_FILE,
        payload={},
        dedup_key=f"ingest_file:{task_id}",
        status=status,
        priority=100,
        attempts=1,
        max_attempts=5,
        last_error=None,
        scheduled_at=now,
        lease_expires_at=None,
        last_heartbeat_at=None,
        locked_by=None,
        created_at=now,
        started_at=now if status == "running" else None,
        finished_at=None,
    )


@pytest.mark.asyncio
async def test_empty_library_returns_zero_values(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'empty.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with factory() as session:
            payload = await stats_overview(session)

        expected = get_settings()
        assert payload["totals"]["entries"] == 0
        assert payload["totals"]["folders"] == 0
        assert payload["totals"]["tags"] == 0
        assert payload["tasks"] == {"running": 0, "pending": 0}
        assert payload["recent"] == []
        assert payload["storage_backend"] == expected.storage_backend
        assert isinstance(payload["semantic"]["enabled"], bool)
        assert isinstance(payload["semantic"]["configured"], bool)
        assert isinstance(payload["semantic"]["index_ready"], bool)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_seeded_counts_and_recent_order(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'state.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        base = _now()
        folder_a = _folder("folder-a", name="A")
        folder_b = _folder("folder-b", name="B", parent_id="folder-a")
        files = [
            _file("file-old", status="done"),
            _file("file-mid", status="failed"),
            _file("file-new", status="pending"),
        ]
        entries = [
            _entry(
                "entry-old", file_id="file-old", name="oldest.txt",
                folder_id="folder-b", created_at=base,
            ),
            _entry(
                "entry-mid", file_id="file-mid", name="middle.txt",
                folder_id=None, created_at=_shift(base, 1),
            ),
            _entry(
                "entry-new", file_id="file-new", name="newest.txt",
                folder_id=None, created_at=_shift(base, 2),
            ),
        ]
        tags = [_tag("tag-a", name="alpha"), _tag("tag-b", name="beta")]
        tasks = [
            _task("task-run", status="running"),
            _task("task-p1", status="pending"),
            _task("task-p2", status="pending"),
        ]

        async with factory() as session:
            session.add_all([
                folder_a, folder_b, *files, *entries, *tags, *tasks,
            ])
            await session.commit()

        async with factory() as session:
            payload = await stats_overview(session)
            # Read-only: the endpoint must leave no pending writes on the session.
            assert not session.new
            assert not session.dirty

        assert payload["totals"]["entries"] == 3
        assert payload["totals"]["folders"] == 2
        assert payload["totals"]["tags"] == 2
        assert payload["tasks"] == {"running": 1, "pending": 2}

        recent = payload["recent"]
        assert [r["entry_id"] for r in recent] == [
            "entry-new", "entry-mid", "entry-old",
        ]
        assert recent[0]["display_name"] == "newest.txt"
        assert recent[0]["ingest_status"] == "pending"
        assert recent[1]["folder_path"] is None
        assert recent[2]["folder_path"] == "/A/B"
        assert recent[0]["created_at"] is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_soft_deleted_rows_are_excluded(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'deleted.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        now = _now()
        live_file = _file("file-live", status="done")
        deleted_file = _file("file-gone", status="done")
        deleted_file.deleted_at = now
        entries = [
            _entry(
                "entry-live", file_id="file-live", name="live.txt",
                folder_id=None, created_at=now,
            ),
            _entry(
                "entry-gone", file_id="file-gone", name="gone.txt",
                folder_id=None, created_at=_shift(now, 1),
            ),
        ]

        async with factory() as session:
            session.add_all([live_file, deleted_file, *entries])
            await session.commit()

        async with factory() as session:
            payload = await stats_overview(session)

        # The soft-deleted file/entry must not count or appear in recent.
        assert payload["totals"]["entries"] == 1
        assert [r["entry_id"] for r in payload["recent"]] == ["entry-live"]
    finally:
        await engine.dispose()
