"""Internal signal that closes evidence gathering before final composition."""
from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from library.agent.tools import ToolContext, ToolPolicy, tool


DESCRIPTION = (
    "Finish the evidence-gathering phase for the current request. Call this only "
    "after enough verified evidence has been collected, or targeted searches show "
    "that the requested evidence is unavailable. When evidence is sufficient and "
    "read_files returned source text, declare the exact citations that support the "
    "answer. The runtime validates them, assigns footnote markers, and persists a "
    "citation manifest. This does not answer the user; after it succeeds, write the "
    "final answer in the next response and use the assigned markers."
)

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "evidence_status": {
            "type": "string",
            "enum": ["sufficient", "insufficient"],
            "description": (
                "Whether the collected evidence is sufficient for a supported "
                "answer. Use insufficient only after targeted searches or reads."
            ),
        },
        "reason": {
            "type": "string",
            "maxLength": 500,
            "description": "Brief internal reason for ending evidence gathering.",
        },
        "citations": {
            "type": "array",
            "maxItems": 20,
            "description": (
                "Exact source citations selected from successful read_files text. "
                "Required when evidence_status is sufficient and source text was "
                "read; omit or pass [] when evidence is insufficient."
            ),
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "entry_id": {
                        "type": "string",
                        "minLength": 7,
                        "maxLength": 36,
                        "pattern": "^[0-9a-fA-F][0-9a-fA-F-]{6,35}$",
                        "description": "Entry ID returned by read_files.",
                    },
                    "quote": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 500,
                        "description": (
                            "Verbatim visible source text from read_files; do not "
                            "quote omitted or metadata-only content."
                        ),
                    },
                    "page": {
                        "type": "integer",
                        "minimum": 1,
                        "description": (
                            "Verified physical PDF page or PPTX slide number. "
                            "Omit when the read result did not establish one."
                        ),
                    },
                    "reason": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 500,
                        "description": "How this source supports the answer.",
                    },
                },
                "required": ["entry_id", "quote", "reason"],
            },
        },
    },
    "required": ["evidence_status"],
}


@tool(
    name="finish_research",
    description=DESCRIPTION,
    schema=SCHEMA,
    policy=ToolPolicy(
        access="read",
        replay="safe",
        confirmation="never",
        timeout_seconds=30.0,
        concurrency="session_serial",
    ),
)
async def finish_research(
    db: AsyncSession,
    ctx: ToolContext,
    args: Mapping[str, Any],
) -> dict[str, Any]:
    del db, ctx
    evidence_status = str(args.get("evidence_status") or "")
    reason = str(args.get("reason") or "").strip()
    return {
        "ok": True,
        "evidence_status": evidence_status,
        **({"reason": reason} if reason else {}),
        "next": "Write the final answer now without calling more tools.",
    }
