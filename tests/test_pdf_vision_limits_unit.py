from __future__ import annotations

import base64
import math
import random
from io import BytesIO
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from library.llm.types import ImageBlock
from library.pipelines import pdf as pdf_pipeline


class _FakePdfImage:
    container = None

    def __init__(self, *, pixel_size: tuple[int, int], matrix: Any) -> None:
        self._pixel_size = pixel_size
        self._matrix = matrix

    def get_matrix(self) -> Any:
        return self._matrix

    def get_px_size(self) -> tuple[int, int]:
        return self._pixel_size


class _FakePdfPage:
    def __init__(
        self,
        *,
        size: tuple[float, float] = (612.0, 792.0),
        bbox: tuple[float, float, float, float] = (0.0, 0.0, 612.0, 792.0),
        images: list[_FakePdfImage] | None = None,
    ) -> None:
        self._size = size
        self._bbox = bbox
        self._images = images or []

    def get_size(self) -> tuple[float, float]:
        return self._size

    def get_bbox(self) -> tuple[float, float, float, float]:
        return self._bbox

    def get_objects(self, **_kwargs: Any) -> list[_FakePdfImage]:
        return self._images


class _Storage:
    async def get(self, _key: str):
        yield b"not-a-real-pdf"


def test_pdf_vector_page_render_scale_is_capped_at_150_dpi() -> None:
    scale = pdf_pipeline._pdf_vision_render_scale(_FakePdfPage())
    assert scale == pytest.approx(pdf_pipeline.PDF_VISION_MAX_DPI / 72.0)
    assert scale * 72.0 == pytest.approx(150.0)


def test_pdf_dominant_scan_render_scale_does_not_upsample_source_image() -> None:
    page_width = 612.0
    page_height = 792.0
    pixel_width = 1_000
    pixel_height = 1_294
    page = _FakePdfPage(images=[_FakePdfImage(
        pixel_size=(pixel_width, pixel_height),
        matrix=SimpleNamespace(
            a=page_width,
            b=0.0,
            c=0.0,
            d=page_height,
            e=0.0,
            f=0.0,
        ),
    )])

    scale = pdf_pipeline._pdf_vision_render_scale(page)
    assert scale < pdf_pipeline.PDF_VISION_MAX_DPI / 72.0
    assert math.ceil(page_width * scale) <= pixel_width
    assert math.ceil(page_height * scale) <= pixel_height


def test_pdf_vision_jpeg_stays_below_request_budget_without_enlarging() -> None:
    source_size = (1_600, 1_600)
    random_bytes = random.Random(20260711).randbytes(
        source_size[0] * source_size[1] * 3
    )
    source = Image.frombytes("RGB", source_size, random_bytes)
    try:
        encoded = pdf_pipeline._encode_pdf_vision_jpeg(
            source,
            effective_dpi=150.0,
        )
        data_url_chars = pdf_pipeline._pdf_vision_data_url_chars(encoded)
        assert pdf_pipeline.PDF_VISION_JPEG_QUALITIES[0] == 80
        assert data_url_chars <= pdf_pipeline.PDF_VISION_MAX_DATA_URL_CHARS
        assert (
            data_url_chars + pdf_pipeline.PDF_VISION_REQUEST_OVERHEAD_CHARS
            <= pdf_pipeline.PDF_VISION_MAX_REQUEST_CHARS
        )
        with Image.open(BytesIO(encoded)) as rendered:
            rendered.load()
            rendered_dpi = rendered.info.get("dpi", (0.0, 0.0))
            assert rendered.width <= source.width
            assert rendered.height <= source.height
            assert rendered.width * rendered.height < source.width * source.height
            assert max(rendered_dpi) <= 150.0
    finally:
        source.close()


def test_pdf_vision_batches_respect_page_and_character_limits() -> None:
    byte_sizes = [200_000, 200_000, 200_000, 300_000, 300_000, 200_000, 200_000]
    pages = [
        (page_no, b"x" * size)
        for page_no, size in enumerate(byte_sizes, start=1)
    ]
    batches = pdf_pipeline._pdf_vision_page_batches(pages)

    assert [[page_no for page_no, _jpeg in batch] for batch in batches] == [
        [1, 2, 3],
        [4, 5],
        [6, 7],
    ]
    for batch in batches:
        image_chars = sum(
            pdf_pipeline._pdf_vision_data_url_chars(jpeg)
            for _page_no, jpeg in batch
        )
        assert len(batch) <= pdf_pipeline.PDF_VISION_MAX_PAGES_PER_BATCH
        assert image_chars <= pdf_pipeline.PDF_VISION_MAX_DATA_URL_CHARS
        assert (
            image_chars + pdf_pipeline.PDF_VISION_REQUEST_OVERHEAD_CHARS
            <= pdf_pipeline.PDF_VISION_MAX_REQUEST_CHARS
        )


