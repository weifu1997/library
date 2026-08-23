from __future__ import annotations

from library.agent.citation_manifest import (
    attach_citation_manifest,
    prepare_finish_citation_manifest,
)
from library.agent.tools import get_tool
from library.citations import iter_citation_footnotes
from library.llm import ToolCall
import library.agent.runtime as runtime


ENTRY_ID = "0750b210-60d5-4f43-9c47-c5c84caac9be"


def _read_call(text: str) -> dict[str, object]:
    return {
        "name": "read_files",
        "arguments": {"requests": [{"entry_id": ENTRY_ID}]},
        "result": {
            "ok": True,
            "results": [
                {
                    "ok": True,
                    "entry_id": ENTRY_ID,
                    "reads": [
                        {
                            "ok": True,
                            "text": text,
                            "args": {"slide_start": 2, "slide_end": 2},
                        }
                    ],
                }
            ],
        },
        "error": None,
    }


def _finish_call(*, quote: str, page: int | None = None) -> ToolCall:
    citation: dict[str, object] = {
        "entry_id": ENTRY_ID,
        "quote": quote,
        "reason": "支持项目定位结论",
    }
    if page is not None:
        citation["page"] = page
    return ToolCall(
        id="finish-1",
        name="finish_research",
        arguments={
            "evidence_status": "sufficient",
            "citations": [citation],
        },
    )


def test_finish_research_is_registered_with_citation_contract() -> None:
    registration = get_tool("finish_research")
    assert registration is not None
    assert registration.policy.access == "read"
    assert registration.policy.concurrency == "session_serial"
    assert registration.input_schema["required"] == ["evidence_status"]
    citation_schema = registration.input_schema["properties"]["citations"]
    assert citation_schema["maxItems"] == 20
    assert citation_schema["items"]["required"] == [
        "entry_id",
        "quote",
        "reason",
    ]


def test_finish_research_builds_manifest_from_visible_source_text() -> None:
    manifest, error = prepare_finish_citation_manifest(
        _finish_call(quote="B50KS 产品定位定义"),
        [_read_call("# Slide 2\nB50KS 产品定位定义")],
    )

    assert error is None
    assert manifest == [
        {
            "marker": "a",
            "entry_id": ENTRY_ID,
            "quote": "B50KS 产品定位定义",
            "reason": "支持项目定位结论",
            "source": "read_files",
            "page": 2,
        }
    ]


def test_finish_research_rejects_unread_quote_and_unverified_page() -> None:
    manifest, quote_error = prepare_finish_citation_manifest(
        _finish_call(quote="没有读取过的结论"),
        [_read_call("# Slide 2\nB50KS 产品定位定义")],
    )
    _, page_error = prepare_finish_citation_manifest(
        _finish_call(quote="B50KS 产品定位定义", page=3),
        [_read_call("# Slide 2\nB50KS 产品定位定义")],
    )

    assert manifest == []
    assert quote_error is not None
    assert quote_error["guard"] == "citation_quote_not_found"
    assert page_error is not None
    assert page_error["guard"] == "citation_page_not_verified"


def test_finish_research_requires_citations_when_source_text_was_read() -> None:
    manifest, error = prepare_finish_citation_manifest(
        ToolCall(
            id="finish-1",
            name="finish_research",
            arguments={"evidence_status": "sufficient"},
        ),
        [_read_call("B50KS 产品定位定义")],
    )

    assert manifest == []
    assert error is not None
    assert error["guard"] == "missing_citations"


def test_finish_research_rejects_citations_without_a_prior_source_read() -> None:
    manifest, error = prepare_finish_citation_manifest(
        _finish_call(quote="B50KS 产品定位定义"),
        [],
    )

    assert manifest == []
    assert error is not None
    assert error["guard"] == "citations_without_source_read"


def test_finish_research_rejects_an_unresolved_read_failure() -> None:
    error = runtime._finish_research_preflight(
        _finish_call(quote="B50KS 产品定位定义"),
        [{
            "name": "read_files",
            "arguments": {"requests": [{"entry_id": ENTRY_ID}]},
            "result": {"ok": False, "error": "range unavailable"},
            "error": None,
        }],
    )

    assert error is not None
    assert error["guard"] == "unresolved_read_failure"


def test_titled_slide_marker_verifies_page_within_a_multi_slide_read() -> None:
    read_call = _read_call("# Slide 2: Product\nB50KS 产品定位定义\n# Slide 3\nOther")
    reads = read_call["result"]["results"][0]["reads"]  # type: ignore[index]
    reads[0]["args"]["slide_end"] = 3

    manifest, error = prepare_finish_citation_manifest(
        _finish_call(quote="B50KS 产品定位定义", page=2),
        [read_call],
    )

    assert error is None
    assert manifest[0]["page"] == 2


def test_manifest_definitions_are_attached_deterministically() -> None:
    manifest = [
        {
            "marker": "a",
            "entry_id": ENTRY_ID,
            "quote": '产品定位为“家庭旗舰”',
            "reason": "支持产品定位结论",
            "page": 2,
        }
    ]

    answer = attach_citation_manifest("B50KS 是一个整车产品项目。", manifest)

    assert "来源：[^a]" in answer
    assert f"[^a]: entry_id={ENTRY_ID}" in answer
    assert 'quote="产品定位为“家庭旗舰”"' in answer
    assert "page=2 - 支持产品定位结论" in answer
    parsed = iter_citation_footnotes(answer)
    assert len(parsed) == 1
    assert parsed[0].entry_id == ENTRY_ID
    assert parsed[0].page == "2"


def test_manifest_replaces_model_written_definition() -> None:
    manifest = [
        {
            "marker": "a",
            "entry_id": ENTRY_ID,
            "quote": "可信原文",
            "reason": "可信理由",
        }
    ]
    raw = (
        "结论。[^a]\n\n"
        '[^a]: entry_id=deadbeef, quote="伪造原文" - 伪造理由'
    )

    answer = attach_citation_manifest(raw, manifest)

    assert answer.count("[^a]:") == 1
    assert "deadbeef" not in answer
    assert "可信原文" in answer
