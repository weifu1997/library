"""ACCESS-M1/M2: eval dataset names and MCP destination jail."""
from __future__ import annotations

from pathlib import Path

import pytest

from library.eval.datasets import refuse_eval_write_to_live_library, safe_eval_dataset_name
from library.mcp_server import INVALID_PARAMS, JsonRpcError, _destination_path


def test_safe_eval_dataset_name_rejects_traversal(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LIBRARY_HOME", str(tmp_path))
    from library.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]

    with pytest.raises(ValueError):
        safe_eval_dataset_name("../tmp/pwn")
    with pytest.raises(ValueError):
        safe_eval_dataset_name("a/b")
    with pytest.raises(ValueError):
        safe_eval_dataset_name("..")
    assert safe_eval_dataset_name("nq") == "nq"


def test_refuse_eval_write_without_flag(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LIBRARY_HOME", str(tmp_path / "LibraryData"))
    from library.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="write-library"):
        refuse_eval_write_to_live_library(write_library=False)
    refuse_eval_write_to_live_library(write_library=True)


def test_destination_path_must_be_under_home(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    allowed = _destination_path(str(tmp_path / "out.zip"))
    assert allowed == (tmp_path / "out.zip").resolve()
    with pytest.raises(JsonRpcError) as exc:
        _destination_path("/etc/passwd")
    assert exc.value.code == INVALID_PARAMS
