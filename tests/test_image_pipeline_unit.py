from __future__ import annotations

import pytest

from library.pipelines.base import PipelineContext
from library.pipelines.image import ImagePipeline


class _MemoryStorage:
    def __init__(self, body: bytes) -> None:
        self.body = body

    async def get(self, key: str):
        assert key == "image-key"
        yield self.body


def _ctx(name: str = "scan.tiff") -> PipelineContext:
    return PipelineContext(
        file_id="file-id",
        storage_key="image-key",
        sha256="sha",
        size_bytes=123,
        mime_type="image/tiff",
        original_ext=".tiff",
        folder_path="/",
        sibling_names=[],
        display_name=name,
    )


@pytest.mark.asyncio
async def test_image_pipeline_without_vision_profile_keeps_file_readable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import library.pipelines.image as mod

    monkeypatch.setattr(mod, "has_vision_profile", lambda: False)

    result = await ImagePipeline().run(
        ctx=_ctx(),
        storage=_MemoryStorage(b"not actually a tiff"),
    )

    assert result.kind == "image"
    assert result.summary == "Image file: scan.tiff"
    coverage = result.description["coverage"]
    assert coverage["source_mode"] == "image_metadata_only"
    assert coverage["reason"] == "vision_profile_missing"
    assert coverage["indexed_partial"] is True
    assert coverage["partial_reasons"] == ["vision_profile_missing"]


@pytest.mark.asyncio
async def test_image_member_without_vision_profile_returns_placeholder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import library.pipelines.image as mod

    monkeypatch.setattr(mod, "has_vision_profile", lambda: False)

    result = await ImagePipeline().read_segment_from_bytes(
        b"image bytes",
        {},
        filename="photo.heic",
    )

    assert result.error is None
    assert "photo.heic" in result.text
    assert result.extras["kind"] == "image"


@pytest.mark.asyncio
async def test_image_pipeline_vision_failure_marks_indexed_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import library.pipelines.image as mod

    class BoomClient:
        async def complete(self, request):  # noqa: ARG002
            raise RuntimeError("vlm down")

    monkeypatch.setattr(mod, "has_vision_profile", lambda: True)
    monkeypatch.setattr(mod, "downscale_for_vlm", lambda body: (b"jpeg", "image/jpeg"))
    monkeypatch.setattr(mod, "get_chat_client", lambda profile: BoomClient())
    monkeypatch.setattr(mod, "_disable_thinking_for_vlm", lambda client: None)

    result = await ImagePipeline().run(
        ctx=_ctx(),
        storage=_MemoryStorage(b"not actually a tiff"),
    )
    coverage = result.description["coverage"]
    assert coverage["source_mode"] == "image_metadata_only"
    assert coverage["reason"] == "vision_index_failed"
    assert coverage["indexed_partial"] is True
    assert coverage["partial_reasons"] == ["vision_index_failed"]


@pytest.mark.asyncio
async def test_image_pipeline_empty_summary_marks_indexed_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import library.pipelines.image as mod
    from types import SimpleNamespace

    class EmptyClient:
        async def complete(self, request):  # noqa: ARG002
            return SimpleNamespace(text="no tagged summary here")

    monkeypatch.setattr(mod, "has_vision_profile", lambda: True)
    monkeypatch.setattr(mod, "downscale_for_vlm", lambda body: (b"jpeg", "image/jpeg"))
    monkeypatch.setattr(mod, "get_chat_client", lambda profile: EmptyClient())
    monkeypatch.setattr(mod, "_disable_thinking_for_vlm", lambda client: None)

    result = await ImagePipeline().run(
        ctx=_ctx(),
        storage=_MemoryStorage(b"not actually a tiff"),
    )
    coverage = result.description["coverage"]
    assert coverage["reason"] == "vision_index_empty"
    assert coverage["indexed_partial"] is True
    assert coverage["partial_reasons"] == ["vision_index_empty"]
