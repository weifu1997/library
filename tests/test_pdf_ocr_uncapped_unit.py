"""Unit checks for default full-document OCR ingest."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from library.pipelines import pdf as pdf_module
from library.pipelines.pdf import PdfPipeline


def test_ocr_ingest_default_is_uncapped() -> None:
    original = pdf_module.OCR_MAX_PAGES
    try:
        pdf_module.OCR_MAX_PAGES = None
        assert pdf_module._ocr_configured_page_cap() is None
        assert pdf_module._ocr_pages_to_process(1000) == 1000

        coverage = PdfPipeline._coverage(
            total_pages=1000,
            indexed_pages=1000,
            chunk_count=25,
            text_truncated=False,
            ocr_used=True,
            ocr_pages_done=1000,
            ocr_failed_pages=0,
            partial_reasons=[],
            max_index_pages=pdf_module._ocr_configured_page_cap(),
        )
        assert coverage["indexed_partial"] is False
        assert coverage["partial_reasons"] == []
        assert "max_index_pages" not in coverage
    finally:
        pdf_module.OCR_MAX_PAGES = original


def test_ocr_cap_reads_live_settings(monkeypatch) -> None:
    from library.config import get_settings

    original = pdf_module.OCR_MAX_PAGES
    try:
        pdf_module.OCR_MAX_PAGES = pdf_module._OCR_CAP_LIVE
        monkeypatch.setenv("OCR_MAX_PAGES", "7")
        get_settings.cache_clear()  # type: ignore[attr-defined]
        assert pdf_module._ocr_configured_page_cap() == 7
        assert pdf_module._ocr_pages_to_process(20) == 7

        monkeypatch.setenv("OCR_MAX_PAGES", "0")
        get_settings.cache_clear()  # type: ignore[attr-defined]
        assert pdf_module._ocr_configured_page_cap() is None
        assert pdf_module._ocr_pages_to_process(20) == 20
    finally:
        pdf_module.OCR_MAX_PAGES = original
        get_settings.cache_clear()  # type: ignore[attr-defined]


def test_ocr_response_strips_reasoning_leak() -> None:
    leaked = (
        "The user wants the text from the image transcribed.\n"
        "1. Identify headings.\n"
        "</think>\n\n"
        "GA/T 1193-2014\n正文内容"
    )

    assert (
        pdf_module._clean_ocr_response_text(leaked)
        == "GA/T 1193-2014\n正文内容"
    )
    assert (
        pdf_module._clean_ocr_response_text("<think>hidden</think>\n正文")
        == "正文"
    )
    assert pdf_module._clean_ocr_response_text("Transcription:\n正文") == "正文"


def test_ocr_retrieval_extra_keeps_metadata_not_raw_text() -> None:
    extra = pdf_module._ocr_retrieval_extra(
        base_extra="notable_terms: standard, injury",
        ocr_pages=["Secret raw OCR page text"],
        document_type="book",
    )

    assert "notable_terms: standard, injury" in extra
    assert "ocr_document_type: book" in extra
    assert "ocr_pages_with_text: 1" in extra
    assert "ocr_text_sample" not in extra
    assert "Secret raw OCR page text" not in extra


def test_ocr_pdf_pages_batches_full_uncapped(monkeypatch) -> None:
    render_calls: list[tuple[int, int]] = []
    requests: list = []

    def fake_render(
        pdf_bytes: bytes,
        page_count: int,
        *,
        start_page: int = 0,
        pdf=None,
    ) -> list[bytes]:
        assert pdf_bytes == b"pdf"
        assert pdf is not None
        render_calls.append((start_page, page_count))
        return [b"jpeg"] * page_count

    def fake_downscale(jpeg_bytes: bytes, *, max_long_edge: int):
        assert jpeg_bytes == b"jpeg"
        return b"scaled", "image/jpeg"

    class FakeVision:
        provider = "openai-compatible"

        async def complete(self, request):
            requests.append(request)
            return SimpleNamespace(text="OCR text")

    original_cap = pdf_module.OCR_MAX_PAGES
    original_batch = pdf_module.OCR_RENDER_BATCH_PAGES
    try:
        pdf_module.OCR_MAX_PAGES = None
        pdf_module.OCR_RENDER_BATCH_PAGES = 20
        _patch_ocr_pdf_document(monkeypatch)
        monkeypatch.setattr(pdf_module, "_render_pdf_pages_to_jpeg", fake_render)
        monkeypatch.setattr(pdf_module, "downscale_for_vlm", fake_downscale)
        monkeypatch.setattr(pdf_module, "get_chat_client", lambda profile: FakeVision())

        out = asyncio.run(pdf_module._ocr_pdf_pages(b"pdf", 45))

        assert len(out) == 45
        assert all(text == "OCR text" for text in out)
        assert render_calls == [(0, 20), (20, 20), (40, 5)]
        assert requests
        assert all(
            req.extra_body == {"thinking": {"type": "disabled"}}
            for req in requests
        )
        assert _FakePdfDocument.constructions == 1
    finally:
        pdf_module.OCR_MAX_PAGES = original_cap
        pdf_module.OCR_RENDER_BATCH_PAGES = original_batch


def test_ocr_ingest_explicit_cap_still_marks_partial() -> None:
    original = pdf_module.OCR_MAX_PAGES
    try:
        pdf_module.OCR_MAX_PAGES = 5
        assert pdf_module._ocr_configured_page_cap() == 5
        assert pdf_module._ocr_pages_to_process(8) == 5

        coverage = PdfPipeline._coverage(
            total_pages=8,
            indexed_pages=5,
            chunk_count=1,
            text_truncated=False,
            ocr_used=True,
            ocr_pages_done=5,
            ocr_failed_pages=0,
            partial_reasons=["ocr_page_cap"],
            max_index_pages=pdf_module._ocr_configured_page_cap(),
        )
        assert coverage["indexed_partial"] is True
        assert coverage["partial_reasons"] == ["ocr_page_cap"]
        assert coverage["max_index_pages"] == 5
    finally:
        pdf_module.OCR_MAX_PAGES = original


class _FlakyVision:
    """Vision client whose failures are scripted per page (1-indexed).

    `fail_pages` maps page number -> how many attempts should still fail
    before the page starts succeeding. `float("inf")` means it never
    recovers.
    """

    provider = "openai-compatible"

    def __init__(self, fail_pages: dict[int, float]) -> None:
        self.fail_pages = dict(fail_pages)
        self.attempts: list[int] = []

    async def complete(self, request):
        # The page number lives in the leading TextBlock: "Page N of M."
        text = request.messages[0].content[0].text
        page_no = int(text.split()[1])
        self.attempts.append(page_no)
        remaining = self.fail_pages.get(page_no, 0)
        if remaining > 0:
            self.fail_pages[page_no] = remaining - 1
            raise RuntimeError(f"429 rate limited (page {page_no})")
        return SimpleNamespace(text=f"page {page_no} text")


class _FakePdfDocument:
    """Stand-in so AM-2's once-per-ingest PdfDocument open does not need
    real PDF bytes in OCR unit tests."""

    constructions = 0

    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs
        type(self).constructions += 1

    def close(self) -> None:
        return None


def _patch_ocr_pdf_document(monkeypatch) -> None:
    import pypdfium2

    _FakePdfDocument.constructions = 0
    monkeypatch.setattr(pypdfium2, "PdfDocument", _FakePdfDocument)


def _patch_ocr_render(monkeypatch, vision) -> None:
    _patch_ocr_pdf_document(monkeypatch)
    monkeypatch.setattr(
        pdf_module, "_render_pdf_pages_to_jpeg",
        lambda pdf_bytes, page_count, *, start_page=0, pdf=None: [b"jpeg"] * page_count,
    )
    monkeypatch.setattr(
        pdf_module, "downscale_for_vlm",
        lambda jpeg_bytes, *, max_long_edge: (b"scaled", "image/jpeg"),
    )
    monkeypatch.setattr(pdf_module, "get_chat_client", lambda profile: vision)
    # Keep the tests fast: the backoff itself is not what we are asserting.
    monkeypatch.setattr(pdf_module, "OCR_RETRY_BASE_SECONDS", 0.0)


def test_ocr_failed_page_is_none_not_blank(monkeypatch) -> None:
    """A page whose OCR never succeeds must be distinguishable from a page
    the model read and found empty."""
    vision = _FlakyVision({3: float("inf")})
    _patch_ocr_render(monkeypatch, vision)
    original = pdf_module.OCR_MAX_PAGES
    try:
        pdf_module.OCR_MAX_PAGES = None
        out = asyncio.run(pdf_module._ocr_pdf_pages(b"pdf", 5))
    finally:
        pdf_module.OCR_MAX_PAGES = original

    assert out[2] is None, "failed page must be None, not ''"
    assert [text for i, text in enumerate(out) if i != 2] == [
        "page 1 text", "page 2 text", "page 4 text", "page 5 text",
    ]


def test_ocr_retries_transient_failure(monkeypatch) -> None:
    """Two transient failures on one page must still yield its text."""
    vision = _FlakyVision({2: 2})
    _patch_ocr_render(monkeypatch, vision)
    original = pdf_module.OCR_MAX_PAGES
    try:
        pdf_module.OCR_MAX_PAGES = None
        out = asyncio.run(pdf_module._ocr_pdf_pages(b"pdf", 3))
    finally:
        pdf_module.OCR_MAX_PAGES = original

    assert out == ["page 1 text", "page 2 text", "page 3 text"]
    # 1 + 3 + 1: page 2 was attempted three times.
    assert vision.attempts.count(2) == 3


def test_ocr_gives_up_after_retry_budget(monkeypatch) -> None:
    vision = _FlakyVision({1: float("inf")})
    _patch_ocr_render(monkeypatch, vision)
    original = pdf_module.OCR_MAX_PAGES
    try:
        pdf_module.OCR_MAX_PAGES = None
        out = asyncio.run(pdf_module._ocr_pdf_pages(b"pdf", 1))
    finally:
        pdf_module.OCR_MAX_PAGES = original

    assert out == [None]
    assert vision.attempts.count(1) == pdf_module.OCR_PAGE_RETRIES + 1


def test_ocr_pages_past_cap_are_blank_not_failed(monkeypatch) -> None:
    """Pages beyond OCR_MAX_PAGES were never attempted — that is '' (not
    processed), not None (attempted and failed)."""
    vision = _FlakyVision({})
    _patch_ocr_render(monkeypatch, vision)
    original = pdf_module.OCR_MAX_PAGES
    try:
        pdf_module.OCR_MAX_PAGES = 2
        out = asyncio.run(pdf_module._ocr_pdf_pages(b"pdf", 4))
    finally:
        pdf_module.OCR_MAX_PAGES = original

    assert out == ["page 1 text", "page 2 text", "", ""]
    assert None not in out


def test_coverage_marks_partial_on_ocr_failures() -> None:
    """Failed pages make the index partial even when the page count looks
    whole — indexed_pages is the target, not the achieved count."""
    coverage = PdfPipeline._coverage(
        total_pages=20,
        indexed_pages=20,
        chunk_count=1,
        text_truncated=False,
        ocr_used=True,
        ocr_pages_done=6,
        ocr_failed_pages=14,
        partial_reasons=["ocr_page_failures"],
        max_index_pages=None,
    )

    assert coverage["indexed_partial"] is True
    assert "ocr_page_failures" in coverage["partial_reasons"]
    assert coverage["ocr_failed_pages"] == 14
    assert coverage["ocr_pages_done"] == 6


def test_coverage_marks_partial_on_text_page_failures() -> None:
    coverage = PdfPipeline._coverage(
        total_pages=20,
        indexed_pages=20,
        chunk_count=1,
        text_truncated=False,
        ocr_used=False,
        ocr_pages_done=0,
        ocr_failed_pages=0,
        partial_reasons=["text_page_failures"],
        max_index_pages=None,
        text_page_failures=1,
    )

    assert coverage["indexed_partial"] is True
    assert "text_page_failures" in coverage["partial_reasons"]
    assert coverage["text_page_failures"] == 1


def test_coverage_unchanged_when_all_ocr_pages_succeed() -> None:
    """Regression guard: the clean path must keep its exact previous shape,
    apart from the additive ocr_failed_pages field."""
    coverage = PdfPipeline._coverage(
        total_pages=3,
        indexed_pages=3,
        chunk_count=1,
        text_truncated=False,
        ocr_used=True,
        ocr_pages_done=3,
        ocr_failed_pages=0,
        partial_reasons=[],
        max_index_pages=None,
    )

    assert coverage == {
        "unit": "pages",
        "total_pages": 3,
        "indexed_pages": 3,
        "indexed_partial": False,
        "partial_reasons": [],
        "chunked": False,
        "chunk_count": 1,
        "text_truncated": False,
        "ocr_used": True,
        "ocr_pages_done": 3,
        "ocr_failed_pages": 0,
    }
