from __future__ import annotations

from hashlib import sha256
from typing import Any, Mapping

from sqlalchemy import select

from library.config import get_settings
from library.db.models import File
from library.db.session import session_scope
from library.repositories.task_outcomes import record_outcome
from library.storage.base import StorageBackend
from library.storage.local import LocalStorage
from library.storage.mirror import MirrorStorage
from library.storage.s3 import S3Storage
from library.tasks.kinds import KIND_DELETE_STORAGE_OBJECT, task_handler


def _storage_from_payload(payload: Mapping[str, Any]) -> StorageBackend:
    backend = str(payload.get("storage_backend") or "").strip().lower()
    if backend in {"local", "mirror"}:
        root = str(payload.get("storage_root") or "").strip()
        if not root:
            raise RuntimeError("storage deletion payload is missing storage_root")
        return LocalStorage(root) if backend == "local" else MirrorStorage(root)
    if backend == "s3":
        bucket = str(payload.get("bucket") or "").strip()
        if not bucket:
            raise RuntimeError("storage deletion payload is missing bucket")
        settings = get_settings()
        return S3Storage(
            bucket=bucket,
            endpoint_url=str(payload.get("endpoint_url") or "") or None,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            region=str(payload.get("region") or settings.s3_region),
        )
    raise RuntimeError("storage deletion payload has an invalid backend")


@task_handler(KIND_DELETE_STORAGE_OBJECT)
async def handle_delete_storage_object(payload: Mapping[str, Any]) -> None:
    storage_key = str(payload.get("storage_key") or "").strip()
    if not storage_key:
        raise RuntimeError("storage deletion payload is missing storage_key")
    target_id = sha256("\0".join((
        str(payload.get("storage_backend") or ""),
        str(payload.get("storage_root") or ""),
        str(payload.get("bucket") or ""),
        str(payload.get("endpoint_url") or ""),
        storage_key,
    )).encode("utf-8")).hexdigest()

    async with session_scope() as session:
        referenced = (
            await session.execute(
                select(File.id).where(File.storage_key == storage_key).limit(1)
            )
        ).scalar_one_or_none()
        if referenced is not None:
            await record_outcome(
                session,
                task_kind=KIND_DELETE_STORAGE_OBJECT,
                object_kind="storage_object",
                object_id=target_id,
                task_run_id=str(payload.get("_task_id") or "") or None,
                outcome="noop",
                detail={
                    "storage_key": storage_key,
                    "reason": "file_reference_present",
                },
            )
            await session.commit()
            return

    storage = _storage_from_payload(payload)
    async with session_scope() as session:
        referenced = (
            await session.execute(
                select(File.id).where(File.storage_key == storage_key).limit(1)
            )
        ).scalar_one_or_none()
        if referenced is not None:
            await record_outcome(
                session,
                task_kind=KIND_DELETE_STORAGE_OBJECT,
                object_kind="storage_object",
                object_id=target_id,
                task_run_id=str(payload.get("_task_id") or "") or None,
                outcome="noop",
                detail={
                    "storage_key": storage_key,
                    "reason": "file_reference_present",
                },
            )
            await session.commit()
            return

    await storage.delete(storage_key)

    async with session_scope() as session:
        await record_outcome(
            session,
            task_kind=KIND_DELETE_STORAGE_OBJECT,
            object_kind="storage_object",
            object_id=target_id,
            task_run_id=str(payload.get("_task_id") or "") or None,
            outcome="applied",
            detail={"storage_key": storage_key},
        )
        await session.commit()
