from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from library.agent import runtime
from library.agent.cache_metrics import summarize_llm_calls
from library.agent.stable_context import (
    ConversationHistoryIntegrityError,
    _validated_tool_calls,
)
from library.agent.tools import (
    ToolContext,
    ToolPolicy,
    ToolRegistration,
    _canonical_schema,
    get_tool,
)
from library.api.routes_agent import _cache_metric_fields
from library.llm import ChatMessage, PromptPrefixTracker, PromptPrefixViolation, ToolDef
from library.llm.types import ToolCall
from library.tasks.usage import bind_accumulator, current_usage, measure_stage, unbind_accumulator


def test_prompt_prefix_tracker_accepts_append_only_lineage() -> None:
    tracker = PromptPrefixTracker()
    tools = [ToolDef(name="read", description="read", input_schema={"type": "object"})]
    first_messages = [ChatMessage(role="user", content="question")]
    first = tracker.observe(
        system="fixed",
        tools=tools,
        messages=first_messages,
        prompt_tokens=120,
    )
    second = tracker.observe(
        system="fixed",
        tools=tools,
        messages=[*first_messages, ChatMessage(role="assistant", content="working")],
        prompt_tokens=180,
    )

    assert first.prefix_preserved is None
    assert second.prefix_preserved is True
    assert second.cached_prefix_messages == 1
    assert second.cache_eligible_tokens == 120


def test_tool_schema_canonicalization_sorts_objects_only() -> None:
    schema = {
        "z": {"b": 2, "a": 1},
        "a": [{"d": 4, "c": 3}, "keep-array-order"],
    }

    assert list(_canonical_schema(schema)) == ["a", "z"]
    assert list(_canonical_schema(schema)["z"]) == ["a", "b"]
    assert _canonical_schema(schema)["a"][1] == "keep-array-order"


def test_registered_tools_publish_recovery_and_concurrency_policy() -> None:
    chart = get_tool("generate_chart")
    recall = get_tool("recall_knowledge")

    assert chart is not None
    assert chart.policy.access == "write"
    assert chart.policy.replay == "idempotent"
    assert chart.policy.concurrency == "session_serial"
    assert recall is not None
    assert recall.policy.concurrency == "session_serial"


def test_prompt_prefix_tracker_rejects_rewritten_history() -> None:
    tracker = PromptPrefixTracker()
    tracker.observe(
        system="fixed",
        tools=[],
        messages=[ChatMessage(role="user", content="one")],
        prompt_tokens=10,
    )

    with pytest.raises(PromptPrefixViolation):
        tracker.observe(
            system="fixed",
            tools=[],
            messages=[ChatMessage(role="user", content="changed")],
            prompt_tokens=10,
        )


def test_cache_metrics_report_eligible_hit_and_reuse() -> None:
    summary = summarize_llm_calls([
        {
            "prompt_tokens": 200,
            "cache_read_tokens": 80,
            "cache_creation_tokens": 20,
            "prompt_prefix_preserved": True,
            "cache_eligible_tokens": 100,
        },
        {
            "prompt_tokens": 50,
            "cache_read_tokens": 0,
            "prompt_prefix_preserved": False,
        },
    ])

    assert summary.prompt_coverage_ratio == 0.4
    assert summary.eligible_hit_ratio == 0.8
    assert summary.eligible_reuse_ratio == 0.8
    assert summary.prefix_breaks == 1


def test_cache_metrics_are_exposed_with_live_event_field_names() -> None:
    metrics = _cache_metric_fields([{
        "prompt_tokens": 200,
        "cache_read_tokens": 80,
        "cache_creation_tokens": 20,
        "prompt_prefix_preserved": True,
        "cache_eligible_tokens": 100,
    }])

    assert metrics == {
        "prompt_tokens": 200,
        "cache_read": 80,
        "cache_creation": 20,
        "cache_eligible_prompt_tokens": 200,
        "cache_eligible_read_tokens": 80,
        "cache_eligible_estimated_tokens": 100,
        "cache_eligible_requests": 1,
        "cache_prompt_coverage_ratio": 0.4,
        "cache_eligible_hit_ratio": 0.8,
        "cache_eligible_reuse_ratio": 0.8,
        "prompt_prefix_breaks": 0,
        "cache_slo": {
            "status": "insufficient_data",
            "minimum_hit_ratio": 0.95,
            "minimum_eligible_requests": 2,
        },
    }


