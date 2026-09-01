"""Retrieval eval runners and retrieval component ablations."""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, Iterable, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from library.agent.text_query import normalize_text_queries
from library.agent.tools import ToolContext
from library.agent.tools.recall_knowledge import (
    load_rerank_documents_by_entry_id,
    recall_knowledge,
    rerank_recall_entries_with_documents,
    score_recall_entries,
    select_evidence_entry_ids,
)
from library.agent.tools.search_metadata import search_metadata
from library.config import get_settings
from library.db.bootstrap import bootstrap_schema
from library.db.session import session_scope
from library.eval.datasets import eval_root, iter_beir_queries, load_qrels
from library.eval.metrics import _MetricAccumulator, _score_query
from library.eval.reporting import result_to_dict
from library.eval.types import BeirQuery, EvalAblationConfig, EvalAblationRunResult, EvalRunResult
from library.eval.utils import _append_unique_str, _read_json
from library.repositories import entries as entries_repo
from library.repositories import entry_relations as relations_repo
from library.semantic.index import (
    semantic_entry_rows,
    semantic_recall_configured,
    search_semantic_index_many,
)
from library.semantic.rerank import rerank_configured

async def run_eval_dataset(
    *,
    name: str,
    retriever: str = "search_metadata",
    k_values: Iterable[int] = (10, 50, 100),
    query_limit: int | None = None,
    semantic_recall: bool | None = None,
    rerank: bool | None = None,
    relation_expansion: bool | None = None,
) -> EvalRunResult:
    """Run retrieval evaluation against an already-imported eval dataset."""
    await bootstrap_schema()
    dataset_dir = eval_root() / name
    manifest_path = dataset_dir / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"eval dataset {name!r} is not imported")
    doc_map: dict[str, str] = _read_json(dataset_dir / "doc_map.json")
    entry_to_doc = {entry_id: doc_id for doc_id, entry_id in doc_map.items()}
    queries = list(iter_beir_queries(dataset_dir / "queries.jsonl"))
    if query_limit is not None:
        queries = queries[:query_limit]
    qrels = load_qrels(dataset_dir / "qrels.tsv")

    ks = sorted({int(k) for k in k_values if int(k) > 0})
    if not ks:
        ks = [10]
    max_k = max(ks)

    per_query: list[dict[str, Any]] = []
    aggregate = _MetricAccumulator(ks)
    if retriever == "semantic_recall":
        eligible: list[tuple[BeirQuery, dict[str, int]]] = []
        for q in queries:
            relevant = {
                doc_id: rel
                for doc_id, rel in qrels.get(q.query_id, {}).items()
                if doc_id in doc_map and rel > 0
            }
            if not relevant:
                aggregate.skipped += 1
                continue
            eligible.append((q, relevant))
        batched_hits = await search_semantic_index_many(
            [q.text for q, _relevant in eligible],
            limit=max_k,
        )
        for (q, relevant), hits in zip(eligible, batched_hits):
            ranked_entries = [
                hit.entry_id
                for hit in hits
                if hit.entry_id in entry_to_doc
            ]
            if relation_expansion:
                async with session_scope() as session:
                    ranked_entries = await _maybe_expand_ranked_ids(
                        session,
                        ranked_entries,
                        limit=max_k,
                        enabled=True,
                    )
            ranked_docs = [
                entry_to_doc[eid]
                for eid in ranked_entries
                if eid in entry_to_doc
            ]
            scored = _score_query(ranked_docs, relevant, ks)
            aggregate.add(scored, zero_result=not ranked_docs)
            per_query.append({
                "query_id": q.query_id,
                "query": q.text,
                "relevant_doc_ids": sorted(relevant),
                "ranked_doc_ids": ranked_docs,
                **scored,
            })
        return aggregate.result(
            name=name,
            retriever=retriever,
            queries_total=len(queries),
            per_query=per_query,
        )

    async with session_scope() as session:
        if retriever == "recall_knowledge":
            eligible = []
            for q in queries:
                relevant = {
                    doc_id: rel
                    for doc_id, rel in qrels.get(q.query_id, {}).items()
                    if doc_id in doc_map and rel > 0
                }
                if not relevant:
                    aggregate.skipped += 1
                    continue
                eligible.append((q, relevant))
            ranked_many = await _retrieve_entries_many(
                session,
                retriever=retriever,
                queries=[q.text for q, _relevant in eligible],
                limit=max_k,
                semantic_recall=semantic_recall,
                rerank=rerank,
                relation_expansion=relation_expansion,
            )
            for (q, relevant), ranked_entries in zip(eligible, ranked_many):
                ranked_docs = [
                    entry_to_doc[eid]
                    for eid in ranked_entries
                    if eid in entry_to_doc
                ]
                scored = _score_query(ranked_docs, relevant, ks)
                aggregate.add(scored, zero_result=not ranked_docs)
                per_query.append({
                    "query_id": q.query_id,
                    "query": q.text,
                    "relevant_doc_ids": sorted(relevant),
                    "ranked_doc_ids": ranked_docs,
                    **scored,
                })
            return aggregate.result(
                name=name,
                retriever=retriever,
                queries_total=len(queries),
                per_query=per_query,
            )

        for q in queries:
            relevant = {
                doc_id: rel
                for doc_id, rel in qrels.get(q.query_id, {}).items()
                if doc_id in doc_map and rel > 0
            }
            if not relevant:
                aggregate.skipped += 1
                continue
            ranked_entries = await _retrieve_entries(
                session,
                retriever=retriever,
                query=q.text,
                limit=max_k,
                relation_expansion=relation_expansion,
            )
            ranked_docs = [
                entry_to_doc[eid]
                for eid in ranked_entries
                if eid in entry_to_doc
            ]
            scored = _score_query(ranked_docs, relevant, ks)
            aggregate.add(scored, zero_result=not ranked_docs)
            per_query.append({
                "query_id": q.query_id,
                "query": q.text,
                "relevant_doc_ids": sorted(relevant),
                "ranked_doc_ids": ranked_docs,
                **scored,
            })

    return aggregate.result(
        name=name,
        retriever=retriever,
        queries_total=len(queries),
        per_query=per_query,
    )


