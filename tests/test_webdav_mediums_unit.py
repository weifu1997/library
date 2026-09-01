"""WEBDAV-M1/M2/M3: untrusted snapshot paths, status redaction, CHECK-field skip.

Run:
    uv run pytest tests/test_webdav_mediums_unit.py -q
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

_TEST_PARENT = Path(os.environ.get(
    "LIBRARY_TEST_TMP",
    tempfile.gettempdir(),
))
_TEST_ROOT = _TEST_PARENT / f"_webdav_mediums_unit_{os.getpid()}_{uuid4().hex[:8]}"
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

from library.config import Settings, get_settings  # noqa: E402
from library.db.engine import dispose_engine, get_engine, get_session_factory  # noqa: E402
from library.db.models import (  # noqa: E402
    Base,
    Catalog,
    EntryRelation,
    File,
    FileEntry,
    Tag,
)
from library.services.webdav_sync import (  # noqa: E402
    WebDavConfigError,
    _as_int,
    _import_metadata,
    _redact_error,
    _status_path,
    _validated_blob_path,
    _validated_latest_snapshot,
    _write_status,
    hydrate_entry,
    pull_latest_metadata,
)
from library.storage import get_storage, reset_storage_cache  # noqa: E402
from library.utils.ids import new_id  # noqa: E402

_REMOTE_ROOT = "/library-test"
_SHA = "ab" * 32
_BLOB_PATH = f"blobs/sha256/ab/{_SHA}"
_SNAPSHOT_ID = "feedfacefeedface"


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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jsonl_test_bytes(rows: list[dict[str, object]]) -> bytes:
    if not rows:
        return b""
    return (
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows)
        + "\n"
    ).encode("utf-8")


class _MemoryWebDavClient:
    remote: dict[str, bytes] = {}
    captured_stream_path: str | None = None

    def __init__(self, _settings) -> None:
        pass

    async def aclose(self) -> None:
        return None

    async def read_json(self, path: str) -> dict | None:
        body = self.remote.get(path)
        return json.loads(body.decode("utf-8")) if body is not None else None

    async def read_bytes(self, path: str) -> bytes:
        return self.remote[path]

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
        _MemoryWebDavClient.captured_stream_path = path
        body = self.remote.get(path, b"")
        if expected_sha256:
            actual = hashlib.sha256(body).hexdigest()
            if actual != expected_sha256.lower():
                raise WebDavConfigError("downloaded blob sha256 mismatch")
        return await get_storage().put(
            storage_key,
            _one_chunk(body or b"ok"),
            content_type=content_type,
            display_name=display_name,
            folder_path=folder_path,
        )


def _use_memory_client(monkeypatch: pytest.MonkeyPatch) -> None:
    _MemoryWebDavClient.remote = {}
    _MemoryWebDavClient.captured_stream_path = None
    monkeypatch.setattr(
        "library.services.webdav_sync.WebDavClient",
        _MemoryWebDavClient,
    )


def _file_meta(
    file_id: str,
    *,
    blob_path: str = _BLOB_PATH,
    size_bytes: object = 3,
    ingest_status: str = "done",
    kind: str = "text",
) -> dict[str, object]:
    now_iso = _now_iso()
    return {
        "file_id": file_id,
        "sha256": _SHA,
        "blob_path": blob_path,
        "size_bytes": size_bytes,
        "mime_type": "text/plain",
        "original_ext": ".txt",
        "kind": kind,
        "ingest_status": ingest_status,
        "created_at": now_iso,
        "updated_at": now_iso,
    }


def _entry_row(
    *,
    entry_id: str,
    file_id: str,
    lifecycle: str = "active",
    catalog_id: str | None = None,
    size_bytes: object = 3,
    tags: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    now_iso = _now_iso()
    return {
        "entry_id": entry_id,
        "folder_id": None,
        "display_name": "ok.txt",
        "lifecycle": lifecycle,
        "catalog_id": catalog_id,
        "created_at": now_iso,
        "updated_at": now_iso,
        "tags": tags or [],
        "file": _file_meta(file_id, size_bytes=size_bytes),
    }


def _empty_rows() -> dict[str, list[dict[str, object]]]:
    return {
        "folders.jsonl": [],
        "catalogs.jsonl": [],
        "views.jsonl": [],
        "tags.jsonl": [],
        "tag_aliases.jsonl": [],
        "entries.jsonl": [],
        "relations.jsonl": [],
        "sessions.jsonl": [],
        "conversations.jsonl": [],
        "journals.jsonl": [],
    }


def _manifest() -> dict[str, object]:
    return {
        "format": "library-knowledge-pack",
        "schema_version": 1,
        "snapshot_id": _SNAPSHOT_ID,
        "created_at": _now_iso(),
        "library_id": "unit-library",
        "app_version": "0.0.0",
        "counts": {},
        "metadata_files": [
            "manifest.json",
            "folders.jsonl",
            "catalogs.jsonl",
            "views.jsonl",
            "tags.jsonl",
            "tag_aliases.jsonl",
            "entries.jsonl",
            "relations.jsonl",
        ],
    }


# ---------------------------------------------------------------------------
# WEBDAV-M1 — untrusted snapshot paths
# ---------------------------------------------------------------------------


def test_validated_blob_path_accepts_content_addressed_layout() -> None:
    assert _validated_blob_path(_BLOB_PATH) == _BLOB_PATH
    assert _validated_blob_path("/" + _BLOB_PATH) == _BLOB_PATH


@pytest.mark.parametrize(
    "value",
    [
        "",
        "../Photos/secret.bin",
        "blobs/sha256/../secret.bin",
        "blobs/sha256/ab/../" + ("c" * 64),
        "blobs/sha256/AB/" + ("ab" * 32),
        "blobs/sha256/ab/" + ("ab" * 31),
        "snapshots/feedfacefeedface/manifest.json",
        "blobs/sha256/ab/" + ("ab" * 32) + "/extra",
    ],
)
def test_validated_blob_path_rejects_non_layout(value: str) -> None:
    with pytest.raises(WebDavConfigError):
        _validated_blob_path(value)


def test_validated_latest_snapshot_accepts_hex_manifest() -> None:
    pointer = f"snapshots/{_SNAPSHOT_ID}/manifest.json"
    assert _validated_latest_snapshot(pointer) == pointer
    assert _validated_latest_snapshot("/" + pointer) == pointer
    assert _validated_latest_snapshot("", required=False) == ""


@pytest.mark.parametrize(
    "value",
    [
        "",
        "../../../other-user/manifest.json",
        "snapshots/../manifest.json",
        "snapshots/feedfacefeedface/../manifest.json",
        "snapshots/FEEDFACEFEEDFACE/manifest.json",
        "snapshots/feedfacefeedfac/manifest.json",
        "snapshots/feedfacefeedface/other.json",
        "blobs/sha256/ab/" + ("ab" * 32),
    ],
)
def test_validated_latest_snapshot_rejects_non_layout(value: str) -> None:
    with pytest.raises(WebDavConfigError):
        _validated_latest_snapshot(value)


async def test_pull_rejects_hostile_latest_snapshot_without_joining(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = _TEST_ROOT / "hostile_latest"
    _use_memory_client(monkeypatch)
    await _activate_home(home)
    latest = {
        "format": "library-webdav-latest",
        "schema_version": 1,
        "library_id": "hostile-library",
        "snapshot_id": _SNAPSHOT_ID,
        "latest_snapshot": "../../../other-user/manifest.json",
        "updated_at": _now_iso(),
    }
    _MemoryWebDavClient.remote = {
        f"{_REMOTE_ROOT}/latest.json": (json.dumps(latest) + "\n").encode("utf-8"),
        "/other-user/manifest.json": b"{}",
        f"{_REMOTE_ROOT}/../../../other-user/manifest.json": b"{}",
    }
    with pytest.raises(WebDavConfigError, match="latest_snapshot"):
        await pull_latest_metadata()


async def test_hydrate_ignores_marker_remote_root_and_rejects_bad_blob_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = _TEST_ROOT / "hydrate_root"
    _use_memory_client(monkeypatch)
    await _activate_home(home)

    now = datetime.now(timezone.utc)
    file_id = new_id()
    entry_id = new_id()
    storage_key = f"seed/{file_id}"
    body = b"ok\n"
    sha = hashlib.sha256(body).hexdigest()
    blob_path = f"blobs/sha256/{sha[:2]}/{sha}"
    factory = get_session_factory()
    async with factory() as session:
        session.add(File(
            id=file_id,
            storage_key=storage_key,
            sha256=sha,
            size_bytes=len(body),
            mime_type="text/plain",
            original_ext=".txt",
            kind="text",
            ingest_status="done",
            ingested_at=now,
            created_at=now,
            updated_at=now,
            description={
                "_webdav_remote": {
                    "remote_root": "/evil-other-library",
                    "blob_path": blob_path,
                    "sha256": sha,
                    "hydrated": False,
                },
            },
        ))
        await session.flush()
        session.add(FileEntry(
            id=entry_id,
            folder_id=None,
            file_id=file_id,
            display_name="ok.txt",
            lifecycle="active",
            created_at=now,
            updated_at=now,
        ))
        await session.commit()

    _MemoryWebDavClient.remote[_REMOTE_ROOT + "/" + blob_path] = body
    hydrated = await hydrate_entry(entry_id)
    assert hydrated["hydrated"] is True
    assert _MemoryWebDavClient.captured_stream_path == f"{_REMOTE_ROOT}/{blob_path}"
    assert "evil-other-library" not in (_MemoryWebDavClient.captured_stream_path or "")


async def test_hydrate_rejects_hostile_blob_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = _TEST_ROOT / "hydrate_blob"
    _use_memory_client(monkeypatch)
    await _activate_home(home)

    now = datetime.now(timezone.utc)
    file_id = new_id()
    entry_id = new_id()
    storage_key = f"seed/{file_id}"
    sha = "ab" * 32
    factory = get_session_factory()
    async with factory() as session:
        session.add(File(
            id=file_id,
            storage_key=storage_key,
            sha256=sha,
            size_bytes=3,
            mime_type="text/plain",
            original_ext=".txt",
            kind="text",
            ingest_status="done",
            ingested_at=now,
            created_at=now,
            updated_at=now,
            description={
                "_webdav_remote": {
                    "remote_root": _REMOTE_ROOT,
                    "blob_path": "../Photos/secret.bin",
                    "sha256": sha,
                    "hydrated": False,
                },
            },
        ))
        await session.flush()
        session.add(FileEntry(
            id=entry_id,
            folder_id=None,
            file_id=file_id,
            display_name="ok.txt",
            lifecycle="active",
            created_at=now,
            updated_at=now,
        ))
        await session.commit()

    with pytest.raises(WebDavConfigError, match="blob_path"):
        await hydrate_entry(entry_id)


# ---------------------------------------------------------------------------
# WEBDAV-M2 — redact credentials in persisted status
# ---------------------------------------------------------------------------


def test_redact_error_strips_embedded_credentials() -> None:
    url_exc = RuntimeError("GET https://user:pass@dav.example/library failed with 401")
    redacted = _redact_error(url_exc)
    assert "user:pass@" not in redacted
    assert "https://user:pass@dav.example/library" not in redacted
    assert "<url>" in redacted

    userinfo_exc = RuntimeError("proxy user:pass@internal.example timed out")
    userinfo = _redact_error(userinfo_exc)
    assert "user:pass@" not in userinfo
    assert "<redacted>" in userinfo


def test_write_status_redacts_error_and_remote_error_fields() -> None:
    home = _TEST_ROOT / "status_redact"
    home.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        library_home=str(home),
        webdav_url="https://dav.test",
        webdav_remote_path="/library-test",
    )
    _write_status(settings, {
        "status": "failed",
        "error": "PUT https://alice:s3cret@dav.example/library failed",
        "remote_error": "HEAD user:token@files.example timed out",
    })
    written = json.loads(_status_path(settings).read_text(encoding="utf-8"))
    blob = json.dumps(written)
    assert "alice:s3cret@" not in blob
    assert "user:token@" not in blob
    assert written["error"]
    assert written["remote_error"]
    assert "<url>" in written["error"] or "<redacted>" in written["error"]
    assert "<redacted>" in written["remote_error"]


# ---------------------------------------------------------------------------
# WEBDAV-M3 — coerce/skip bad CHECK fields
# ---------------------------------------------------------------------------


def test_as_int_coerces_or_defaults_unparseable_size() -> None:
    assert _as_int(12) == 12
    assert _as_int("12") == 12
    assert _as_int("10MB", 0) == 0
    assert _as_int(None, 0) == 0
    assert _as_int("", 0) == 0


async def test_import_skips_illegal_check_fields_and_keeps_legal_rows() -> None:
    home = _TEST_ROOT / "import_checks"
    await _activate_home(home)

    legal_entry_id = new_id()
    legal_file_id = new_id()
    evil_lifecycle_entry_id = new_id()
    evil_lifecycle_file_id = new_id()
    size_entry_id = new_id()
    size_file_id = new_id()
    catalog_entry_id = new_id()
    catalog_file_id = new_id()
    dangling_catalog_id = new_id()
    live_catalog_id = new_id()
    live_catalog_entry_id = new_id()
    live_catalog_file_id = new_id()
    legal_relation_id = new_id()
    illegal_relation_id = new_id()
    default_relation_id = new_id()
    second_entry_id = new_id()
    second_file_id = new_id()
    tag_id = new_id()
    illegal_tag_id = new_id()

    now_iso = _now_iso()
    rows = _empty_rows()
    rows["catalogs.jsonl"] = [{
        "catalog_id": live_catalog_id,
        "parent_id": None,
        "name": "Papers",
        "created_at": now_iso,
        "updated_at": now_iso,
    }]
    rows["tags.jsonl"] = [
        {
            "tag_id": tag_id,
            "name": "webdav",
            "facet": "topic",
            "created_at": now_iso,
            "updated_at": now_iso,
            "doc_count": 1,
        },
        {
            "tag_id": illegal_tag_id,
            "name": "evil",
            "facet": "not-a-facet",
            "created_at": now_iso,
            "updated_at": now_iso,
            "doc_count": 1,
        },
    ]
    rows["entries.jsonl"] = [
        _entry_row(
            entry_id=legal_entry_id,
            file_id=legal_file_id,
            tags=[{"tag_id": tag_id, "source": "ingest", "created_at": now_iso}],
        ),
        _entry_row(
            entry_id=second_entry_id,
            file_id=second_file_id,
        ),
        _entry_row(
            entry_id=evil_lifecycle_entry_id,
            file_id=evil_lifecycle_file_id,
            lifecycle="evil",
        ),
        _entry_row(
            entry_id=size_entry_id,
            file_id=size_file_id,
            size_bytes="10MB",
        ),
        _entry_row(
            entry_id=catalog_entry_id,
            file_id=catalog_file_id,
            catalog_id=dangling_catalog_id,
        ),
        _entry_row(
            entry_id=live_catalog_entry_id,
            file_id=live_catalog_file_id,
            catalog_id=live_catalog_id,
        ),
    ]
    rows["relations.jsonl"] = [
        {
            "relation_id": legal_relation_id,
            "entry_a_id": legal_entry_id,
            "entry_b_id": second_entry_id,
            "note": "same topic",
            "source_kind": "mine_tag_overlap",
            "created_at": now_iso,
            "last_observed_at": now_iso,
            "observation_count": 1,
        },
        {
            "relation_id": illegal_relation_id,
            "entry_a_id": legal_entry_id,
            "entry_b_id": second_entry_id,
            "note": "old default",
            "source_kind": "mine_relations",
            "created_at": now_iso,
            "last_observed_at": now_iso,
            "observation_count": 1,
        },
        {
            "relation_id": default_relation_id,
            "entry_a_id": legal_entry_id,
            "entry_b_id": second_entry_id,
            "note": "missing source_kind uses old illegal default",
            "created_at": now_iso,
            "last_observed_at": now_iso,
            "observation_count": 1,
        },
    ]

    factory = get_session_factory()
    async with factory() as session:
        imported = await _import_metadata(
            session,
            root=_REMOTE_ROOT,
            latest={"library_id": "unit-library", "snapshot_id": _SNAPSHOT_ID},
            manifest=_manifest(),
            rows=rows,  # type: ignore[arg-type]
        )
        await session.commit()

    assert imported["entries"] >= 4
    assert imported["catalogs"] == 1
    assert imported["tags"] == 1
    assert imported["relations"] == 1
    assert imported["conflicts"] >= 4

    async with factory() as session:
        legal = await session.get(FileEntry, legal_entry_id)
        assert legal is not None
        assert legal.lifecycle == "active"

        assert await session.get(FileEntry, evil_lifecycle_entry_id) is None

        sized = await session.get(File, size_file_id)
        assert sized is not None
        assert sized.size_bytes == 0
        sized_entry = await session.get(FileEntry, size_entry_id)
        assert sized_entry is not None

        dangling = await session.get(FileEntry, catalog_entry_id)
        assert dangling is not None
        assert dangling.catalog_id is None

        live_catalog = await session.get(Catalog, live_catalog_id)
        assert live_catalog is not None
        attached = await session.get(FileEntry, live_catalog_entry_id)
        assert attached is not None
        assert attached.catalog_id == live_catalog_id

        assert await session.get(Tag, illegal_tag_id) is None
        assert await session.get(Tag, tag_id) is not None

        legal_rel = await session.get(EntryRelation, legal_relation_id)
        assert legal_rel is not None
        assert legal_rel.source_kind == "mine_tag_overlap"

        assert await session.get(EntryRelation, illegal_relation_id) is None
        assert await session.get(EntryRelation, default_relation_id) is None

        kinds = (
            await session.execute(select(EntryRelation.source_kind))
        ).scalars().all()
        assert "mine_relations" not in kinds
