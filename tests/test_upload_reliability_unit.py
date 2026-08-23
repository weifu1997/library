from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from library.api import routes_upload
from library.capacity import CapacityExceeded
from library.config import Settings
from library.db.bootstrap import bootstrap_schema_sync
from library.db.models import File
from library.db.models.tasks import Task
from library.services.upload import UploadResult, upload
from library.storage import s3 as s3_module
from library.storage.local import LocalStorage
from library.storage.s3 import S3Storage
from library.tasks.kinds import KIND_INGEST_FILE, KIND_REFRESH_SEMANTIC_FILE
from library import upload_limits
from library.utils.ids import new_id


async def _chunks(*values: bytes) -> AsyncIterator[bytes]:
    for value in values:
        yield value


class _FakeS3Client:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def put_object(self, **kwargs: Any) -> None:
        self.calls.append(("put", kwargs))

    async def create_multipart_upload(self, **kwargs: Any) -> dict[str, str]:
        self.calls.append(("create", kwargs))
        return {"UploadId": "upload-1"}

    async def upload_part(self, **kwargs: Any) -> dict[str, str]:
        self.calls.append(("part", kwargs))
        return {"ETag": f"etag-{kwargs['PartNumber']}"}

    async def complete_multipart_upload(self, **kwargs: Any) -> None:
        self.calls.append(("complete", kwargs))

    async def abort_multipart_upload(self, **kwargs: Any) -> None:
        self.calls.append(("abort", kwargs))


class _FakeClientContext:
    def __init__(self, client: _FakeS3Client) -> None:
        self.client = client

    async def __aenter__(self) -> _FakeS3Client:
        return self.client

    async def __aexit__(self, *_args: Any) -> None:
        return None


def _fake_s3(client: _FakeS3Client) -> S3Storage:
    storage = object.__new__(S3Storage)
    storage.bucket = "bucket"
    storage._client = lambda: _FakeClientContext(client)  # type: ignore[method-assign]
    return storage


@pytest.mark.asyncio
async def test_s3_put_is_bounded_and_aborts_failed_multipart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(s3_module, "_MULTIPART_PART_SIZE", 4)
    client = _FakeS3Client()
    await _fake_s3(client).put(
        "object",
        _chunks(b"abc", b"defghi"),
        content_type="text/plain",
    )
    assert [name for name, _ in client.calls] == [
        "create", "part", "part", "part", "complete",
    ]
    assert [kwargs["Body"] for name, kwargs in client.calls if name == "part"] == [
        b"abcd", b"efgh", b"i",
    ]

    failed_client = _FakeS3Client()

    async def failed_stream() -> AsyncIterator[bytes]:
        yield b"abcd"
        raise RuntimeError("read failed")

    with pytest.raises(RuntimeError, match="read failed"):
        await _fake_s3(failed_client).put("object", failed_stream())
    assert [name for name, _ in failed_client.calls][-1] == "abort"


@pytest.mark.asyncio
async def test_local_put_removes_partial_file_after_stream_failure(
    tmp_path: Path,
) -> None:
    storage = LocalStorage(tmp_path)

    async def failed_stream() -> AsyncIterator[bytes]:
        yield b"partial"
        raise RuntimeError("read failed")

    with pytest.raises(RuntimeError, match="read failed"):
        await storage.put("objects/file", failed_stream())
    assert not (tmp_path / "objects" / "file").exists()
    assert not (tmp_path / "objects" / "file.part").exists()


def _multipart_body(file_bytes: bytes, *, metadata: bytes = b"") -> tuple[bytes, bytes]:
    boundary = b"upload-limit-boundary"
    body = b"".join([
        b"--" + boundary + b"\r\n",
        b'Content-Disposition: form-data; name="metadata"\r\n\r\n',
        metadata,
        b"\r\n--" + boundary + b"\r\n",
        b'Content-Disposition: form-data; name="file"; filename="a.txt"\r\n',
        b"Content-Type: text/plain\r\n\r\n",
        file_bytes,
        b"\r\n--" + boundary + b"--\r\n",
    ])
    return boundary, body


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("file_bytes", "expected_status"),
    [(b"1234", 204), (b"12345", 413)],
)
async def test_upload_middleware_counts_file_bytes_before_spooling(
    monkeypatch: pytest.MonkeyPatch,
    file_bytes: bytes,
    expected_status: int,
) -> None:
    monkeypatch.setattr(
        upload_limits,
        "get_settings",
        lambda: SimpleNamespace(upload_max_bytes=4),
    )
    boundary, body = _multipart_body(file_bytes, metadata=b"m" * 32_000)
    chunks = [body[pos:pos + 7] for pos in range(0, len(body), 7)]
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        chunk = chunks.pop(0)
        return {
            "type": "http.request",
            "body": chunk,
            "more_body": bool(chunks),
        }

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    async def downstream(_scope, wrapped_receive, wrapped_send) -> None:
        while True:
            message = await wrapped_receive()
            if not message.get("more_body", False):
                break
        await wrapped_send({"type": "http.response.start", "status": 204, "headers": []})
        await wrapped_send({"type": "http.response.body", "body": b""})

    middleware = upload_limits.UploadSizeLimitMiddleware(downstream)
    await middleware(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/upload",
            "headers": [
                (b"content-type", b"multipart/form-data; boundary=" + boundary),
            ],
        },
        receive,
        send,
    )

    assert sent[0]["status"] == expected_status


