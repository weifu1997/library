"""INGEST-M3 — archive ingest must record sampled coverage."""
from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace

import pytest

from library.pipelines.archive import (
    ArchivePipeline,
    PEEK_MEMBERS_MAX_FOR_TINY,
    _archive_coverage,
)
from library.pipelines.base import PipelineContext


class _MemoryStorage:
    def __init__(self, body: bytes) -> None:
        self.body = body

    async def get(self, key: str):
        del key
        yield self.body


def _zip_with_n_text_members(n: int) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i in range(n):
            zf.writestr(f"file-{i:02d}.txt", f"content {i}\n")
    return buf.getvalue()


def _ctx() -> PipelineContext:
    return PipelineContext(
        file_id="file-id",
        storage_key="file-key",
        sha256="sha",
        size_bytes=10,
        mime_type="application/zip",
        original_ext=".zip",
        folder_path="/",
        sibling_names=[],
        display_name="bundle.zip",
    )


def test_archive_coverage_marks_peek_cap() -> None:
    peeks = [{"path": f"f{i}.txt", "preview": "ok"} for i in range(8)]
    coverage = _archive_coverage(file_count=20, peeks=peeks)
    assert coverage["indexed_partial"] is True
    assert coverage["indexed_units"] == 8
    assert coverage["total_units"] == 20
    assert coverage["partial_reasons"] == ["archive_peek_cap"]
    assert coverage["peek_failures"] == 0


def test_archive_coverage_marks_peek_failures() -> None:
    peeks = [
        {"path": "a.txt", "preview": "hello"},
        {"path": "b.txt", "preview": "[read failed: boom]"},
        {"path": "c.txt", "preview": "[peek failed: timeout]"},
    ]
    coverage = _archive_coverage(file_count=3, peeks=peeks)
    assert coverage["indexed_partial"] is True
    assert coverage["partial_reasons"] == ["archive_peek_failures"]
    assert coverage["peek_failures"] == 2


def test_archive_coverage_complete_when_all_members_peeked() -> None:
    peeks = [{"path": "a.txt", "preview": "hello"}]
    coverage = _archive_coverage(file_count=1, peeks=peeks)
    assert coverage["indexed_partial"] is False
    assert coverage["partial_reasons"] == []
    assert coverage["peek_failures"] == 0


@pytest.mark.asyncio
async def test_archive_ingest_writes_coverage_when_capped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import library.pipelines.archive as mod

    class FakeIngest:
        async def complete(self, request):  # noqa: ARG002
            return SimpleNamespace(text="""<summary>
A bundle of text files.
</summary>
<description>
Sample archive.
</description>
<extra>
</extra>
<entry_extra>
</entry_extra>
<catalog_path>
</catalog_path>
<tags>
form: archive
</tags>
""")

    monkeypatch.setattr(mod, "get_chat_client", lambda profile: FakeIngest())
    n = PEEK_MEMBERS_MAX_FOR_TINY + 4
    result = await ArchivePipeline().run(
        ctx=_ctx(),
        storage=_MemoryStorage(_zip_with_n_text_members(n)),
    )
    coverage = result.description["coverage"]
    assert coverage["indexed_partial"] is True
    assert "archive_peek_cap" in coverage["partial_reasons"]
    assert coverage["indexed_units"] == PEEK_MEMBERS_MAX_FOR_TINY
    assert coverage["total_units"] == n
    assert "indexed_coverage:" in (result.extra or "")
