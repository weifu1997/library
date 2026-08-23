"""Token-aware, request-local compaction for conversation history.

Stored turns remain lossless. When a provider request would exceed the
configured context window, completed atomic message groups are summarized into
a structured checkpoint while the newest complete groups remain verbatim.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from library.llm import ChatMessage, ToolResultBlock, ToolUseBlock


CHECKPOINT_VERSION = 1
CHECKPOINT_MESSAGE_PREFIX = "[Conversation compaction checkpoint]"
_CITATION_RE = re.compile(r"entry_id=([0-9a-fA-F-]{8,})")
_CONSTRAINT_TERMS = ("must", "never", "required", "cannot", "必须", "不要", "不能", "要求")
_DECISION_TERMS = ("decision", "decided", "recommend", "conclusion", "决定", "结论", "建议")
_NEXT_TERMS = ("next", "todo", "remaining", "下一步", "待办", "尚未")


class TokenCounter:
    """Model-token counter with a conservative dependency-free fallback."""

    def __init__(self, tokenizer: str) -> None:
        self.tokenizer = tokenizer or "utf8_upper_bound"
        self._encoding: Any = None
        if self.tokenizer != "utf8_upper_bound":
            try:
                import tiktoken

                self._encoding = tiktoken.get_encoding(self.tokenizer)
            except Exception:  # noqa: BLE001 - a conservative fallback is intentional
                self._encoding = None

    @property
    def exact(self) -> bool:
        return self._encoding is not None

    def text(self, value: str) -> int:
        if not value:
            return 0
        if self._encoding is not None:
            return len(self._encoding.encode(value, disallowed_special=()))
        # A UTF-8 byte cannot encode to more than one model token. This keeps
        # the hard limit safe for CJK even when the configured tokenizer is not
        # installed or its name is invalid.
        return len(value.encode("utf-8"))

    def message(self, message: ChatMessage) -> int:
        total = 4 + self.text(message.role)
        content = message.content
        if isinstance(content, str):
            return total + self.text(content)
        for block in content or []:
            if isinstance(block, ToolUseBlock):
                total += self.text(block.id) + self.text(block.name)
                total += self.text(
                    json.dumps(block.arguments, ensure_ascii=False, default=str)
                )
            elif isinstance(block, ToolResultBlock):
                total += self.text(block.tool_call_id) + self.text(block.content)
            elif getattr(block, "kind", None) == "image":
                # Base64 size does not represent provider image-token usage.
                total += 8_192
            else:
                total += self.text(str(getattr(block, "text", "")))
        return total

    def messages(self, messages: Iterable[ChatMessage]) -> int:
        return sum(self.message(message) for message in messages)


@dataclass(slots=True)
class TurnSnapshot:
    turn_index: int
    user_message: str
    agent_response: str | None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class ConversationCheckpoint:
    summary: dict[str, Any]
    through_turn_index: int
    retained_from_turn: int | None
    tokens_before: int
    summary_tokens: int
    tokenizer: str
    exact_token_count: bool
    split_turn: bool = False

    def message(self) -> ChatMessage:
        rendered = json.dumps(self.summary, ensure_ascii=False, indent=2, default=str)
        return ChatMessage(
            role="user",
            content=f"{CHECKPOINT_MESSAGE_PREFIX}\n{rendered}",
        )


def fit_messages_to_token_budget(
    messages: list[ChatMessage],
    *,
    token_budget: int,
    counter: TokenCounter,
) -> tuple[list[ChatMessage], ConversationCheckpoint | None]:
    """Fit a request to a hard input budget without splitting tool exchanges."""
    budget = max(128, int(token_budget))
    tokens_before = counter.messages(messages)
    if tokens_before <= budget:
        return messages, None

    groups = _atomic_message_groups(messages)
    kept: list[list[ChatMessage]] = []
    used = 0
    checkpoint_reserve = min(4_096, max(256, budget // 2))
    tail_budget = max(0, budget - checkpoint_reserve)
    for group in reversed(groups):
        size = counter.messages(group)
        if used + size > tail_budget:
            break
        kept.append(group)
        used += size
    kept.reverse()

    omitted_count = len(groups) - len(kept)
    snapshots = [
        _messages_to_snapshot(index + 1, group)
        for index, group in enumerate(groups[:omitted_count])
    ]
    checkpoint = build_checkpoint(
        snapshots,
        through_turn_index=len(snapshots),
        retained_from_turn=(len(snapshots) + 1 if kept else None),
        tokens_before=tokens_before,
        counter=counter,
        summary_token_budget=max(128, budget - used),
        split_turn=(len(groups) == 1),
    )
    fitted = [checkpoint.message(), *(message for group in kept for message in group)]

    while counter.messages(fitted) > budget and kept:
        moved = kept.pop(0)
        snapshots.append(_messages_to_snapshot(len(snapshots) + 1, moved))
        used = counter.messages(message for group in kept for message in group)
        checkpoint = build_checkpoint(
            snapshots,
            through_turn_index=len(snapshots),
            retained_from_turn=(len(snapshots) + 1 if kept else None),
            tokens_before=tokens_before,
            counter=counter,
            summary_token_budget=max(128, budget - used),
            split_turn=not kept,
        )
        fitted = [checkpoint.message(), *(message for group in kept for message in group)]

    tokens_after = counter.messages(fitted)
    if tokens_after > budget:
        raise ValueError(
            "conversation checkpoint cannot fit the configured model context window"
        )
    if tokens_after >= tokens_before:
        raise ValueError("conversation checkpoint did not reduce model input tokens")
    return fitted, checkpoint


def build_checkpoint(
    turns: list[TurnSnapshot],
    *,
    through_turn_index: int,
    retained_from_turn: int | None,
    tokens_before: int,
    counter: TokenCounter,
    summary_token_budget: int,
    split_turn: bool = False,
) -> ConversationCheckpoint:
    """Build a bounded, structured summary from completed message groups."""
    summary: dict[str, Any] = {
        "version": CHECKPOINT_VERSION,
        "goal": [],
        "constraints": [],
        "progress": [],
        "key_decisions": [],
        "next_steps": [],
        "critical_context": [],
        "evidence_entry_ids": [],
        "evidence": [],
        "scopes": [],
        "tool_history": [],
    }

    for turn in turns:
        _append_unique(summary["goal"], _bounded(turn.user_message, 2_000))
        for sentence in _sentences(turn.user_message):
            if _contains(sentence, _CONSTRAINT_TERMS):
                _append_unique(summary["constraints"], _bounded(sentence, 800))
        response = turn.agent_response or ""
        if response:
            _append_unique(summary["progress"], _bounded(response, 2_500))
        for sentence in _sentences(response):
            if _contains(sentence, _DECISION_TERMS):
                _append_unique(summary["key_decisions"], _bounded(sentence, 1_000))
            if _contains(sentence, _NEXT_TERMS):
                _append_unique(summary["next_steps"], _bounded(sentence, 1_000))
        for entry_id in _CITATION_RE.findall(response):
            _append_unique(summary["evidence_entry_ids"], entry_id)
        for call in turn.tool_calls:
            if not isinstance(call, dict):
                continue
            item = {
                "turn": turn.turn_index,
                "name": str(call.get("name") or "tool"),
                "input": _bounded_json(call.get("input") or call.get("arguments"), 1_000),
                "result": _bounded_json(call.get("output") or call.get("result"), 1_500),
                "error": _bounded(str(call.get("error") or ""), 500) or None,
            }
            _append_unique(summary["tool_history"], item)
            for entry_id in _entry_ids(item):
                _append_unique(summary["evidence_entry_ids"], entry_id)
            for evidence in _evidence_refs(call):
                _append_unique(summary["evidence"], evidence)
            for scope in _scope_refs(call):
                _append_unique(summary["scopes"], scope)

    summary["critical_context"] = _critical_context(summary)
    _fit_summary(summary, counter=counter, token_budget=max(256, summary_token_budget))
    summary_tokens = counter.text(json.dumps(summary, ensure_ascii=False, default=str))
    return ConversationCheckpoint(
        summary=summary,
        through_turn_index=through_turn_index,
        retained_from_turn=retained_from_turn,
        tokens_before=tokens_before,
        summary_tokens=summary_tokens,
        tokenizer=counter.tokenizer,
        exact_token_count=counter.exact,
        split_turn=split_turn,
    )


def _fit_summary(summary: dict[str, Any], *, counter: TokenCounter, token_budget: int) -> None:
    order = (
        "tool_history", "progress", "goal", "key_decisions", "constraints",
        "next_steps", "scopes", "evidence", "evidence_entry_ids",
    )
    while counter.text(json.dumps(summary, ensure_ascii=False, default=str)) > token_budget:
        changed = False
        for key in order:
            values = summary.get(key)
            minimum = 1 if key in {"goal", "progress"} else 0
            if isinstance(values, list) and len(values) > minimum:
                values.pop(0)
                changed = True
                break
        if not changed:
            # The provider hard limit wins if even the retained goal/progress
            # minima cannot fit.
            for key in order:
                values = summary.get(key)
                if isinstance(values, list) and values:
                    values.pop(0)
                    changed = True
                    break
        if not changed:
            break
        summary["critical_context"] = _critical_context(summary)


def _critical_context(summary: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("constraints", "key_decisions", "next_steps"):
        for value in summary.get(key) or []:
            _append_unique(values, _bounded(str(value), 800))
    ids = summary.get("evidence_entry_ids") or []
    if ids:
        values.append("Evidence entry IDs: " + ", ".join(str(value) for value in ids))
    for evidence in summary.get("evidence") or []:
        values.append(
            "Evidence locator: " + json.dumps(evidence, ensure_ascii=False, default=str)
        )
    return values[-20:]


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?。！？；])\s*|\n+", text) if part.strip()]


def _contains(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _bounded(value: str, limit: int) -> str:
    value = value.strip()
    return value if len(value) <= limit else value[:limit].rstrip() + "…"


def _bounded_json(value: Any, limit: int) -> Any:
    if value is None:
        return None
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return value
    return {"preview": text[:limit].rstrip() + "…", "truncated": True}


def _append_unique(values: list[Any], value: Any) -> None:
    if value not in (None, "") and value not in values:
        values.append(value)


def _entry_ids(value: Any) -> list[str]:
    return _CITATION_RE.findall(json.dumps(value, ensure_ascii=False, default=str))


def _evidence_refs(call: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    locator_keys = (
        "entry_id", "quote", "page", "page_start", "page_end", "line_start",
        "line_end", "paragraph_start", "paragraph_end", "section_id", "heading",
        "member_path", "sha256", "content_sha256", "file_sha256", "version",
    )

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("entry_id"):
                ref = {
                    key: value[key]
                    for key in locator_keys
                    if key in value and value[key] not in (None, "")
                }
                if ref:
                    _append_unique(refs, ref)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(call.get("output") or call.get("result"))
    return refs[:100]


def _scope_refs(call: dict[str, Any]) -> list[dict[str, Any]]:
    value = call.get("input") or call.get("arguments")
    if not isinstance(value, dict):
        return []
    scope = {
        key: value[key]
        for key in ("view_id", "catalog_id", "folder_id")
        if key in value and value[key] not in (None, "", [])
    }
    return [scope] if scope else []


def _atomic_message_groups(messages: list[ChatMessage]) -> list[list[ChatMessage]]:
    """Keep assistant tool-use and all corresponding results together."""
    groups: list[list[ChatMessage]] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        group = [message]
        tool_ids = {
            block.id
            for block in (message.content if isinstance(message.content, list) else [])
            if isinstance(block, ToolUseBlock)
        }
        if tool_ids:
            index += 1
            seen: set[str] = set()
            while index < len(messages):
                candidate = messages[index]
                if candidate.role != "tool":
                    break
                result_ids = {
                    block.tool_call_id
                    for block in (
                        candidate.content if isinstance(candidate.content, list) else []
                    )
                    if isinstance(block, ToolResultBlock)
                }
                if not result_ids or not result_ids.issubset(tool_ids):
                    break
                group.append(candidate)
                seen.update(result_ids)
                index += 1
                if seen >= tool_ids:
                    break
            groups.append(group)
            continue
        groups.append(group)
        index += 1
    return groups


def _messages_to_snapshot(index: int, messages: list[ChatMessage]) -> TurnSnapshot:
    users: list[str] = []
    assistants: list[str] = []
    calls: list[dict[str, Any]] = []
    results: dict[str, Any] = {}
    for message in messages:
        if isinstance(message.content, str):
            if message.role == "user":
                users.append(message.content)
            elif message.role == "assistant":
                assistants.append(message.content)
            continue
        for block in message.content or []:
            if isinstance(block, ToolUseBlock):
                calls.append({"id": block.id, "name": block.name, "input": block.arguments})
            elif isinstance(block, ToolResultBlock):
                try:
                    results[block.tool_call_id] = json.loads(block.content)
                except (TypeError, ValueError):
                    results[block.tool_call_id] = block.content
            else:
                text = str(getattr(block, "text", ""))
                if text:
                    (users if message.role == "user" else assistants).append(text)
    for call in calls:
        call["output"] = results.get(call.get("id"))
    return TurnSnapshot(
        turn_index=index,
        user_message="\n".join(users),
        agent_response="\n".join(assistants) or None,
        tool_calls=calls,
    )


__all__ = [
    "CHECKPOINT_MESSAGE_PREFIX",
    "ConversationCheckpoint",
    "TokenCounter",
    "fit_messages_to_token_budget",
]
