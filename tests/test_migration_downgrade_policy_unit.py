"""Every migration must state what its downgrade does.

A bare `pass` in `downgrade()` reads as "reverted" and returns success, but
for a migration that changed the schema it leaves the database at the newer
shape while alembic_version moves back. The two then disagree with nothing to
signal it, and the next `upgrade head` re-runs the migration against a
database that already has its changes.

So the policy is: a downgrade either really reverts, or raises, or is an
explicit documented no-op for a migration that changed no schema. What it may
never be is an undocumented `pass`.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"

# Migrations that only repair data. A no-op downgrade is correct for these:
# there is no schema change to revert, and the prior data state was wrong.
_DATA_ONLY_REVISIONS = {
    "0004_repair_dangling_file_entries_fks",
    "0013_reconcile_dead_ingest_files",
}


def _migration_files() -> list[Path]:
    files = sorted(p for p in _VERSIONS.glob("*.py") if p.name != "__init__.py")
    assert files, "no migrations found"
    return files


def _downgrade_node(path: Path) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "downgrade":
            return node
    raise AssertionError(f"{path.name} has no downgrade()")


@pytest.mark.parametrize("path", _migration_files(), ids=lambda p: p.stem)
def test_downgrade_is_never_an_undocumented_pass(path: Path) -> None:
    node = _downgrade_node(path)
    body = node.body
    docstring = ast.get_docstring(node)

    is_bare_pass = len(body) == 1 and isinstance(body[0], ast.Pass)
    is_bare_return_none = (
        len(body) == 1
        and isinstance(body[0], ast.Return)
        and (body[0].value is None or getattr(body[0].value, "value", ...) is None)
    )
    if (is_bare_pass or is_bare_return_none) and not docstring:
        raise AssertionError(
            f"{path.stem}.downgrade() is an undocumented no-op. Either revert "
            "the change, raise NotImplementedError explaining why it cannot be "
            "reverted, or document why nothing needs reverting."
        )


@pytest.mark.parametrize("path", _migration_files(), ids=lambda p: p.stem)
def test_no_op_downgrades_are_data_only_migrations(path: Path) -> None:
    """A documented no-op is only legitimate when no schema changed."""
    node = _downgrade_node(path)
    body = node.body
    # Strip ONLY a leading docstring. Filtering every ast.Expr would also
    # discard `op.execute(...)` / `op.drop_table(...)`, which are expression
    # statements too — that would misread a real downgrade as a no-op.
    statements = list(body)
    if ast.get_docstring(node) is not None:
        statements = statements[1:]
    no_op = not statements or all(
        isinstance(n, (ast.Pass, ast.Return)) for n in statements
    )
    if no_op:
        assert path.stem in _DATA_ONLY_REVISIONS, (
            f"{path.stem}.downgrade() does nothing, but the migration is not in "
            "the data-only allowlist. If it changes schema, it must raise "
            "instead of silently reporting success."
        )


@pytest.mark.parametrize(
    "revision",
    sorted(
        {
            "0002_additive_columns",
            "0003_file_entries_folder_id_nullable",
            "0005_sessions_end_reason_check",
            "0012_journal_invalidation",
            "0014_files_kind_check",
        }
    ),
)
def test_irreversible_migrations_raise_with_guidance(revision: str) -> None:
    """Loud failure beats a lie. The message must also tell the operator what
    to do instead, or the raise is just an obstacle."""
    import importlib.util

    path = _VERSIONS / f"{revision}.py"
    spec = importlib.util.spec_from_file_location(f"_mig_{revision}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with pytest.raises(NotImplementedError) as excinfo:
        module.downgrade()

    message = str(excinfo.value)
    assert revision in message
    assert "roll back" in message.lower()


def test_data_only_downgrades_still_succeed() -> None:
    """The legitimate no-ops must stay callable — they are not errors."""
    import importlib.util

    for revision in sorted(_DATA_ONLY_REVISIONS):
        path = _VERSIONS / f"{revision}.py"
        spec = importlib.util.spec_from_file_location(f"_mig_{revision}", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.downgrade() is None