def test_cache_slo_reports_met_breached_and_insufficient_data() -> None:
    insufficient = _cache_metric_fields([{
        "prompt_tokens": 100,
        "cache_read_tokens": 100,
        "prompt_prefix_preserved": True,
    }])
    met = _cache_metric_fields([
        {
            "prompt_tokens": 100,
            "cache_read_tokens": 100,
            "cache_eligible_tokens": 100,
            "prompt_prefix_preserved": True,
        },
        {
            "prompt_tokens": 100,
            "cache_read_tokens": 95,
            "cache_eligible_tokens": 100,
            "prompt_prefix_preserved": True,
        },
    ])
    breached = _cache_metric_fields([
        {
            "prompt_tokens": 100,
            "cache_read_tokens": 50,
            "cache_eligible_tokens": 100,
            "prompt_prefix_preserved": True,
        },
        {
            "prompt_tokens": 100,
            "cache_read_tokens": 50,
            "cache_eligible_tokens": 100,
            "prompt_prefix_preserved": True,
        },
    ])

    assert insufficient["cache_slo"]["status"] == "insufficient_data"
    assert met["cache_slo"]["status"] == "met"
    assert breached["cache_slo"]["status"] == "breached"


@pytest.mark.asyncio
async def test_single_tool_timeout_is_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeDb:
        async def commit(self) -> None:
            return None

    @asynccontextmanager
    async def fake_session_scope():
        yield FakeDb()

    async def slow_handler(_db, _ctx, _args):
        await asyncio.sleep(1)
        return {"ok": True}

    registration = ToolRegistration(
        name="slow",
        description="slow",
        input_schema={"type": "object"},
        handler=slow_handler,
        policy=ToolPolicy(timeout_seconds=0.01),
    )
    monkeypatch.setattr(runtime, "session_scope", fake_session_scope)

    _duration, result, error = await runtime._run_tool(
        registration,
        ToolContext(session_id="s", conversation_id="c"),
        SimpleNamespace(arguments={}),
    )

    assert result is None
    assert isinstance(error, TimeoutError)


@pytest.mark.asyncio
async def test_fatal_tool_failure_stops_later_waves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[str] = []
    persisted: list[str] = []
    registrations = {
        "first": SimpleNamespace(policy=ToolPolicy(concurrency="parallel")),
        "second": SimpleNamespace(policy=ToolPolicy(concurrency="parallel")),
        "serial": SimpleNamespace(policy=ToolPolicy(concurrency="session_serial")),
    }

    async def fake_run(_registration, _ctx, tool_call):  # noqa: ANN001
        started.append(tool_call.name)
        if tool_call.name == "first":
            return 1, None, RuntimeError("fatal executor failure")
        await asyncio.sleep(0.001)
        return 2, {"ok": True}, None

    async def fake_persist(**kwargs):  # noqa: ANN003
        persisted.append(kwargs["name"])

    monkeypatch.setattr(runtime, "get_tool", registrations.get)
    monkeypatch.setattr(runtime, "_run_tool", fake_run)
    monkeypatch.setattr(runtime, "_persist_tool_call", fake_persist)
    monkeypatch.setattr(
        runtime,
        "get_settings",
        lambda: SimpleNamespace(agent_max_parallel_tool_calls=2),
    )

    blocks = []
    events = [
        event
        async for event in runtime._dispatch_tool_calls(
            tool_calls=[
                ToolCall(id="c1", name="first", arguments={"q": "a"}),
                ToolCall(id="c2", name="second", arguments={"q": "b"}),
                ToolCall(id="c3", name="serial", arguments={"q": "c"}),
            ],
            ctx=ToolContext(session_id="s", conversation_id="c"),
            conversation_id="c",
            result_blocks=blocks,
            guard=runtime._CallGuard(),
        )
    ]

    assert started == ["first", "second"]
    assert persisted == ["first", "second", "serial"]
    assert len(blocks) == 3
    assert blocks[-1].is_error is True
    assert any('"not_started": true' in event.data for event in events)


def test_corrupt_resumed_tool_history_fails_closed() -> None:
    conversation = SimpleNamespace(
        id="conversation-1",
        tool_calls=[{"name": "read", "arguments": "not-an-object"}],
    )

    with pytest.raises(ConversationHistoryIntegrityError):
        _validated_tool_calls(conversation)


def test_task_stage_durations_are_accumulated() -> None:
    token = bind_accumulator()
    try:
        with measure_stage("extraction"):
            pass
        with measure_stage("extraction"):
            pass
        counters = current_usage()
        assert counters is not None
        detail = counters.to_detail(duration_ms=5)
        assert "extraction" in detail["stages_ms"]
    finally:
        unbind_accumulator(token)