async def run_load_eval_dataset(
    *,
    name: str,
    retriever: str = "recall_knowledge",
    k: int = 5,
    request_count: int = 1_000,
    concurrency: int = 20,
    warmup_requests: int = 20,
    declared_corpus_size: int | None = None,
    max_error_rate: float = 0.01,
    max_p95_ms: float | None = None,
    min_hit_at_k: float | None = None,
    min_mrr: float | None = None,
) -> dict[str, Any]:
    """Run bounded concurrent retrieval latency and quality checks."""
    await bootstrap_schema()
    dataset_dir = eval_root() / name
    if not (dataset_dir / "manifest.json").exists():
        raise RuntimeError(f"eval dataset {name!r} is not imported")
    doc_map: dict[str, str] = _read_json(dataset_dir / "doc_map.json")
    qrels = load_qrels(dataset_dir / "qrels.tsv")
    cases: list[tuple[str, str, set[str]]] = []
    for query in iter_beir_queries(dataset_dir / "queries.jsonl"):
        expected = {
            doc_map[doc_id]
            for doc_id, relevance in qrels.get(query.query_id, {}).items()
            if relevance > 0 and doc_id in doc_map
        }
        if expected:
            cases.append((query.query_id, query.text, expected))

    async def retrieve(query: str, limit: int) -> list[str]:
        async with session_scope() as session:
            return await _retrieve_entries(
                session,
                retriever=retriever,
                query=query,
                limit=limit,
            )

    return await run_load_eval_with_retriever(
        retrieve,
        cases=cases,
        k=k,
        request_count=request_count,
        concurrency=concurrency,
        warmup_requests=warmup_requests,
        declared_corpus_size=declared_corpus_size or len(doc_map),
        max_error_rate=max_error_rate,
        max_p95_ms=max_p95_ms,
        min_hit_at_k=min_hit_at_k,
        min_mrr=min_mrr,
    )