def test_pdf_vision_question_fits_reserved_serialized_overhead() -> None:
    question = "照明要求\n" * 20_000
    bounded = pdf_pipeline._bounded_pdf_vision_question(question)
    assert bounded
    assert len(bounded) < len(question)
    assert (
        pdf_pipeline._json_string_chars(bounded)
        <= pdf_pipeline.PDF_VISION_MAX_QUESTION_CHARS
    )


@pytest.mark.asyncio
async def test_pdf_multi_page_question_uses_one_vision_call() -> None:
    class _Client:
        def __init__(self) -> None:
            self.requests: list[Any] = []

        async def complete(self, request: Any) -> Any:
            self.requests.append(request)
            return SimpleNamespace(
                text="[Page 1]\nfirst\n\n[Page 2]\nsecond\n\n[Page 3]\nthird"
            )

    client = _Client()
    answers, request_count, used_fallback = (
        await pdf_pipeline._answer_pdf_question_pages(
            client=client,
            pages=[(1, b"jpeg-1"), (2, b"jpeg-2"), (3, b"jpeg-3")],
            question="What is visible?",
        )
    )

    assert request_count == 1
    assert used_fallback is False
    assert len(client.requests) == 1
    request = client.requests[0]
    assert request.max_tokens == 6_144
    image_blocks = [
        block
        for block in request.messages[0].content
        if isinstance(block, ImageBlock)
    ]
    assert [base64.b64decode(block.data_b64) for block in image_blocks] == [
        b"jpeg-1",
        b"jpeg-2",
        b"jpeg-3",
    ]
    assert answers == [
        "[Page 1]\nfirst\n\n[Page 2]\nsecond\n\n[Page 3]\nthird"
    ]


@pytest.mark.asyncio
async def test_pdf_multi_page_fallback_is_only_for_incompatible_providers() -> None:
    class _Client:
        def __init__(self, error: Exception) -> None:
            self.error = error
            self.page_counts: list[int] = []

        async def complete(self, request: Any) -> Any:
            image_count = sum(
                isinstance(block, ImageBlock)
                for block in request.messages[0].content
            )
            self.page_counts.append(image_count)
            if image_count > 1:
                raise self.error
            return SimpleNamespace(text="single page answer")

    compatible_failure = _Client(
        RuntimeError("provider does not accept multiple images")
    )
    answers, request_count, used_fallback = (
        await pdf_pipeline._answer_pdf_question_pages(
            client=compatible_failure,
            pages=[(4, b"jpeg-4"), (5, b"jpeg-5"), (6, b"jpeg-6")],
            question="What is visible?",
        )
    )
    assert compatible_failure.page_counts == [3, 1, 1, 1]
    assert request_count == 4
    assert used_fallback is True
    assert [answer.splitlines()[0] for answer in answers] == [
        "[Page 4]",
        "[Page 5]",
        "[Page 6]",
    ]

    timeout = _Client(TimeoutError("provider timed out"))
    with pytest.raises(TimeoutError, match="provider timed out"):
        await pdf_pipeline._answer_pdf_question_pages(
            client=timeout,
            pages=[(1, b"jpeg-1"), (2, b"jpeg-2")],
            question="What is visible?",
        )
    assert timeout.page_counts == [2]


@pytest.mark.asyncio
async def test_late_pdf_question_renders_only_the_requested_page_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    render_calls: list[tuple[int, int, float]] = []

    def fake_render(
        _body: bytes,
        page_count: int,
        *,
        start_page: int = 0,
        dpi: float,
    ) -> list[bytes]:
        render_calls.append((start_page, page_count, dpi))
        return [f"jpeg-{page}".encode() for page in range(start_page, start_page + page_count)]

    class _Client:
        async def complete(self, _request: Any) -> Any:
            return SimpleNamespace(text="late-page answer")

    monkeypatch.setattr(pdf_pipeline, "has_vision_profile", lambda: True)
    monkeypatch.setattr(pdf_pipeline, "_render_pdf_pages_to_jpeg", fake_render)
    monkeypatch.setattr(
        pdf_pipeline,
        "downscale_for_vlm",
        lambda body, *, max_long_edge: (body, "image/jpeg"),
    )
    monkeypatch.setattr(pdf_pipeline, "_fit_pdf_vision_jpeg_budget", lambda body: body)
    monkeypatch.setattr(pdf_pipeline, "get_chat_client", lambda _profile: _Client())

    result = await pdf_pipeline.PdfPipeline()._answer_with_vlm(
        file_row=SimpleNamespace(storage_key="late.pdf"),
        question="What is visible?",
        args={"page_start": 50, "page_end": 54},
        storage=_Storage(),
    )

    assert result.error is None
    assert render_calls == [(49, 5, pdf_pipeline.PDF_VISION_MAX_DPI)]
    assert result.extras["page_start"] == 50
    assert result.extras["page_end"] == 54
