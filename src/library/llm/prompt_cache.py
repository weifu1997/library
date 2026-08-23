"""Prompt-layout helpers for provider-side prefix caches.

DeepSeek's disk cache only hits a prefix after that prefix has been stored
as a complete cache unit. A stable prelude followed by a changing payload in
one user message therefore may miss on the second request (`A+B` then `A+C`).

These helpers put the stable prelude in its own user message, followed by a
fixed assistant acknowledgement, then append the variable payload as the live
user message. Providers that cache complete message prefixes can then reuse
the stable unit as soon as it has been written. Anthropic callers should keep
`cache_breakpoints=[0]` so the first user message is explicitly cache-marked.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from library.llm.types import (
    ChatMessage,
    ContentBlock,
    ImageBlock,
    TextBlock,
    ToolDef,
    ToolResultBlock,
    ToolUseBlock,
)

CACHE_PREFIX_ACK = (
    "Context received. I will apply it to the next user message."
)


def cacheable_prefix_messages(stable_prefix: str) -> list[ChatMessage]:
    """Return the stable prefix as a complete message pair."""
    return [
        ChatMessage(role="user", content=[TextBlock(text=stable_prefix)]),
        ChatMessage(role="assistant", content=CACHE_PREFIX_ACK),
    ]


def cacheable_prompt_messages(
    stable_prefix: str,
    variable_content: str | Sequence[ContentBlock],
) -> list[ChatMessage]:
    """Build a cache-friendly prompt from stable and variable parts."""
    if isinstance(variable_content, str):
        payload: str | list[ContentBlock] = variable_content
    else:
        payload = list(variable_content)
    return cacheable_prefix_messages(stable_prefix) + [
        ChatMessage(role="user", content=payload),
    ]


def serialize_chat_message(message: ChatMessage) -> dict[str, Any]:
    """Return a canonical provider-neutral representation of one message."""
    content: str | list[dict[str, Any]]
    if isinstance(message.content, str):
        content = message.content
    else:
        content = [_serialize_content_block(block) for block in message.content]
    return {"role": message.role, "content": content}


def canonical_prompt_fingerprint(
    *,
    system: str,
    tools: Sequence[ToolDef] | None,
    messages: Sequence[ChatMessage],
) -> str:
    payload = {
        "system": system,
        "tools": [_serialize_tool(tool) for tool in (tools or ())],
        "messages": [serialize_chat_message(message) for message in messages],
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


class PromptPrefixViolation(RuntimeError):
    """Raised when a warm model request rewrites its visible prefix."""


@dataclass(frozen=True, slots=True)
class PromptPrefixObservation:
    epoch: int
    fingerprint: str
    header_fingerprint: str
    message_count: int
    cached_prefix_messages: int
    cache_eligible_tokens: int
    prefix_preserved: bool | None
    break_reason: str | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "prompt_epoch": self.epoch,
            "prompt_fingerprint": self.fingerprint,
            "prompt_header_fingerprint": self.header_fingerprint,
            "prompt_message_count": self.message_count,
            "cached_prefix_messages": self.cached_prefix_messages,
            "cache_eligible_tokens": self.cache_eligible_tokens,
            "prompt_prefix_preserved": self.prefix_preserved,
            "prompt_epoch_break_reason": self.break_reason,
        }


class PromptPrefixTracker:
    """Verify that successive requests append to the prior prompt lineage."""

    def __init__(self) -> None:
        self._epoch = 0
        self._header: str | None = None
        self._messages: tuple[str, ...] = ()
        self._prompt_tokens = 0

    def observe(
        self,
        *,
        system: str,
        tools: Sequence[ToolDef] | None,
        messages: Sequence[ChatMessage],
        prompt_tokens: int | None = None,
        allow_epoch_break: bool = False,
        break_reason: str | None = None,
    ) -> PromptPrefixObservation:
        header = _canonical_json({
            "system": system,
            "tools": [_serialize_tool(tool) for tool in (tools or ())],
        })
        current = tuple(
            _canonical_json(serialize_chat_message(message))
            for message in messages
        )
        first = self._header is None
        preserved = (
            not first
            and header == self._header
            and len(current) >= len(self._messages)
            and current[:len(self._messages)] == self._messages
        )
        if not first and not preserved:
            if not allow_epoch_break:
                raise PromptPrefixViolation(
                    "model-visible request rewrote its system/tools/messages "
                    "prefix without an explicit prompt epoch boundary"
                )
            self._epoch += 1
        effective_reason = break_reason if not first and not preserved else None
        fingerprint = hashlib.sha256(
            (header + "\n" + "\n".join(current)).encode("utf-8")
        ).hexdigest()
        observation = PromptPrefixObservation(
            epoch=self._epoch,
            fingerprint=fingerprint,
            header_fingerprint=hashlib.sha256(header.encode("utf-8")).hexdigest(),
            message_count=len(current),
            cached_prefix_messages=len(self._messages) if preserved else 0,
            cache_eligible_tokens=self._prompt_tokens if preserved else 0,
            prefix_preserved=None if first else preserved,
            break_reason=effective_reason,
        )
        self._header = header
        self._messages = current
        self._prompt_tokens = max(0, int(prompt_tokens or 0))
        return observation


def _serialize_tool(tool: ToolDef | dict[str, Any]) -> dict[str, Any]:
    if isinstance(tool, dict):
        return {
            "name": tool.get("name"),
            "description": tool.get("description"),
            "input_schema": tool.get("input_schema") or {},
        }
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
    }


def _serialize_content_block(block: ContentBlock) -> dict[str, Any]:
    if isinstance(block, TextBlock):
        return {"kind": "text", "text": block.text}
    if isinstance(block, ImageBlock):
        return {
            "kind": "image",
            "media_type": block.media_type,
            "data_b64": block.data_b64,
        }
    if isinstance(block, ToolUseBlock):
        return {
            "kind": "tool_use",
            "id": block.id,
            "name": block.name,
            "arguments": block.arguments,
        }
    if isinstance(block, ToolResultBlock):
        return {
            "kind": "tool_result",
            "tool_call_id": block.tool_call_id,
            "content": block.content,
            "is_error": block.is_error,
        }
    raise TypeError(f"unsupported content block: {type(block).__name__}")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
