from __future__ import annotations

from typing import Any, AsyncIterator

import aioboto3
from botocore.exceptions import ClientError

from library.storage.base import StorageBackend

_CHUNK = 1024 * 256
_MULTIPART_PART_SIZE = 8 * 1024 * 1024


class S3Storage(StorageBackend):
    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str = "us-east-1",
    ) -> None:
        self.bucket = bucket
        self._session = aioboto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        self._endpoint_url = endpoint_url

    def _client(self):  # type: ignore[no-untyped-def]
        return self._session.client("s3", endpoint_url=self._endpoint_url)

    async def check_ready(self) -> None:
        async with self._client() as s3:
            await s3.head_bucket(Bucket=self.bucket)

    async def put(
        self,
        key: str,
        stream: AsyncIterator[bytes],
        *,
        size: int | None = None,
        content_type: str | None = None,
        display_name: str | None = None,
        folder_path: str | None = None,
    ) -> str:
        upload_id: str | None = None
        parts: list[dict[str, object]] = []
        buffer = bytearray()
        async with self._client() as s3:
            try:
                async for chunk in stream:
                    if not chunk:
                        continue
                    buffer.extend(chunk)
                    if upload_id is None and len(buffer) >= _MULTIPART_PART_SIZE:
                        create_kwargs: dict[str, object] = {
                            "Bucket": self.bucket,
                            "Key": key,
                        }
                        if content_type:
                            create_kwargs["ContentType"] = content_type
                        created = await s3.create_multipart_upload(**create_kwargs)
                        upload_id = str(created["UploadId"])
                    while (
                        upload_id is not None
                        and len(buffer) >= _MULTIPART_PART_SIZE
                    ):
                        body = bytes(buffer[:_MULTIPART_PART_SIZE])
                        del buffer[:_MULTIPART_PART_SIZE]
                        parts.append(await self._upload_part(
                            s3,
                            key=key,
                            upload_id=upload_id,
                            part_number=len(parts) + 1,
                            body=body,
                        ))

                if upload_id is None:
                    kwargs: dict[str, object] = {
                        "Bucket": self.bucket,
                        "Key": key,
                        "Body": bytes(buffer),
                    }
                    if content_type:
                        kwargs["ContentType"] = content_type
                    await s3.put_object(**kwargs)
                    return key

                if buffer:
                    parts.append(await self._upload_part(
                        s3,
                        key=key,
                        upload_id=upload_id,
                        part_number=len(parts) + 1,
                        body=bytes(buffer),
                    ))
                await s3.complete_multipart_upload(
                    Bucket=self.bucket,
                    Key=key,
                    UploadId=upload_id,
                    MultipartUpload={"Parts": parts},
                )
            except BaseException:
                if upload_id is not None:
                    try:
                        await s3.abort_multipart_upload(
                            Bucket=self.bucket,
                            Key=key,
                            UploadId=upload_id,
                        )
                    except Exception:
                        # Preserve the original read/upload failure. Bucket
                        # lifecycle rules can expire a rare abandoned upload.
                        pass
                raise
        return key

    async def _upload_part(
        self,
        client: Any,
        *,
        key: str,
        upload_id: str,
        part_number: int,
        body: bytes,
    ) -> dict[str, object]:
        response = await client.upload_part(
            Bucket=self.bucket,
            Key=key,
            UploadId=upload_id,
            PartNumber=part_number,
            Body=body,
        )
        return {"ETag": response["ETag"], "PartNumber": part_number}

    async def rename(self, old_key: str, new_key: str) -> str:
        # UUID-flat: rename is a no-op. Storage key never changes for
        # objects already addressed by UUID.
        return old_key

    async def get(self, key: str) -> AsyncIterator[bytes]:
        async with self._client() as s3:
            obj = await s3.get_object(Bucket=self.bucket, Key=key)
            async with obj["Body"] as body:
                while True:
                    chunk = await body.read(_CHUNK)
                    if not chunk:
                        return
                    yield chunk

    async def get_range(self, key: str, start: int, end: int) -> bytes:
        async with self._client() as s3:
            obj = await s3.get_object(
                Bucket=self.bucket, Key=key, Range=f"bytes={start}-{end}"
            )
            async with obj["Body"] as body:
                return await body.read()

    async def delete(self, key: str) -> None:
        async with self._client() as s3:
            await s3.delete_object(Bucket=self.bucket, Key=key)

    async def exists(self, key: str) -> bool:
        async with self._client() as s3:
            try:
                await s3.head_object(Bucket=self.bucket, Key=key)
                return True
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code")
                if code in {"404", "NoSuchKey", "NotFound"}:
                    return False
                raise
