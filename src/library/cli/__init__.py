"""Library CLI — interactive REPL.

  library                 # connect to localhost:8000
  python -m library.cli   # same

Slash commands match Claude Code's idiom: `/help`, `/upload`, `/ls`, `/quit`.
Anything not starting with `/` is forwarded to the agent as chat.
"""
from library.cli.client import CliHttpError, LibraryClient
from library.cli.commands import (
    COMMANDS,
    CliContext,
    chat,
    dispatch,
    list_commands,
)

__all__ = [
    "CliContext",
    "CliHttpError",
    "LibraryClient",
    "COMMANDS",
    "chat",
    "dispatch",
    "list_commands",
]
