"""AT-2 + AT-5 regression for query_sql.

AT-2 — hostile column names never become queryable identifiers:
  `_validate_column_name` rejects `"`, `;`, and control chars at load time;
  `_run_duckdb` refuses to load a CSV whose header contains one, so the
  model can never reference it (a header like `x"; SELECT 1 --` inside a
  quoted DuckDB identifier could otherwise splice a second statement).

AT-5 — char-cap paging honesty:
  The char-cap branch (rows exceeding MAX_RESULT_CHARS) must advance
  `next_offset` by the FULL fetched page (no re-delivery of the dropped
  tail) and only report `has_more` when that page was actually full (no
  phantom "more" when the result set was small).

Uses `_run_duckdb` directly with temp files — no DB / entries needed.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import mkdtemp
from types import SimpleNamespace

import pytest

from library.agent.tools.query_sql import (
    MAX_RESULT_CHARS,
    MAX_RESULT_ROWS,
    _run_duckdb,
    _validate_column_name,
)


def _write_csv(dir_path: Path, name: str, text: str) -> Path:
    p = dir_path / name
    p.write_text(text, encoding="utf-8")
    return p


def _record(path: Path, display_name: str) -> tuple[list, list]:
    entry = SimpleNamespace(id="e1", display_name=display_name)
    file_stub = SimpleNamespace()
    records = [(entry, file_stub, "csv")]
    on_disk = [(str(path), entry, file_stub)]
    return on_disk, records


# --- AT-2 ---------------------------------------------------------------

def test_validate_column_name_rejects_hostile() -> None:
    assert _validate_column_name("age") is None
    assert _validate_column_name("first name") is None
    assert _validate_column_name("x\"; SELECT 1 --") is not None  # `;`
    assert _validate_column_name('quote"d') is not None  # `"`
    assert _validate_column_name("line\nbreak") is not None  # control char


@pytest.mark.asyncio
async def test_hostile_header_rejected_at_load() -> None:
    tmp = Path(mkdtemp(prefix="qs_at2_"))
    try:
        csv = _write_csv(
            tmp, "hostile.csv",
            'x"; SELECT 1 --,ok\n1,2\n',
        )
        on_disk, records = _record(csv, "hostile.csv")
        r = _run_duckdb(on_disk, "SELECT COUNT(*) FROM t1", records, 0, None)
        assert r["ok"] is False
        assert "not queryable" in r["error"]
        assert "rows" not in r
    finally:
        for p in tmp.glob("*"):
            p.unlink()
        tmp.rmdir()


# --- AT-5 ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_char_cap_small_page_no_phantom_more() -> None:
    """12 wide rows: over MAX_RESULT_CHARS but under the row page limit.
    Old behavior forced has_more=True here (phantom "more"); now the page
    wasn't full, so has_more must be False and no next_offset offered."""
    tmp = Path(mkdtemp(prefix="qs_at5_"))
    try:
        body = "a,b\n" + "\n".join(
            f'{i},"{"x" * 6000}"' for i in range(12)
        )
        csv = _write_csv(tmp, "wide.csv", body)
        on_disk, records = _record(csv, "wide.csv")
        r = _run_duckdb(on_disk, "SELECT * FROM t1", records, 0, None)
        assert r["ok"] is True
        approx = 6001 * 12 + len("a,b")
        assert approx > MAX_RESULT_CHARS  # guard: scenario actually caps
        keep = max(1, 12 * MAX_RESULT_CHARS // approx)
        assert r["truncated"] is True
        assert r["truncation_reason"] is not None
        assert len(r["rows"]) == keep
        assert r["has_more"] is False
        assert "next_offset" not in r
    finally:
        for p in tmp.glob("*"):
            p.unlink()
        tmp.rmdir()


@pytest.mark.asyncio
async def test_char_cap_full_page_advances_by_full_fetch() -> None:
    """600 rows fill the 500-row page AND exceed MAX_RESULT_CHARS. The next
    offset must advance past the full fetched page (500), not just the kept
    rows, so the next page never re-delivers the dropped tail."""
    tmp = Path(mkdtemp(prefix="qs_at5_"))
    try:
        body = "a,b\n" + "\n".join(
            f'{i},"{"y" * 100}"' for i in range(600)
        )
        csv = _write_csv(tmp, "full.csv", body)
        on_disk, records = _record(csv, "full.csv")
        r = _run_duckdb(on_disk, "SELECT * FROM t1", records, 0, None)
        assert r["ok"] is True
        flat = MAX_RESULT_ROWS  # page filled to the cap
        assert r["has_more"] is True
        assert r["next_offset"] == flat  # full-page advance, not `keep`
        assert len(r["rows"]) < flat  # char cap dropped some rows
        assert r["row_count"] == len(r["rows"])
    finally:
        for p in tmp.glob("*"):
            p.unlink()
        tmp.rmdir()
