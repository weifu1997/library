"""INGEST-M1 — git HEAD branch names must not escape ``.git/``."""
from __future__ import annotations

from pathlib import Path

from library.pipelines.git_metadata import _safe_branch_name, parse

_HASH = "fed4444444444444444444444444444444444444"


def _write_git(
    root: Path,
    *,
    head: str,
    refs: dict[str, str] | None = None,
    packed: str | None = None,
) -> None:
    git = root / ".git"
    git.mkdir(parents=True)
    (git / "HEAD").write_text(head, encoding="utf-8")
    for name, content in (refs or {}).items():
        path = git / "refs" / "heads" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    if packed is not None:
        (git / "packed-refs").write_text(packed, encoding="utf-8")


def test_safe_branch_name_allows_nested_and_rejects_traversal() -> None:
    assert _safe_branch_name("main") == "main"
    assert _safe_branch_name("feature/login") == "feature/login"
    assert _safe_branch_name("../../secret") is None
    assert _safe_branch_name("foo/../../../etc/passwd") is None
    assert _safe_branch_name("..") is None
    assert _safe_branch_name("foo\\bar") is None
    assert _safe_branch_name("") is None


def test_parse_reads_normal_and_nested_branch(tmp_path: Path) -> None:
    _write_git(
        tmp_path,
        head="ref: refs/heads/main\n",
        refs={"main": f"{_HASH}\n"},
    )
    meta = parse(tmp_path)
    assert meta is not None
    assert meta.branch == "main"
    assert meta.head_hash == _HASH

    nested = tmp_path / "nested"
    _write_git(
        nested,
        head="ref: refs/heads/feature/login\n",
        refs={"feature/login": f"{_HASH}\n"},
    )
    nested_meta = parse(nested)
    assert nested_meta is not None
    assert nested_meta.branch == "feature/login"
    assert nested_meta.head_hash == _HASH


def test_parse_rejects_dotdot_branch_and_does_not_read_outside(
    tmp_path: Path,
) -> None:
    secret = tmp_path / "secret"
    secret.write_text("LEAKED_SHOULD_NOT_APPEAR\n", encoding="utf-8")
    _write_git(tmp_path, head="ref: refs/heads/../../secret\n")
    meta = parse(tmp_path)
    assert meta is not None
    assert meta.branch is None
    assert meta.head_hash is None


def test_parse_packed_refs_still_resolves_missing_loose_ref(
    tmp_path: Path,
) -> None:
    _write_git(
        tmp_path,
        head="ref: refs/heads/main\n",
        packed=f"{_HASH} refs/heads/main\n",
    )
    meta = parse(tmp_path)
    assert meta is not None
    assert meta.branch == "main"
    assert meta.head_hash == _HASH
