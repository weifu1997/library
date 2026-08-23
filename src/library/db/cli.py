"""One-shot database preparation for managed deployments."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from alembic import command
from alembic.config import Config


def _alembic_configuration() -> Config:
    """Resolve migration assets in source trees and installed images."""
    explicit = str(os.environ.get("ALEMBIC_CONFIG") or "").strip()
    candidates = (
        [Path(explicit).expanduser()]
        if explicit
        else [
            Path.cwd() / "alembic.ini",
            Path(__file__).resolve().parents[3] / "alembic.ini",
        ]
    )
    checked: list[str] = []
    for candidate in candidates:
        config_path = candidate.resolve()
        checked.append(str(config_path))
        if not config_path.is_file():
            continue
        configuration = Config(str(config_path))
        configured_location = (
            configuration.get_main_option("script_location") or "alembic"
        )
        script_location = Path(configured_location)
        if not script_location.is_absolute():
            script_location = config_path.parent / script_location
        script_location = script_location.resolve()
        if not script_location.is_dir():
            raise SystemExit(
                f"Alembic script directory does not exist: {script_location}"
            )
        configuration.set_main_option("script_location", str(script_location))
        return configuration
    raise SystemExit(
        "Alembic configuration not found; checked: " + ", ".join(checked)
    )


def _run_alembic_upgrade() -> None:
    command.upgrade(_alembic_configuration(), "head")


async def _force_compatibility_bootstrap() -> None:
    from library.db.bootstrap import bootstrap_schema
    from library.db.engine import dispose_engine

    try:
        await bootstrap_schema(force=True)
    finally:
        await dispose_engine()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="library-db-prepare",
        description=(
            "Upgrade Alembic and explicitly run the idempotent compatibility "
            "bootstrap before API and worker rollout."
        ),
    )
    parser.add_argument(
        "--migrations-only",
        action="store_true",
        help="Run Alembic only; skip the explicit compatibility bootstrap.",
    )
    args = parser.parse_args(argv)
    _run_alembic_upgrade()
    if not args.migrations_only:
        asyncio.run(_force_compatibility_bootstrap())
    print(json.dumps({
        "alembic": "head",
        "bootstrap": not args.migrations_only,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
