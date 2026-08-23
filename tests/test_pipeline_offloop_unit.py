"""Unit checks for audit 二.4 / 二.5.

二.4 — CPU-bound document parsing must run via ``asyncio.to_thread`` so the
event loop and worker heartbeats stay responsive. These tests wrap
``asyncio.to_thread`` to record which callables were offloaded and on which
thread they actually ran.

二.5 — the scanned-PDF OCR fallback must honor a configurable page cap
(``ocr_max_pages``, default 300) and flag ``ocr_page_cap`` partial coverage
when it trips, instead of fanning out one VLM call per page unbounded.
"""
from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import pytest

from library.config import get_settings
from library.pipelines import pdf as pdf_module
from library.pipelines import pptx as pptx_module
from library.pipelines.base import PipelineContext
from library.pipelines.docx import DocxPipeline
from library.pipelines.pdf import PdfPipeline
from library.pipelines.pptx import PptxPipeline
from library.pipelines.spreadsheet import SpreadsheetPipeline


class _ChunkStorage:
    def __init__(self, size: int = 16):
        self.size = size

    async def get(self, key: str):
        del key
        yield b"x" * self.size


class _FakeResult(dict):
    """Dict-shaped stand-in that also tolerates the attribute writes run()
    performs on real PipelineResults (e.g. result.description)."""

    description = None


def _ctx(name: str) -> PipelineContext:
    return PipelineContext(
        file_id=f"file-{name}",
        storage_key=f"{name}.bin",
        sha256="0" * 64,
        size_bytes=16,
        mime_type=None,
        original_ext=f".{name}",
        folder_path="/tests",
        sibling_names=[],
        display_name=f"{name}.bin",
    )