@pytest.mark.asyncio
async def test_upload_middleware_rejects_impossible_raw_size_without_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        upload_limits,
        "get_settings",
        lambda: SimpleNamespace(upload_max_bytes=10),
    )
    received = False
    downstream_called = False
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        nonlocal received
        received = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    async def downstream(_scope, _receive, _send) -> None:
        nonlocal downstream_called
        downstream_called = True

    raw_size = 10 + upload_limits.MULTIPART_NON_FILE_BUDGET + 1
    middleware = upload_limits.UploadSizeLimitMiddleware(downstream)
    await middleware(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/upload",
            "headers": [(b"content-length", str(raw_size).encode("ascii"))],
        },
        receive,
        send,
    )

    assert sent[0]["status"] == 413
    assert received is False
    assert downstream_called is False


async def _upload_db(tmp_path: Path, name: str):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / name}")
    async with engine.begin() as connection:
        await connection.run_sync(bootstrap_schema_sync)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_upload_does_not_deduplicate_against_soft_deleted_file(
    tmp_path: Path,
) -> None:
    engine, factory = await _upload_db(tmp_path, "soft-deleted.db")
    storage = LocalStorage(tmp_path / "objects")
    # Use the model's normal datetime defaults for the historical row; only
    # deleted_at matters to this regression.
    deleted_at = datetime.now(timezone.utc)
    old_file_id = new_id()
    try:
        async with factory() as session:
            session.add(File(
                id=old_file_id,
                storage_key="old/object",
                sha256="a" * 64,
                size_bytes=7,
                ingest_status="done",
                ingested_at=deleted_at,
                deleted_at=deleted_at,
                created_at=deleted_at,
                updated_at=deleted_at,
            ))
            await session.commit()

        # Match the historical row's hash exactly without depending on a
        # preimage for the fixture value.
        body = b"fresh replacement"

        async with factory() as session:
            old = await session.get(File, old_file_id)
            assert old is not None
            old.sha256 = hashlib.sha256(body).hexdigest()
            await session.commit()

        async with factory() as session:
            result = await upload(
                session,
                storage,
                stream=_chunks(body),
                fallback_name="replacement.txt",
                remote_path="/replacement.txt",
                content_type="text/plain",
            )
            await session.commit()

        assert result.deduped is False
        assert result.file_id != old_file_id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("ingest_status", "expected_kind"),
    [
        ("failed", KIND_INGEST_FILE),
        ("done", KIND_REFRESH_SEMANTIC_FILE),
    ],
)
async def test_deduplicated_upload_schedules_required_follow_up(
    tmp_path: Path,
    ingest_status: str,
    expected_kind: str,
) -> None:
    engine, factory = await _upload_db(tmp_path, f"dedup-{ingest_status}.db")
    storage = LocalStorage(tmp_path / f"objects-{ingest_status}")
    now = datetime.now(timezone.utc)
    body = b"shared upload body"
    file_id = new_id()
    try:
        async with factory() as session:
            session.add(File(
                id=file_id,
                storage_key="existing/object",
                sha256=hashlib.sha256(body).hexdigest(),
                size_bytes=len(body),
                mime_type="text/plain",
                original_ext=".txt",
                kind="text" if ingest_status == "done" else None,
                summary="Existing summary" if ingest_status == "done" else None,
                description={"sections": []} if ingest_status == "done" else None,
                ingest_status=ingest_status,
                ingested_at=now if ingest_status == "done" else None,
                deleted_at=None,
                created_at=now,
                updated_at=now,
            ))
            await session.commit()

        async with factory() as session:
            result = await upload(
                session,
                storage,
                stream=_chunks(body),
                fallback_name="copy.txt",
                remote_path="/copy.txt",
                content_type="text/plain",
            )
            await session.commit()

        async with factory() as session:
            task = (
                await session.execute(
                    select(Task).where(Task.kind == expected_kind)
                )
            ).scalar_one()
            stored = await session.get(File, file_id)

        assert result.deduped is True
        assert result.file_id == file_id
        assert task.payload["file_id"] == file_id
        assert task.status == "pending"
        assert stored is not None
        assert stored.ingest_status == ("pending" if ingest_status == "failed" else "done")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_new_upload_capacity_rejects_and_removes_written_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, factory = await _upload_db(tmp_path, "capacity.db")
    storage = LocalStorage(tmp_path / "capacity-objects")
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(
        "library.services.upload.get_settings",
        lambda: Settings(library_document_limit=1),
    )
    try:
        async with factory() as session:
            session.add(File(
                id=new_id(),
                storage_key="existing/object",
                sha256=hashlib.sha256(b"existing").hexdigest(),
                size_bytes=8,
                ingest_status="done",
                ingested_at=now,
                deleted_at=None,
                created_at=now,
                updated_at=now,
            ))
            await session.commit()

        async with factory() as session:
            with pytest.raises(CapacityExceeded):
                await upload(
                    session,
                    storage,
                    stream=_chunks(b"new body"),
                    fallback_name="new.txt",
                    remote_path="/new.txt",
                    content_type="text/plain",
                )
            await session.rollback()

        async with factory() as session:
            assert len((await session.execute(select(File))).scalars().all()) == 1
        assert not any(path.is_file() for path in (tmp_path / "capacity-objects").rglob("*"))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_deduplicated_upload_does_not_consume_document_capacity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, factory = await _upload_db(tmp_path, "dedup-capacity.db")
    storage = LocalStorage(tmp_path / "dedup-capacity-objects")
    now = datetime.now(timezone.utc)
    body = b"same body"
    file_id = new_id()
    monkeypatch.setattr(
        "library.services.upload.get_settings",
        lambda: Settings(library_document_limit=1),
    )
    try:
        async with factory() as session:
            session.add(File(
                id=file_id,
                storage_key="existing/object",
                sha256=hashlib.sha256(body).hexdigest(),
                size_bytes=len(body),
                kind="text",
                summary="ready",
                description={"sections": []},
                ingest_status="done",
                ingested_at=now,
                deleted_at=None,
                created_at=now,
                updated_at=now,
            ))
            await session.commit()

        async with factory() as session:
            result = await upload(
                session,
                storage,
                stream=_chunks(body),
                fallback_name="copy.txt",
                remote_path="/copy.txt",
                content_type="text/plain",
            )
            await session.commit()
        assert result.deduped is True
        assert result.file_id == file_id
    finally:
        await engine.dispose()


