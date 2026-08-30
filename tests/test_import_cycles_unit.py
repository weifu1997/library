"""Service modules must be importable on their own.

`library.services.user_files` used to fail when it was the first thing a
process imported:

    user_files -> pipelines.registry -> pipelines.archive -> tasks
      -> tasks.runner -> tasks.handlers -> mine_relations
      -> mine_citation_graph -> services.exports -> user_files

The test suite never hit it because other modules were imported first, so the
cycle only surfaced in a bare interpreter — a script, a REPL, or anything that
reaches for one service without booting the app. Each module is imported in a
fresh subprocess so import order cannot hide a regression.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

_STANDALONE_MODULES = [
    "library.services.user_files",
    "library.services.exports",
    "library.services.folders",
    "library.services.webdav_sync",
    "library.services.entries",
    "library.services.upload",
    "library.repositories.folders",
    "library.pipelines.registry",
]


@pytest.mark.parametrize("module", _STANDALONE_MODULES)
def test_module_imports_standalone(module: str) -> None:
    """A fresh interpreter, importing only this module."""
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"`import {module}` failed in a fresh interpreter — most likely a new "
        f"import cycle:\n{result.stderr[-2000:]}"
    )
