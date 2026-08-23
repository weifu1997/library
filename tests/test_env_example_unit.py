from __future__ import annotations

import re
from pathlib import Path

from library.config import Settings


def test_env_example_documents_every_setting() -> None:
    text = (Path(__file__).parents[1] / ".env.example").read_text(encoding="utf-8")
    documented = {
        match.group(1)
        for line in text.splitlines()
        if (match := re.match(r"^\s*#?\s*([A-Z][A-Z0-9_]*)\s*=", line))
    }
    expected = {
        alias if isinstance(alias := field.validation_alias, str) else name.upper()
        for name, field in Settings.model_fields.items()
    }

    assert expected - documented == set()


def test_env_example_uses_only_the_unified_compression_settings() -> None:
    text = (Path(__file__).parents[1] / ".env.example").read_text(encoding="utf-8")

    assert "COMPRESSION_ENABLED=true" in text
    assert "COMPRESSION_MAX_RATIO=0.85" in text
    assert "READ_COMPRESSION_ENABLED=" not in text
