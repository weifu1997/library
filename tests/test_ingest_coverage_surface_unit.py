"""Unit checks for the user-facing ingest-coverage slice.

`File.description` is an AI-written JSON column with no enforced shape, and
`coverage` inside it is optional and versioned only by whatever wrote it. The
metadata endpoint must degrade field-by-field rather than fail, and must not
leak internal diagnostics to the client.
"""
from __future__ import annotations

import library.main  # noqa: F401  (import order: avoids a pre-existing cycle)
from library.services.user_files import _coverage_summary


def test_coverage_absent_or_malformed_returns_none() -> None:
    assert _coverage_summary(None) is None
    assert _coverage_summary("not a dict") is None
    assert _coverage_summary({}) is None
    assert _coverage_summary({"coverage": None}) is None
    assert _coverage_summary({"coverage": "nope"}) is None
    assert _coverage_summary({"coverage": []}) is None
    # A coverage block with nothing usable in it is the same as no coverage.
    assert _coverage_summary({"coverage": {"unit": "pages"}}) is None


def test_coverage_exposes_only_whitelisted_fields() -> None:
    out = _coverage_summary({
        "coverage": {
            "unit": "pages",
            "total_pages": 20,
            "indexed_pages": 20,
            "indexed_partial": True,
            "partial_reasons": ["ocr_page_failures"],
            "chunked": True,
            "chunk_count": 3,
            "text_truncated": False,
            "max_index_pages": 400,
            "ocr_used": True,
            "ocr_pages_done": 6,
            "ocr_failed_pages": 14,
        },
    })

    assert out == {
        "indexed_partial": True,
        "ocr_used": True,
        "total_pages": 20,
        "indexed_pages": 20,
        "ocr_pages_done": 6,
        "ocr_failed_pages": 14,
        "partial_reasons": ["ocr_page_failures"],
    }
    # Internal diagnostics must not reach the client.
    for leaked in ("unit", "chunked", "chunk_count", "max_index_pages"):
        assert leaked not in out


def test_coverage_drops_wrongly_typed_fields_without_failing() -> None:
    out = _coverage_summary({
        "coverage": {
            "indexed_partial": "yes",      # not a bool -> dropped
            "total_pages": "20",           # not an int -> dropped
            "indexed_pages": 5,            # kept
            "partial_reasons": ["ok", 7, None],  # non-str entries dropped
        },
    })

    assert out == {"indexed_pages": 5, "partial_reasons": ["ok"]}


def test_coverage_rejects_bool_for_int_fields() -> None:
    """bool is an int subclass — `True` must not become a page count."""
    out = _coverage_summary({
        "coverage": {"total_pages": True, "indexed_pages": 3},
    })
    assert out == {"indexed_pages": 3}


def test_coverage_tolerates_records_predating_ocr_failed_pages() -> None:
    """Documents ingested before the OCR partial-failure fix have no
    `ocr_failed_pages` key at all. Absence is normal, not an error."""
    out = _coverage_summary({
        "coverage": {
            "indexed_partial": True,
            "total_pages": 300,
            "indexed_pages": 50,
            "partial_reasons": ["text_page_cap"],
        },
    })

    assert out["indexed_partial"] is True
    assert "ocr_failed_pages" not in out
    assert out["partial_reasons"] == ["text_page_cap"]


def test_coverage_partial_reasons_survives_empty_list() -> None:
    out = _coverage_summary({
        "coverage": {"indexed_partial": False, "partial_reasons": []},
    })
    assert out == {"indexed_partial": False, "partial_reasons": []}
