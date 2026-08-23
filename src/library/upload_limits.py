"""ASGI upload limits applied before multipart bodies are spooled."""
from __future__ import annotations

import json
from typing import Any

from python_multipart.multipart import MultipartParser, parse_options_header

from library.config import get_settings

_UPLOAD_PATHS = frozenset({"/v1/upload"})
# Bound field names, query metadata, boundaries, and part headers separately
# from file content. The multipart observer counts file bytes exactly.
MULTIPART_NON_FILE_BUDGET = 256 * 1024


class _UploadTooLargeAbort(Exception):
    pass


class _MultipartFileByteObserver:
    """Count file-part bytes incrementally without retaining content."""

    def __init__(self, boundary: bytes, *, max_file_bytes: int) -> None:
        self.max_file_bytes = max_file_bytes
        self.file_bytes = 0
        self._header_field = bytearray()
        self._header_value = bytearray()
        self._headers: dict[bytes, bytes] = {}
        self._is_file_part = False
        self._parser = MultipartParser(
            boundary,
            callbacks={
                "on_part_begin": self._on_part_begin,
                "on_header_field": self._on_header_field,
                "on_header_value": self._on_header_value,
                "on_header_end": self._on_header_end,
                "on_headers_finished": self._on_headers_finished,
                "on_part_data": self._on_part_data,
            },
        )

    def write(self, body: bytes) -> None:
        self._parser.write(body)

    def finalize(self) -> None:
        self._parser.finalize()

    def _on_part_begin(self) -> None:
        self._header_field.clear()
        self._header_value.clear()
        self._headers.clear()
        self._is_file_part = False

    def _on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._header_field.extend(data[start:end])

    def _on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._header_value.extend(data[start:end])

    def _on_header_end(self) -> None:
        key = bytes(self._header_field).strip().lower()
        if key:
            self._headers[key] = bytes(self._header_value).strip()
        self._header_field.clear()
        self._header_value.clear()

    def _on_headers_finished(self) -> None:
        _disposition, options = parse_options_header(
            self._headers.get(b"content-disposition", b"")
        )
        self._is_file_part = b"filename" in options

    def _on_part_data(self, data: bytes, start: int, end: int) -> None:
        del data
        if not self._is_file_part:
            return
        self.file_bytes += end - start
        if self.file_bytes > self.max_file_bytes:
            raise _UploadTooLargeAbort()


class UploadSizeLimitMiddleware:
    """Reject oversized uploads before Starlette creates temporary files."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if (
            scope.get("type") != "http"
            or scope.get("method") != "POST"
            or scope.get("path") not in _UPLOAD_PATHS
        ):
            await self.app(scope, receive, send)
            return

        max_bytes = int(get_settings().upload_max_bytes or 0)
        if max_bytes <= 0:
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers") or []}
        raw_limit = max_bytes + MULTIPART_NON_FILE_BUDGET
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > raw_limit:
                    await self._reject(send, max_bytes)
                    return
            except ValueError:
                pass

        observer = self._observer(headers.get(b"content-type"), max_bytes=max_bytes)
        raw_bytes = 0
        response_started = False
        oversized = False

        async def counting_receive() -> dict[str, Any]:
            nonlocal observer, oversized, raw_bytes
            message = await receive()
            if message.get("type") != "http.request":
                return message
            body = message.get("body", b"")
            raw_bytes += len(body)
            if raw_bytes > raw_limit:
                oversized = True
                raise _UploadTooLargeAbort()
            if observer is not None and body:
                try:
                    observer.write(body)
                except _UploadTooLargeAbort:
                    oversized = True
                    raise
                except Exception:
                    # Starlette should report malformed multipart syntax; the
                    # independent raw ceiling still protects temporary space.
                    observer = None
            if observer is not None and not message.get("more_body", False):
                try:
                    observer.finalize()
                except _UploadTooLargeAbort:
                    oversized = True
                    raise
                except Exception:
                    observer = None
            return message

        async def watching_send(message: dict[str, Any]) -> None:
            nonlocal response_started
            # Request-form parsing may translate a receive exception into a
            # 400 response. Once the byte observer has proved the file is too
            # large, suppress that downstream response and emit the canonical
            # 413 after the parser has unwound and closed its temporary files.
            if oversized:
                return
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, watching_send)
            if oversized and not response_started:
                await self._reject(send, max_bytes)
        except _UploadTooLargeAbort:
            if not response_started:
                await self._reject(send, max_bytes)

    @staticmethod
    def _observer(
        content_type: bytes | None,
        *,
        max_bytes: int,
    ) -> _MultipartFileByteObserver | None:
        if not content_type:
            return None
        media_type, options = parse_options_header(content_type)
        boundary = options.get(b"boundary")
        if media_type != b"multipart/form-data" or not boundary:
            return None
        return _MultipartFileByteObserver(boundary, max_file_bytes=max_bytes)

    @staticmethod
    async def _reject(send: Any, max_bytes: int) -> None:
        body = json.dumps(
            {"detail": {"error": "upload_too_large", "max_bytes": max_bytes}},
            separators=(",", ":"),
        ).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        })
        await send({"type": "http.response.body", "body": body})


__all__ = ["MULTIPART_NON_FILE_BUDGET", "UploadSizeLimitMiddleware"]
