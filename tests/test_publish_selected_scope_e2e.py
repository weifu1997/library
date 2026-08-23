"""Selective WebDAV publish must not leak the whole library (audit 二.23).

`publish_selected` limits blobs + entries.jsonl to the chosen entries, but the
row-merge used to splice the COMPLETE local folders/catalogs/views/tags/
tag_aliases/sessions/conversations/journals into the remote snapshot — pushing
a user's entire taxonomy and every private agent conversation/journal when they
share a single document.

This test seeds a small library where the selected entry lives under a nested
folder chain with one attached tag, alongside unrelated folders/tags and
private agent state, then publishes just that one entry and asserts the pack
only carries the reachable taxonomy (folder ancestor chain + attached tags +
their aliases) and drops views/sessions/conversations/journals entirely.

Run:
    .venv/bin/python -m pytest tests/test_publish_selected_scope_e2e.py -q
"""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

_TEST_PARENT = Path(os.environ.get(
    "LIBRARY_TEST_TMP",
    str(Path(__file__).resolve().parent),
))
_TEST_ROOT = _TEST_PARENT / f"_publish_selected_scope_e2e_{os.getpid()}_{uuid4().hex[:8]}"
_TEST_ROOT.mkdir(parents=True, exist_ok=True)
os.environ["LIBRARY_HOME"] = str(_TEST_ROOT)
os.environ["STORAGE_BACKEND"] = "local"
os.environ["WORKER_ENABLED"] = "false"
os.environ["LLM_DEFAULT_API_KEY"] = "sk-fake"
os.environ["LLM_DEFAULT_MODEL"] = "fake-model"
os.environ["WEBDAV_URL"] = "https://dav.test"
os.environ["WEBDAV_REMOTE_PATH"] = "/library-test"

from library.config import Settings as _Settings  # noqa: E402

_Settings.model_config["env_file"] = None

from library.config import get_settings  # noqa: E402
from library.db.engine import dispose_engine, get_engine, get_session_factory  # noqa: E402
from library.db.models import (  # noqa: E402
    Base,
    Conversation,
    EntryTag,
    File,
    FileEntry,
    Folder,
    Journal,
    Session,
    Tag,
    TagAlias,
    View,
)
from library.services.webdav_sync import (  # noqa: E402
    WebDavConfigError,
    _parse_jsonl,
    publish_selected,
)
from library.storage import get_storage, reset_storage_cache  # noqa: E402
from library.utils.ids import new_id  # noqa: E402


async def _create_schema() -> None:
    await _activate_home(_TEST_ROOT)


