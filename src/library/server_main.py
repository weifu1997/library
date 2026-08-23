from __future__ import annotations

import argparse
import logging
import os
import sys

import uvicorn


def build_arg_parser(prog: str = "library serve") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Run the Library HTTP backend and worker.",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Host to bind. Defaults to LIBRARY_API_HOST, .env, or 127.0.0.1.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to bind. Defaults to LIBRARY_API_PORT, .env, or 8000.",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        help="Uvicorn log level. Defaults to LIBRARY_API_LOG_LEVEL or info.",
    )
    return parser


def main(argv: list[str] | None = None, *, prog: str = "library serve") -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list and args_list[0] == "serve":
        args_list = args_list[1:]
    parser = build_arg_parser(prog=prog)
    args = parser.parse_args(args_list)

    from library.config import get_settings

    settings = get_settings()
    host = args.host or settings.library_api_host
    port = int(args.port or settings.library_api_port)
    log_level = args.log_level or os.environ.get("LIBRARY_API_LOG_LEVEL", "info")

    os.environ["LIBRARY_API_HOST"] = host
    os.environ["LIBRARY_API_PORT"] = str(port)
    os.environ["LIBRARY_HTTP_SERVER"] = "1"
    os.environ.setdefault("PYTHONUNBUFFERED", "1")

    logging.basicConfig(
        level=log_level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    uvicorn.run(
        "library.main:app",
        host=host,
        port=port,
        log_level=log_level,
        access_log=False,
    )
    return 0