class _FakeStorage:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def delete(self, key: str) -> None:
        self.deleted.append(key)


class _FailedCommitSession:
    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.rolled_back = False

    async def commit(self) -> None:
        raise self.error

    async def rollback(self) -> None:
        self.rolled_back = True


class _ScalarResult:
    def __init__(self, value: str | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> str | None:
        return self.value


class _VerificationSession:
    def __init__(self, referenced: str | None) -> None:
        self.referenced = referenced

    async def execute(self, _statement: Any) -> _ScalarResult:
        return _ScalarResult(self.referenced)


def _result() -> UploadResult:
    return UploadResult(
        file_id="file-1",
        entry_id="entry-1",
        folder_id=None,
        display_name="file.txt",
        deduped=False,
        auto_renamed=False,
        storage_key="objects/file-1",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("referenced", "expected_deleted"),
    [(None, ["objects/file-1"]), ("file-1", [])],
)
async def test_failed_upload_commit_deletes_only_an_unreferenced_object(
    monkeypatch: pytest.MonkeyPatch,
    referenced: str | None,
    expected_deleted: list[str],
) -> None:
    @asynccontextmanager
    async def verification_scope():
        yield _VerificationSession(referenced)

    monkeypatch.setattr(routes_upload, "session_scope", verification_scope)
    session = _FailedCommitSession(RuntimeError("commit failed"))
    storage = _FakeStorage()
    with pytest.raises(RuntimeError, match="commit failed"):
        await routes_upload._commit_upload(  # type: ignore[arg-type]
            session,
            storage,
            _result(),
        )
    assert session.rolled_back
    assert storage.deleted == expected_deleted


@pytest.mark.asyncio
async def test_cancelled_upload_commit_preserves_object() -> None:
    session = _FailedCommitSession(asyncio.CancelledError())
    storage = _FakeStorage()
    with pytest.raises(asyncio.CancelledError):
        await routes_upload._commit_upload(  # type: ignore[arg-type]
            session,
            storage,
            _result(),
        )
    assert session.rolled_back
    assert storage.deleted == []
