"""Deterministic OpenAPI export. Does not start the app lifespan."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from library import __version__
from library.main import app

_REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = _REPO_ROOT / "openapi" / "openapi.json"

# Live secrets must never appear in the committed spec. Schema field *names*
# such as api_key are expected; values that look like tokens are not.
_SECRET_VALUE = re.compile(
    r"(sk-[A-Za-z0-9]{10,}|Bearer [A-Za-z0-9._\-]{16,}|postgresql\+asyncpg://[^\"\\s]+)"
)


def build_spec() -> dict:
    spec = app.openapi()
    spec.setdefault("info", {})
    spec["info"]["title"] = spec["info"].get("title") or "Library"
    spec["info"]["version"] = __version__
    return spec


def render(spec: dict) -> str:
    return json.dumps(spec, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def assert_no_secrets(text: str) -> None:
    match = _SECRET_VALUE.search(text)
    if match:
        raise SystemExit(
            "refusing to export OpenAPI: possible secret value in spec: "
            f"{match.group(0)[:12]}…"
        )


def export(*, path: Path | None = None) -> Path:
    target = path or OUTPUT_PATH
    text = render(build_spec())
    assert_no_secrets(text)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def main() -> None:
    written = export()
    print(f"wrote {written}", file=sys.stderr)


if __name__ == "__main__":
    main()
