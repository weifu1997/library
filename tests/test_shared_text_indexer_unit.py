from __future__ import annotations

from types import SimpleNamespace

import pytest

from library.llm.types import ChatRequest, ChatResponse, TokenUsage
from library.pipelines import _text_indexer as indexer
from library.pipelines.base import PipelineContext
from library.pipelines.docx import _docx_sections
from library.pipelines.pptx import _slide_sections
from library.pipelines.spreadsheet import _sheet_sections


def _ctx() -> PipelineContext:
    return PipelineContext(
        file_id="file-1",
        storage_key="object-1",
        sha256="a" * 64,
        size_bytes=100_000,
        mime_type="text/plain",
        original_ext=".txt",
        folder_path="/tests",
        sibling_names=[],
        display_name="long.txt",
    )


def _response(*, summary: str, sections: str = "") -> ChatResponse:
    return ChatResponse(
        text=f"""<summary>{summary}</summary>
<description>Indexed description.</description>
<sections>{sections}</sections>
<extra>terms: alpha, omega</extra>
<entry_extra></entry_extra>
<catalog_path>Tests / Documents</catalog_path>
<tags>topic: tests\nform: text</tags>""",
        tool_calls=[],
        stop_reason="end_turn",
        usage=TokenUsage(),
    )


def test_index_output_budget_never_exceeds_configured_limit() -> None:
    assert indexer._index_output_tokens(1, configured=600) == 600
    assert indexer._index_output_tokens(100_000, configured=1_200) == 1_200
    assert indexer._index_output_tokens(10_000_000, configured=50_000) == 16_384
    assert indexer._index_output_tokens(100_000, configured=0) == 0
    with pytest.raises(ValueError, match="non-negative"):
        indexer._index_output_tokens(100_000, configured=-1)


@pytest.mark.asyncio
async def test_long_extracted_text_is_chunked_then_aggregated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = "\n".join(f"line {number} alpha omega" for number in range(7_000))

    class FakeClient:
        def __init__(self) -> None:
            self.requests: list[ChatRequest] = []

        async def complete(self, request: ChatRequest) -> ChatResponse:
            self.requests.append(request)
            if "aggregate" in (request.system or "").lower():
                return _response(summary="Aggregate summary.")
            number = len(self.requests)
            return _response(
                summary=f"Chunk {number}.",
                sections=(
                    f"s1 | {number}-{number + 10} | Chunk {number} | "
                    "Indexed chunk. | alpha, omega"
                ),
            )

    fake = FakeClient()
    monkeypatch.setattr(indexer, "get_chat_client", lambda _profile: fake)
    monkeypatch.setattr(
        indexer,
        "get_settings",
        lambda: SimpleNamespace(llm_ingest_max_tokens=900),
    )
    monkeypatch.setattr(
        indexer,
        "maybe_compress_ingest_aggregate_view",
        lambda body, **_kwargs: (body, None),
    )

    result = await indexer.index_extracted_text(
        body,
        _ctx(),
        "text",
        coverage={"unit": "lines", "total_units": 7_000, "indexed_units": 7_000},
    )

    assert result.summary == "Aggregate summary."
    assert result.description["coverage"]["chunk_count"] >= 2
    assert len(result.description["sections"]) >= 2
    assert all(request.max_tokens <= 900 for request in fake.requests)
    assert "section_map:" in (result.extra or "")


@pytest.mark.asyncio
async def test_failed_chunks_keep_stable_fallback_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = "\n".join(f"line {number} content" for number in range(8_000))

    class FailingChunkClient:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, request: ChatRequest) -> ChatResponse:
            self.calls += 1
            if "aggregate" in (request.system or "").lower():
                return _response(summary="Recovered aggregate.")
            raise RuntimeError("chunk unavailable")

    fake = FailingChunkClient()
    monkeypatch.setattr(indexer, "get_chat_client", lambda _profile: fake)
    monkeypatch.setattr(
        indexer,
        "get_settings",
        lambda: SimpleNamespace(llm_ingest_max_tokens=1_200),
    )
    monkeypatch.setattr(
        indexer,
        "maybe_compress_ingest_aggregate_view",
        lambda body, **_kwargs: (body, None),
    )

    result = await indexer.index_extracted_text(body, _ctx(), "text")

    sections = result.description["sections"]
    assert result.summary == "Recovered aggregate."
    assert len(sections) >= 2
    assert all(section["anchor"]["unit"] == "lines" for section in sections)
    assert all(section["anchor"]["value"] for section in sections)


def test_office_named_sections_have_stable_native_anchors() -> None:
    slides = _slide_sections(["# Slide 1: Intro\nWelcome", "# Slide 2\nDetails"])
    sheets = _sheet_sections({
        "sheets": [
            {
                "name": "Revenue",
                "indexed_rows": 200,
                "total_rows": 500,
                "indexed_partial": True,
            },
        ],
    })
    blocks = _docx_sections(
        ["# Overview", "intro", "## Details", "deep content"],
        indexed_chars=10_000,
    )

    assert slides[0]["title"] == "Slide 1: Intro"
    assert slides[0]["anchor"] == {"unit": "slides", "value": "1"}
    assert sheets[0]["title"] == "Revenue"
    assert sheets[0]["anchor"] == {"unit": "sheet", "value": "Revenue"}
    assert blocks[1]["title"] == "Details"
    assert blocks[1]["anchor"] == {"unit": "blocks", "value": "3-4"}


@pytest.mark.asyncio
async def test_model_failure_uses_named_sections_and_marks_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_client(_profile: str):
        raise RuntimeError("no ingest model")

    fallback = [{
        "title": "Revenue",
        "anchor": {"unit": "sheet", "value": "Revenue"},
        "summary": "rows 1-20",
        "key_terms": ["Revenue"],
    }]
    monkeypatch.setattr(indexer, "get_chat_client", fail_client)

    result = await indexer.index_extracted_text(
        "# Sheet: Revenue\nmonth | amount",
        _ctx(),
        "table",
        coverage={"unit": "rows", "total_units": 20, "indexed_units": 20},
        fallback_sections=fallback,
        pipeline="spreadsheet",
    )

    assert result.description["source"] == "heuristic"
    assert result.description["sections"][0]["title"] == "Revenue"
    assert result.description["sections"][0]["anchor"]["unit"] == "sheet"