async def run_load_eval_with_retriever(
    retrieve: Callable[[str, int], Awaitable[list[str]]],
    *,
    cases: list[tuple[str, str, set[str]]],
    k: int,
    request_count: int,
    concurrency: int,
    warmup_requests: int = 0,
    declared_corpus_size: int | None = None,
    max_error_rate: float = 0.01,
    max_p95_ms: float | None = None,
    min_hit_at_k: float | None = None,
    min_mrr: float | None = None,
) -> dict[str, Any]:
    """Measure one retrieval callable without coupling the runner to HTTP."""
    if not cases:
        raise ValueError("load eval requires at least one query with relevant entries")
    bounded_k = max(1, int(k))
    total_requests = max(1, int(request_count))
    worker_count = min(max(1, int(concurrency)), total_requests)
    warmup_count = max(0, int(warmup_requests))
    for index in range(warmup_count):
        _case_id, query, _expected = cases[index % len(cases)]
        try:
            await retrieve(query, bounded_k)
        except Exception:
            pass

    next_request = 0
    latencies_ms: list[float] = []
    relevant_ranks: list[int | None] = []
    error_count = 0
    error_samples: list[dict[str, Any]] = []

    async def worker() -> None:
        nonlocal next_request, error_count
        while True:
            request_index = next_request
            next_request += 1
            if request_index >= total_requests:
                return
            case_id, query, expected = cases[request_index % len(cases)]
            started = time.perf_counter()
            try:
                ranked = await retrieve(query, bounded_k)
                relevant_ranks.append(_first_expected_rank(ranked, expected))
            except Exception as exc:  # noqa: BLE001 - failures are measured output
                error_count += 1
                relevant_ranks.append(None)
                if len(error_samples) < 20:
                    error_samples.append({
                        "case_id": case_id,
                        "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                    })
            finally:
                latencies_ms.append((time.perf_counter() - started) * 1000)

    run_started = time.perf_counter()
    await asyncio.gather(*(worker() for _ in range(worker_count)))
    elapsed_seconds = max(time.perf_counter() - run_started, 1e-9)
    error_rate = error_count / total_requests
    hit_at_k = (
        sum(1 for rank in relevant_ranks if rank is not None and rank <= bounded_k)
        / total_requests
    )
    mrr = sum(1 / rank for rank in relevant_ranks if rank is not None) / total_requests
    latency = {
        "min": min(latencies_ms) if latencies_ms else 0.0,
        "p50": _percentile(latencies_ms, 50),
        "p95": _percentile(latencies_ms, 95),
        "p99": _percentile(latencies_ms, 99),
        "max": max(latencies_ms) if latencies_ms else 0.0,
        "mean": sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0.0,
    }
    violations: list[str] = []
    if error_rate > max_error_rate:
        violations.append(f"error_rate {error_rate:.6f} > {max_error_rate:.6f}")
    if max_p95_ms is not None and latency["p95"] > max_p95_ms:
        violations.append(f"p95_ms {latency['p95']:.3f} > {max_p95_ms:.3f}")
    if min_hit_at_k is not None and hit_at_k < min_hit_at_k:
        violations.append(f"hit_at_{bounded_k} {hit_at_k:.6f} < {min_hit_at_k:.6f}")
    if min_mrr is not None and mrr < min_mrr:
        violations.append(f"mrr {mrr:.6f} < {min_mrr:.6f}")
    return {
        "ok": not violations,
        "declared_corpus_size": declared_corpus_size,
        "request_count": total_requests,
        "concurrency": worker_count,
        "warmup_requests": warmup_count,
        "elapsed_seconds": elapsed_seconds,
        "requests_per_second": total_requests / elapsed_seconds,
        "success_count": total_requests - error_count,
        "error_count": error_count,
        "error_rate": error_rate,
        "latency_ms": latency,
        "k": bounded_k,
        "hit_at_k": hit_at_k,
        "mrr": mrr,
        "thresholds": {
            "max_error_rate": max_error_rate,
            "max_p95_ms": max_p95_ms,
            "min_hit_at_k": min_hit_at_k,
            "min_mrr": min_mrr,
        },
        "violations": violations,
        "error_samples": error_samples,
    }


def _first_expected_rank(ranked: list[str], expected: set[str]) -> int | None:
    return next((index for index, entry_id in enumerate(ranked, start=1) if entry_id in expected), None)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * min(max(percentile, 0.0), 100.0) / 100.0
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def default_ablation_configs() -> list[EvalAblationConfig]:
    return [
        EvalAblationConfig(
            name="metadata_only",
            retriever="search_metadata",
        ),
        EvalAblationConfig(
            name="metadata_plus_relations",
            retriever="search_metadata",
            relation_expansion=True,
        ),
        EvalAblationConfig(
            name="hybrid_no_rerank",
            retriever="recall_knowledge",
            semantic_recall=True,
        ),
        EvalAblationConfig(
            name="hybrid_plus_relations",
            retriever="recall_knowledge",
            semantic_recall=True,
            relation_expansion=True,
        ),
        EvalAblationConfig(
            name="hybrid_plus_rerank",
            retriever="recall_knowledge",
            semantic_recall=True,
            rerank=True,
        ),
        EvalAblationConfig(
            name="full_recall",
            retriever="recall_knowledge",
            semantic_recall=True,
            rerank=True,
            relation_expansion=True,
        ),
    ]


async def run_eval_ablation_dataset(
    *,
    name: str,
    k_values: Iterable[int] = (10, 50, 100),
    query_limit: int | None = None,
    configs: Iterable[EvalAblationConfig] | None = None,
) -> EvalAblationRunResult:
    ks = sorted({int(k) for k in k_values if int(k) > 0}) or [10]
    run_configs = list(configs or default_ablation_configs())
    runs: list[dict[str, Any]] = []
    baseline: EvalRunResult | None = None
    for config in run_configs:
        result = await run_eval_dataset(
            name=name,
            retriever=config.retriever,
            k_values=ks,
            query_limit=query_limit,
            semantic_recall=config.semantic_recall,
            rerank=config.rerank,
            relation_expansion=config.relation_expansion,
        )
        if baseline is None:
            baseline = result
        runs.append({
            "config": _ablation_config_to_dict(config),
            "delta_vs_baseline": _ablation_delta(result, baseline, max(ks)),
            "result": result_to_dict(result),
        })
    return EvalAblationRunResult(
        name=name,
        k_values=ks,
        query_limit=query_limit,
        runs=runs,
    )


def _ablation_config_to_dict(config: EvalAblationConfig) -> dict[str, Any]:
    return {
        "name": config.name,
        "retriever": config.retriever,
        "plan_phase": config.plan_phase,
        "semantic_recall": config.semantic_recall,
        "rerank": config.rerank,
        "relation_expansion": config.relation_expansion,
    }


def _ablation_delta(
    result: EvalRunResult,
    baseline: EvalRunResult,
    max_k: int,
) -> dict[str, float]:
    return {
        "mrr": result.mrr - baseline.mrr,
        f"hit@{max_k}": result.hit_rate.get(max_k, 0.0)
        - baseline.hit_rate.get(max_k, 0.0),
        f"candidate_recall@{max_k}": result.recall.get(max_k, 0.0)
        - baseline.recall.get(max_k, 0.0),
        f"ndcg@{max_k}": result.ndcg.get(max_k, 0.0)
        - baseline.ndcg.get(max_k, 0.0),
    }


async def _retrieve_entries(
    session: AsyncSession,
    *,
    retriever: str,
    query: str,
    limit: int,
    relation_expansion: bool | None = None,
) -> list[str]:
    ctx = ToolContext(session_id="eval", conversation_id="eval")
    if retriever == "search_metadata":
        result = await search_metadata(
            session,
            ctx,
            {"text": query, "limit": limit},
        )
        ranked = [str(e["entry_id"]) for e in result.get("entries") or []]
        return await _maybe_expand_ranked_ids(
            session,
            ranked,
            limit=limit,
            enabled=bool(relation_expansion),
        )
    if retriever == "semantic_recall":
        try:
            rows = await semantic_entry_rows(session, query, limit=limit)
        except RuntimeError as exc:
            # SEARCH-4: recall_knowledge records these as degraded. The eval
            # semantic_recall retriever has no degraded channel; treat a missing
            # or incompatible index as an empty ranking instead of aborting.
            if str(exc) not in {"index_missing", "index_incompatible"}:
                raise
            rows = []
        ranked = [str(e["entry_id"]) for e in rows]
        return await _maybe_expand_ranked_ids(
            session,
            ranked,
            limit=limit,
            enabled=bool(relation_expansion),
        )
    if retriever == "recall_knowledge":
        result = await recall_knowledge(
            session,
            ctx,
            {"text": query, "limit": limit},
        )
        return [str(eid) for eid in result.get("verify_entry_ids") or []]
    raise ValueError(
        "unknown retriever "
        f"{retriever!r}; expected search_metadata, semantic_recall, or recall_knowledge"
    )


async def _retrieve_entries_many(
    session: AsyncSession,
    *,
    retriever: str,
    queries: list[str],
    limit: int,
    semantic_recall: bool | None = None,
    rerank: bool | None = None,
    relation_expansion: bool | None = None,
) -> list[list[str]]:
    details = await _retrieve_entries_many_detail(
        session,
        retriever=retriever,
        queries=queries,
        limit=limit,
        evidence_limit=None,
        semantic_recall=semantic_recall,
        rerank=rerank,
        relation_expansion=relation_expansion,
    )
    return [detail["ranked_ids"] for detail in details]


async def _retrieve_entries_many_detail(
    session: AsyncSession,
    *,
    retriever: str,
    queries: list[str],
    limit: int,
    evidence_limit: int | None,
    semantic_recall: bool | None = None,
    rerank: bool | None = None,
    relation_expansion: bool | None = None,
) -> list[dict[str, list[str]]]:
    if not queries:
        return []
    if retriever == "recall_knowledge":
        return await _retrieve_recall_knowledge_many(
            session,
            queries=queries,
            limit=limit,
            evidence_limit=evidence_limit,
            semantic_recall=semantic_recall,
            rerank=rerank,
            relation_expansion=relation_expansion,
        )
    ranked_many = [
        await _retrieve_entries(
            session,
            retriever=retriever,
            query=query,
            limit=limit,
            relation_expansion=relation_expansion,
        )
        for query in queries
    ]
    return [
        {
            "ranked_ids": ranked,
            "evidence_ids": ranked[:evidence_limit] if evidence_limit else ranked,
        }
        for ranked in ranked_many
    ]


async def _retrieve_recall_knowledge_many(
    session: AsyncSession,
    *,
    queries: list[str],
    limit: int,
    evidence_limit: int | None,
    semantic_recall: bool | None = None,
    rerank: bool | None = None,
    relation_expansion: bool | None = None,
) -> list[dict[str, list[str]]]:
    fetch_limit = 100
    settings = get_settings()
    use_semantic = (
        semantic_recall_configured()
        if semantic_recall is None
        else bool(semantic_recall) and semantic_recall_configured()
    )
    use_rerank = (
        rerank_configured(settings)
        if rerank is None
        else bool(rerank) and rerank_configured(settings)
    )
    text_terms_by_query = [normalize_text_queries(query) for query in queries]
    semantic_queries = [" ".join(terms) for terms in text_terms_by_query]
    semantic_hits_many = (
        await search_semantic_index_many(
            semantic_queries,
            limit=min(fetch_limit, settings.semantic_recall_limit),
        )
        if use_semantic
        else [[] for _query in queries]
    )
    semantic_ids = sorted({
        hit.entry_id
        for hits in semantic_hits_many
        for hit in hits
    })
    semantic_rows_by_id = await _entry_rows_by_id(session, semantic_ids)
    metadata_results = await _search_metadata_many(
        text_terms_by_query,
        limit=fetch_limit,
        concurrency=20,
    )

    ranked_by_query: list[list[dict[str, Any]]] = []
    queries_for_rerank: list[str] = []
    rerank_entry_ids: list[str] = []
    rerank_top_n = max(1, int(settings.rerank_top_n or 80))
    for text_terms, metadata_entries, semantic_hits in zip(
        text_terms_by_query,
        metadata_results,
        semantic_hits_many,
    ):
        entry_map: dict[str, dict[str, Any]] = {}
        _merge_eval_entries(entry_map, metadata_entries, "metadata_text")
        semantic_entries = [
            {
                **semantic_rows_by_id[hit.entry_id],
                "matched_section_id": hit.section_id,
            }
            for hit in semantic_hits
            if hit.entry_id in semantic_rows_by_id
        ]
        _merge_eval_entries(entry_map, semantic_entries, "semantic")
        ranked = score_recall_entries(list(entry_map.values()), text_terms=text_terms)
        ranked_by_query.append(ranked)
        queries_for_rerank.append(" ".join(text_terms))
        if text_terms and use_rerank:
            for row in ranked[:rerank_top_n]:
                entry_id = str(row.get("entry_id") or "")
                if entry_id:
                    rerank_entry_ids.append(entry_id)

    if rerank_entry_ids and use_rerank:
        documents_by_query: list[dict[str, str]] = []
        for ranked in ranked_by_query:
            top = ranked[:rerank_top_n]
            documents_by_query.append(await load_rerank_documents_by_entry_id(
                session,
                [str(row.get("entry_id") or "") for row in top],
                matched_section_ids={
                    str(row["entry_id"]): str(row["matched_section_id"])
                    for row in top
                    if row.get("entry_id") and row.get("matched_section_id")
                },
            ))
        semaphore = asyncio.Semaphore(max(1, int(settings.rerank_concurrency or 10)))

        async def _rerank_one(
            query: str,
            ranked: list[dict[str, Any]],
            documents_by_id: dict[str, str],
        ) -> list[dict[str, Any]]:
            if not query.strip() or not ranked:
                return ranked
            async with semaphore:
                reranked, _trace = await rerank_recall_entries_with_documents(
                    ranked,
                    query=query,
                    documents_by_id=documents_by_id,
                )
                return reranked

        ranked_by_query = await asyncio.gather(*(
            _rerank_one(query, ranked, documents_by_id)
            for query, ranked, documents_by_id in zip(
                queries_for_rerank,
                ranked_by_query,
                documents_by_query,
            )
        ))

    out: list[dict[str, list[str]]] = []
    for ranked in ranked_by_query:
        ranked_ids = [
            str(entry.get("entry_id"))
            for entry in ranked[:max(1, limit)]
            if entry.get("entry_id")
        ]
        ranked_ids = await _maybe_expand_ranked_ids(
            session,
            ranked_ids,
            limit=limit,
            enabled=bool(relation_expansion),
        )
        evidence_ids = (
            _expand_evidence_ids(
                ranked_ids=ranked_ids,
                evidence_ids=select_evidence_entry_ids(
                    ranked[:max(1, limit)],
                    max(1, evidence_limit),
                ),
                limit=max(1, evidence_limit),
            )
            if evidence_limit
            else ranked_ids
        )
        out.append({"ranked_ids": ranked_ids, "evidence_ids": evidence_ids})
    return out


async def _maybe_expand_ranked_ids(
    session: AsyncSession,
    ranked_ids: list[str],
    *,
    limit: int,
    enabled: bool,
) -> list[str]:
    if not enabled or not ranked_ids:
        return ranked_ids[:max(1, limit)]
    out: list[str] = []
    seen: set[str] = set()
    for entry_id in ranked_ids:
        if entry_id and entry_id not in seen:
            seen.add(entry_id)
            out.append(entry_id)
        if len(out) >= limit:
            return out

    per_anchor_limit = max(1, min(10, limit))
    for anchor_id in ranked_ids[:max(1, limit)]:
        rel_rows = await relations_repo.list_top_for_entry(
            session,
            anchor_id,
            limit=per_anchor_limit,
            vetted_only=True,
        )
        for relation in rel_rows:
            other_id = (
                relation.entry_b_id
                if relation.entry_a_id == anchor_id
                else relation.entry_a_id
            )
            if not other_id or other_id in seen:
                continue
            seen.add(other_id)
            out.append(other_id)
            if len(out) >= limit:
                return out
    return out[:max(1, limit)]


def _expand_evidence_ids(
    *,
    ranked_ids: list[str],
    evidence_ids: list[str],
    limit: int,
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for entry_id in evidence_ids + ranked_ids:
        if not entry_id or entry_id in seen:
            continue
        seen.add(entry_id)
        out.append(entry_id)
        if len(out) >= limit:
            return out
    return out


async def _search_metadata_many(
    text_terms_by_query: list[list[str]],
    *,
    limit: int,
    concurrency: int,
) -> list[list[Any]]:
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def _one(text_terms: list[str]) -> list[Any]:
        if not text_terms:
            return []
        async with semaphore:
            async with session_scope() as session:
                result = await search_metadata(
                    session,
                    ToolContext(session_id="eval", conversation_id="eval"),
                    {"text": text_terms, "limit": limit},
                )
                return list(result.get("entries") or [])

    return await asyncio.gather(*(_one(text_terms) for text_terms in text_terms_by_query))


async def _entry_rows_by_id(
    session: AsyncSession,
    entry_ids: list[str],
) -> dict[str, dict[str, Any]]:
    rows = await entries_repo.list_live_with_file_by_ids(session, entry_ids)
    out: dict[str, dict[str, Any]] = {}
    for entry, file_row in rows:
        out[entry.id] = {
            "entry_id": entry.id,
            "display_name": entry.display_name,
            "lifecycle": entry.lifecycle,
            "kind": file_row.kind,
            "summary": file_row.summary,
            "catalog_id": entry.catalog_id,
            "folder_id": entry.folder_id,
        }
    return out


def _merge_eval_entries(
    entry_map: dict[str, dict[str, Any]],
    entries: list[Any],
    source: str,
) -> None:
    total = len(entries)
    for idx, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            continue
        entry_id = str(entry.get("entry_id") or "")
        if not entry_id:
            continue
        existing = entry_map.get(entry_id)
        if existing is None:
            existing = {
                "entry_id": entry_id,
                "display_name": entry.get("display_name"),
                "lifecycle": entry.get("lifecycle"),
                "kind": entry.get("kind"),
                "summary": entry.get("summary"),
                "catalog_id": entry.get("catalog_id"),
                "folder_id": entry.get("folder_id"),
                "coverage": entry.get("coverage"),
                "matched_section_id": entry.get("matched_section_id"),
                "matched_by": [],
                "rrf_score": 0.0,
                "rank_score": 0,
                "score": 0.0,
                "score_components": {},
            }
            entry_map[entry_id] = existing
        else:
            for key in (
                "display_name",
                "lifecycle",
                "kind",
                "summary",
                "catalog_id",
                "folder_id",
                "coverage",
                "matched_section_id",
            ):
                if existing.get(key) in (None, "") and entry.get(key) not in (None, ""):
                    existing[key] = entry.get(key)
        _append_unique_str(existing["matched_by"], source)
        rank_key = _rank_key_for_source(source)
        if rank_key:
            rank = idx + 1
            existing[rank_key] = min(
                int(existing.get(rank_key) or rank),
                rank,
            )
        existing["rank_score"] = max(
            int(existing.get("rank_score") or 0),
            total - idx,
        )
        existing["rrf_score"] = _eval_rrf_score(existing)


def _rank_key_for_source(source: str) -> str | None:
    if source in {"metadata_text", "metadata_tags"}:
        return "lexical_rank"
    if source == "semantic":
        return "semantic_rank"
    return None


def _eval_rrf_score(row: Mapping[str, Any], *, k: int = 60) -> float:
    score = 0.0
    for key in ("lexical_rank", "semantic_rank"):
        raw = row.get(key)
        if raw is None:
            continue
        try:
            rank = int(raw)
        except (TypeError, ValueError):
            continue
        if rank > 0:
            score += 1.0 / (k + rank)
    return score


def _eval_entry_sort_key(row: Mapping[str, Any]) -> tuple[float, int, int, str]:
    matched_by = set(row.get("matched_by") or [])
    return (
        -float(row.get("rrf_score") or 0.0),
        -int("metadata_text" in matched_by and "semantic" in matched_by),
        -int(row.get("rank_score") or 0),
        str(row.get("display_name") or ""),
    )


def _select_quota_evidence_ids(
    ranked: list[Mapping[str, Any]],
    evidence_limit: int,
) -> list[str]:
    if evidence_limit <= 0:
        return []
    overlap_quota, lexical_quota, semantic_quota = _evidence_quotas(evidence_limit)
    overlap: list[Mapping[str, Any]] = []
    lexical_only: list[Mapping[str, Any]] = []
    semantic_only: list[Mapping[str, Any]] = []
    for row in ranked:
        matched_by = set(row.get("matched_by") or [])
        has_lexical = "metadata_text" in matched_by or "metadata_tags" in matched_by
        has_semantic = "semantic" in matched_by
        if has_lexical and has_semantic:
            overlap.append(row)
        elif has_lexical:
            lexical_only.append(row)
        elif has_semantic:
            semantic_only.append(row)

    out: list[str] = []
    seen: set[str] = set()

    def take(rows: list[Mapping[str, Any]], quota: int) -> None:
        for row in rows:
            if len(out) >= evidence_limit or quota <= 0:
                return
            entry_id = str(row.get("entry_id") or "")
            if not entry_id or entry_id in seen:
                continue
            seen.add(entry_id)
            out.append(entry_id)
            quota -= 1

    take(overlap, overlap_quota)
    take(lexical_only, lexical_quota)
    take(semantic_only, semantic_quota)
    take(ranked, evidence_limit - len(out))
    return out[:evidence_limit]


def _evidence_quotas(evidence_limit: int) -> tuple[int, int, int]:
    if evidence_limit <= 1:
        return evidence_limit, 0, 0
    overlap = max(1, round(evidence_limit * 0.4))
    lexical = max(1, round(evidence_limit * 0.4))
    semantic = max(0, evidence_limit - overlap - lexical)
    return overlap, lexical, semantic