async def _activate_home(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.environ["LIBRARY_HOME"] = str(path)
    os.environ["STORAGE_BACKEND"] = "local"
    os.environ["WORKER_ENABLED"] = "false"
    os.environ["LLM_DEFAULT_API_KEY"] = "sk-fake"
    os.environ["LLM_DEFAULT_MODEL"] = "fake-model"
    os.environ["WEBDAV_URL"] = "https://dav.test"
    os.environ["WEBDAV_REMOTE_PATH"] = "/library-test"
    get_settings.cache_clear()  # type: ignore[attr-defined]
    reset_storage_cache()
    await dispose_engine()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _one_chunk(body: bytes) -> AsyncIterator[bytes]:
    yield body


class _MemoryWebDavClient:
    remote: dict[str, bytes] = {}

    def __init__(self, _settings) -> None:
        pass

    async def aclose(self) -> None:
        return None

    async def read_json(self, path: str) -> dict | None:
        body = self.remote.get(path)
        return json.loads(body.decode("utf-8")) if body is not None else None

    async def read_bytes(self, path: str) -> bytes:
        return self.remote[path]

    async def exists(self, path: str) -> bool:
        return path in self.remote

    async def ensure_dir(self, path: str) -> None:
        return None

    async def put_bytes(
        self,
        path: str,
        body: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> None:
        self.remote[path] = body

    async def put_stream(
        self,
        path: str,
        stream: AsyncIterator[bytes],
        *,
        content_type: str | None,
    ) -> None:
        body = bytearray()
        async for chunk in stream:
            body.extend(chunk)
        self.remote[path] = bytes(body)

    async def stream_to_storage(
        self,
        path: str,
        *,
        storage_key: str,
        display_name: str,
        folder_path: str | None,
        content_type: str | None,
        expected_sha256: str | None = None,
    ) -> str:
        body = self.remote[path]
        if expected_sha256:
            actual = hashlib.sha256(body).hexdigest()
            if actual != expected_sha256.lower():
                raise WebDavConfigError("downloaded blob sha256 mismatch")
        return await get_storage().put(
            storage_key,
            _one_chunk(body),
            content_type=content_type,
            display_name=display_name,
            folder_path=folder_path,
        )


def _mk_file(storage_key: str, sha: str, summary: str, now: datetime) -> File:
    return File(
        id=new_id(),
        storage_key=storage_key,
        sha256=sha,
        size_bytes=10,
        mime_type="text/plain",
        original_ext=".txt",
        kind="text",
        summary=summary,
        description=None,
        extra="",
        ingest_status="done",
        ingested_at=now,
        created_at=now,
        updated_at=now,
    )


def _mk_tag(name: str, now: datetime) -> Tag:
    return Tag(
        id=new_id(),
        name=name,
        facet="topic",
        alias_of=None,
        doc_count=1,
        last_used_at=now,
        created_at=now,
        updated_at=now,
    )


async def _seed_scoped_source() -> dict[str, str]:
    now = datetime.now(timezone.utc)
    sel_body = b"Selected shared document.\n"
    other_body = b"Unrelated private document.\n"
    sel_sha = hashlib.sha256(sel_body).hexdigest()
    other_sha = hashlib.sha256(other_body).hexdigest()
    await get_storage().put("aa/bb/selected", _one_chunk(sel_body), content_type="text/plain")
    await get_storage().put("aa/bb/other", _one_chunk(other_body), content_type="text/plain")

    factory = get_session_factory()
    async with factory() as session:
        # Nested ancestor chain for the selected entry + an unrelated sibling
        # tree that must NOT ride along on the selective publish.
        work = Folder(id=new_id(), parent_id=None, name="work", created_at=now, updated_at=now)
        projects = Folder(id=new_id(), parent_id=work.id, name="projects", created_at=now, updated_at=now)
        alpha = Folder(id=new_id(), parent_id=projects.id, name="alpha", created_at=now, updated_at=now)
        personal = Folder(id=new_id(), parent_id=None, name="personal", created_at=now, updated_at=now)

        sel_file = _mk_file("aa/bb/selected", sel_sha, "Shared summary", now)
        other_file = _mk_file("aa/bb/other", other_sha, "Private summary", now)

        sel_entry = FileEntry(
            id=new_id(), folder_id=alpha.id, file_id=sel_file.id,
            display_name="shared.txt", lifecycle="active", catalog_id=None,
            extra="", created_at=now, updated_at=now,
        )
        other_entry = FileEntry(
            id=new_id(), folder_id=personal.id, file_id=other_file.id,
            display_name="private.txt", lifecycle="active", catalog_id=None,
            extra="", created_at=now, updated_at=now,
        )

        shared_tag = _mk_tag("shared", now)   # attached to the selected entry
        private_tag = _mk_tag("private", now)  # attached only to the other entry
        orphan_tag = _mk_tag("orphan", now)    # attached to nothing

        share_alias = TagAlias(
            id=new_id(), from_name="共享", to_tag_id=shared_tag.id,
            note=None, created_at=now,
        )
        priv_alias = TagAlias(
            id=new_id(), from_name="私密", to_tag_id=private_tag.id,
            note=None, created_at=now,
        )

        view = View(
            id=new_id(), name="Everything", summary=None, description=None,
            extra=None, tags=["private"], filter_spec={"lifecycle": ["active"]},
            created_at=now, updated_at=now,
        )

        sess = Session(
            id=new_id(), started_at=now, ended_at=now, end_reason="normal",
            initiating_user_message="private chat", turn_count=1,
            total_input_tokens=1, total_output_tokens=2, total_cache_read=0,
            total_tool_calls=0, total_llm_calls=0,
            total_cost_estimate=Decimal("0"), total_duration_ms=0,
        )
        conv = Conversation(
            id=new_id(), session_id=sess.id, turn_index=0, started_at=now,
            ended_at=now, user_message="private chat", agent_response="secret",
            tool_calls=[], llm_calls=[], total_input_tokens=1,
            total_output_tokens=2, total_cache_read=0, total_tool_calls=0,
            total_llm_calls=0, total_cost_estimate=Decimal("0"),
            total_duration_ms=0,
        )
        journal = Journal(
            id=new_id(), conversation_id=conv.id,
            note="A private note about the unrelated document.",
            entry_ids=[other_entry.id], tags=["private"], source_kind="insight",
            summarized_journal_ids=[], created_at=now,
        )

        session.add_all([
            work, projects, alpha, personal, sel_file, other_file,
            shared_tag, private_tag, orphan_tag, view, sess,
        ])
        await session.flush()
        session.add_all([sel_entry, other_entry, share_alias, priv_alias])
        await session.flush()
        session.add(conv)
        await session.flush()
        session.add(journal)
        await session.flush()
        session.add_all([
            EntryTag(entry_id=sel_entry.id, tag_id=shared_tag.id, source="ingest", created_at=now),
            EntryTag(entry_id=other_entry.id, tag_id=private_tag.id, source="ingest", created_at=now),
        ])
        await session.commit()

        return {
            "selected_entry_id": sel_entry.id,
            "other_entry_id": other_entry.id,
            "work_id": work.id,
            "projects_id": projects.id,
            "alpha_id": alpha.id,
            "personal_id": personal.id,
            "shared_tag_id": shared_tag.id,
            "private_tag_id": private_tag.id,
            "orphan_tag_id": orphan_tag.id,
            "view_id": view.id,
            "session_id": sess.id,
            "conversation_id": conv.id,
            "journal_id": journal.id,
        }


async def test_publish_selected_scopes_metadata_to_selected_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _activate_home(_TEST_ROOT / "source_scope")
    seeded = await _seed_scoped_source()
    _MemoryWebDavClient.remote = {}
    monkeypatch.setattr(
        "library.services.webdav_sync.WebDavClient",
        _MemoryWebDavClient,
    )

    published = await publish_selected([seeded["selected_entry_id"]])
    assert published["selected_entries"] == 1

    remote = _MemoryWebDavClient.remote
    latest = json.loads(remote["/library-test/latest.json"].decode("utf-8"))
    snapshot_root = f"/library-test/snapshots/{latest['snapshot_id']}"

    def rows(name: str) -> list[dict]:
        return _parse_jsonl(remote[f"{snapshot_root}/{name}"], source=name)

    # Only the selected entry is published.
    entry_ids = {row["entry_id"] for row in rows("entries.jsonl")}
    assert entry_ids == {seeded["selected_entry_id"]}

    # Folders: exactly the ancestor chain of the selected entry's folder;
    # the unrelated "personal" tree is NOT leaked.
    folder_ids = {row["folder_id"] for row in rows("folders.jsonl")}
    assert folder_ids == {seeded["work_id"], seeded["projects_id"], seeded["alpha_id"]}
    assert seeded["personal_id"] not in folder_ids

    # Tags: only the tag actually attached to the selected entry.
    tag_ids = {row["tag_id"] for row in rows("tags.jsonl")}
    assert tag_ids == {seeded["shared_tag_id"]}
    assert seeded["private_tag_id"] not in tag_ids
    assert seeded["orphan_tag_id"] not in tag_ids

    # Tag aliases: only those pointing at an attached tag.
    alias_targets = {row["to_tag_id"] for row in rows("tag_aliases.jsonl")}
    assert alias_targets == {seeded["shared_tag_id"]}

    # Private / unrelated collections are dropped from a selective publish.
    assert rows("views.jsonl") == []
    assert rows("sessions.jsonl") == []
    assert rows("conversations.jsonl") == []
    assert rows("journals.jsonl") == []


if __name__ == "__main__":
    import asyncio

    async def _main() -> None:
        await _create_schema()

    asyncio.run(_main())
