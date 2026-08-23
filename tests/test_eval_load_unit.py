from __future__ import annotations

import asyncio

from library.eval.retrieval import run_load_eval_with_retriever


def test_load_eval_reports_latency_quality_and_thresholds() -> None:
    active = 0
    maximum = 0
    calls = 0

    async def retrieve(query: str, limit: int) -> list[str]:
        nonlocal active, maximum, calls
        assert limit == 3
        calls += 1
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0.001)
        active -= 1
        if query == "fails":
            raise RuntimeError("provider unavailable")
        return ["noise", "expected"]

    result = asyncio.run(run_load_eval_with_retriever(
        retrieve,
        cases=[
            ("ok", "works", {"expected"}),
            ("bad", "fails", {"expected"}),
        ],
        k=3,
        request_count=6,
        concurrency=2,
        warmup_requests=1,
        declared_corpus_size=10_000,
        max_error_rate=0.2,
        min_hit_at_k=0.8,
        min_mrr=0.4,
    ))

    assert calls == 7
    assert maximum == 2
    assert result["request_count"] == 6
    assert result["concurrency"] == 2
    assert result["declared_corpus_size"] == 10_000
    assert result["error_count"] == 3
    assert result["hit_at_k"] == 0.5
    assert result["mrr"] == 0.25
    assert result["latency_ms"]["p95"] >= 0
    assert result["ok"] is False
    assert len(result["violations"]) == 3