@pytest.fixture
def record_to_thread(monkeypatch):
    """Wrap ``asyncio.to_thread`` so a test can assert which callables were
    offloaded and on which worker thread they ran (to prove they left the
    event-loop thread)."""
    real = asyncio.to_thread
    calls: list = []
    threads: dict = {}

    async def recording(func, /, *args, **kwargs):
        calls.append(func)

        def _wrapped(*a, **k):
            threads[func] = threading.get_ident()
            return func(*a, **k)

        return await real(_wrapped, *args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", recording)
    return calls, threads


async def _fake_index(body, ctx, *, kind, coverage, **_kwargs):
    return _FakeResult(body=body, ctx=ctx, kind=kind, coverage=coverage)


# --- 二.4: parse/extract offloading ----------------------------------------


@pytest.mark.asyncio
async def test_docx_parse_runs_off_the_event_loop(monkeypatch, record_to_thread):
    calls, threads = record_to_thread
    loop_ident = threading.get_ident()

    def fake_parse(body: bytes) -> list[str]:
        return ["hello"]

    monkeypatch.setattr(
        DocxPipeline, "_parse_paragraphs_from_bytes", staticmethod(fake_parse),
    )
    monkeypatch.setattr(
        "library.pipelines.docx.index_extracted_text", _fake_index,
    )

    await DocxPipeline().run(ctx=_ctx("docx"), storage=_ChunkStorage())

    assert fake_parse in calls, "paragraph parse was not offloaded"
    assert threads[fake_parse] != loop_ident


@pytest.mark.asyncio
async def test_pptx_parse_runs_off_the_event_loop(monkeypatch, record_to_thread):
    calls, threads = record_to_thread
    loop_ident = threading.get_ident()

    def fake_render(body: bytes, *, max_slides=None):
        assert max_slides == pptx_module.MAX_PPTX_SLIDES
        return ["# Slide 1\nhi"], {
            "unit": "slides",
            "source_mode": "pptx_extracted_text",
            "total_slides": 1,
            "indexed_slides": 1,
        }

    monkeypatch.setattr(
        PptxPipeline, "_render_from_bytes_with_coverage", staticmethod(fake_render),
    )
    monkeypatch.setattr(
        "library.pipelines.pptx.index_extracted_text", _fake_index,
    )

    await PptxPipeline().run(ctx=_ctx("pptx"), storage=_ChunkStorage())

    assert fake_render in calls, "deck parse was not offloaded"
    assert threads[fake_render] != loop_ident


@pytest.mark.asyncio
async def test_spreadsheet_parse_runs_off_the_event_loop(monkeypatch, record_to_thread):
    calls, threads = record_to_thread
    loop_ident = threading.get_ident()

    def fake_render(body: bytes):
        return "# Sheet: s\nv", {
            "unit": "rows",
            "source_mode": "spreadsheet_row_sample",
            "total_rows": 1,
            "indexed_rows": 1,
        }

    monkeypatch.setattr(
        SpreadsheetPipeline,
        "_render_from_bytes_with_coverage",
        staticmethod(fake_render),
    )
    monkeypatch.setattr(
        "library.pipelines.spreadsheet.index_extracted_text", _fake_index,
    )

    await SpreadsheetPipeline().run(ctx=_ctx("xlsx"), storage=_ChunkStorage())

    assert fake_render in calls, "workbook parse was not offloaded"
    assert threads[fake_render] != loop_ident


@pytest.mark.asyncio
async def test_pdf_parse_and_extract_run_off_the_event_loop(monkeypatch, record_to_thread):
    calls, threads = record_to_thread
    loop_ident = threading.get_ident()

    def fake_page_count(body: bytes) -> int:
        return 2

    def fake_extract_text(body: bytes, *, max_pages=None) -> list[str]:
        # Enough chars/page that the text layer is trusted (no OCR fallback).
        return ["this page has a real text layer with plenty of characters"] * 2

    def fake_extract_images(body: bytes, *, max_pages=None):
        return []

    async def fake_single_index(self, **kwargs):
        return _FakeResult(coverage={})

    monkeypatch.setattr(PdfPipeline, "_page_count", staticmethod(fake_page_count))
    monkeypatch.setattr(PdfPipeline, "_extract_text", staticmethod(fake_extract_text))
    monkeypatch.setattr(pdf_module, "extract_images", fake_extract_images)
    monkeypatch.setattr(pdf_module, "has_vision_profile", lambda *a, **k: True)
    monkeypatch.setattr(PdfPipeline, "_run_single_index", fake_single_index)

    await PdfPipeline().run(ctx=_ctx("pdf"), storage=_ChunkStorage())

    # All three pure-CPU steps were offloaded (二.4 targets).
    for fn in (fake_page_count, fake_extract_text, fake_extract_images):
        assert fn in calls, f"{fn.__name__} was not offloaded"
        assert threads[fn] != loop_ident


# --- 二.5: OCR page cap -----------------------------------------------------


def test_ocr_max_pages_default_is_bounded(monkeypatch) -> None:
    # OCR is no longer uncapped by default: the configurable setting defaults
    # to a bounded value (二.5), and the pdf module seeds its page cap from it.
    assert get_settings().ocr_max_pages == 300

    # When the module cap carries the settings default, the OCR path is bounded
    # at 300 pages. (Set it explicitly here rather than reading the live global:
    # a sibling e2e module mutates OCR_MAX_PAGES at import time, so the raw
    # value is order-sensitive under a full-suite run.)
    monkeypatch.setattr(pdf_module, "OCR_MAX_PAGES", get_settings().ocr_max_pages)
    assert pdf_module._ocr_configured_page_cap() == 300
    assert pdf_module._ocr_pages_to_process(1000) == 300


@pytest.mark.asyncio
async def test_scanned_pdf_caps_ocr_pages_and_flags_partial(monkeypatch):
    total_pages = 10
    cap = 3
    # Simulate the configured cap (ocr_max_pages) seeding OCR_MAX_PAGES.
    monkeypatch.setattr(pdf_module, "OCR_MAX_PAGES", cap)
    monkeypatch.setattr(pdf_module, "OCR_RENDER_BATCH_PAGES", 20)
    monkeypatch.setattr(pdf_module, "has_vision_profile", lambda *a, **k: True)

    ocr_calls: list[int] = []

    def fake_render(pdf_bytes, page_count, *, start_page=0):
        return [b"jpeg"] * page_count

    def fake_downscale(jpeg_bytes, *, max_long_edge):
        return b"scaled", "image/jpeg"

    class FakeVision:
        provider = "openai-compatible"

        async def complete(self, request):
            ocr_calls.append(1)
            return SimpleNamespace(text="Scanned page text.")

    # No usable text layer -> force the OCR fallback branch.
    monkeypatch.setattr(
        PdfPipeline, "_page_count", staticmethod(lambda body: total_pages),
    )
    monkeypatch.setattr(
        PdfPipeline,
        "_extract_text",
        staticmethod(lambda body, *, max_pages=None: [""] * total_pages),
    )
    monkeypatch.setattr(pdf_module, "_render_pdf_pages_to_jpeg", fake_render)
    monkeypatch.setattr(pdf_module, "downscale_for_vlm", fake_downscale)
    monkeypatch.setattr(pdf_module, "get_chat_client", lambda profile: FakeVision())

    captured: dict = {}

    async def fake_single_index(self, **kwargs):
        captured.update(kwargs)
        return _FakeResult(
            coverage={"partial_reasons": list(kwargs["partial_reasons"])},
        )

    monkeypatch.setattr(PdfPipeline, "_run_single_index", fake_single_index)

    result = await PdfPipeline().run(ctx=_ctx("pdf"), storage=_ChunkStorage())

    # OCR ran for exactly the capped page count, not all total_pages.
    assert len(ocr_calls) == cap
    assert captured["indexed_pages"] == cap
    assert captured["total_pages"] == total_pages
    assert captured["ocr_used"] is True
    assert "ocr_page_cap" in captured["partial_reasons"]
    assert result["coverage"]["partial_reasons"] == ["ocr_page_cap"]
