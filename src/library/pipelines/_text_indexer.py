"""Shared indexing helper for pipelines that extract a text-shaped view.

Short views use one model call. Longer views are split into stable line
ranges: chunk calls build the section map, then one aggregate call produces
only file-level summary, tags, and retrieval metadata. Any model failure
degrades to deterministic sections so ingest never loses the extracted file.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from library.agent.compression_adapter import (
    maybe_compress_ingest_aggregate_view,
    maybe_compress_ingest_view,
)
from library.config import get_settings
from library.llm import ChatRequest, cacheable_prompt_messages, get_chat_client
from library.llm.tagged_response import render_format_hint, render_sections_hint
from library.pipelines._long_index import (
    IndexFields,
    build_retrieval_extra,
    fallback_section,
    ingest_output_tokens,
    llm_ingest_concurrency,
    normalize_sections,
    parse_index_response,
    plain_summary,
    render_sections_digest,
    renumber_sections,
)
from library.pipelines.base import PipelineContext, PipelineResult, TagSuggestion
from library.tasks.usage import measure_stage

log = logging.getLogger(__name__)

SINGLE_INDEX_CHARS = 12_000
TEXT_CHUNK_CHARS = 50_000
TEXT_SECTION_DIGEST_CHARS = 60_000
INDEX_ADAPTIVE_MIN_OUTPUT_TOKENS = 1_024
INDEX_MAX_OUTPUT_TOKENS = 16_384

INDEXER_SYSTEM = """You are Library's document indexer.

Read the extracted view of one knowledge-base document and produce a
structured index that lets a downstream agent decide whether to retrieve it
and jump to a relevant section by a stable anchor. The view may be partial or
sampled. Use only supplied content and coverage metadata; never infer omitted
content.

`summary` is one or two sentences (<=60 Chinese characters / <=30 English
words) in the document's language. `description` explains its organisation.
`sections` covers meaningful headings or logical chunks with stable anchors.
`extra` and `entry_extra` contain useful `key: value` lines.
`entry_catalog_path` is a best-guess classification path. `tags` contains
3-10 facet/name pairs using topic, form, time, source, language, or extra.
Reuse the supplied vocabulary when suitable.

""" + render_format_hint() + "\n" + render_sections_hint(
    anchor_unit="heading, lines, pages, rows, members, blocks, slides, or text",
    anchor_example="lines 100-160",
)

CHUNK_SYSTEM = """You are Library's document section indexer.

You receive one line range from a larger extracted document. Index only this
range. `summary` and `sections` are required and should cover every meaningful
heading or logical chunk. Use line-range anchors from the supplied context,
not byte offsets, and do not invent content outside the range.

""" + render_format_hint() + "\n" + render_sections_hint(
    anchor_unit="lines",
    anchor_example="lines 1200-1450",
)

AGGREGATE_SYSTEM = """You are Library's aggregate document indexer.

You receive a precomputed section map for the indexed part of a document.
Produce only file-level summary, description, extra, entry_extra,
entry_catalog_path, and tags. Do not output sections; the caller preserves the
supplied map. If indexed coverage is partial, say so and do not imply omitted
content was reviewed. Make `extra` retrieval-friendly with important alternate
names, technical terms, and useful anchors from the map.

""" + render_format_hint()


# Kept for legacy callers that import it; tagged responses are used at runtime.
def make_schema(kind: str) -> dict[str, Any]:
    del kind
    return {}


async def index_extracted_text(
    body: str,
    ctx: PipelineContext,
    kind: str,
    *,
    coverage: dict[str, Any] | None = None,
    fallback_sections: list[dict[str, Any]] | None = None,
    pipeline: str | None = None,
    warnings: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> PipelineResult:
    """Index extracted text with bounded model calls and safe degradation."""
    coverage = dict(coverage or {})
    metadata = dict(metadata or {})
    pipeline_name = pipeline or kind
    anchor_unit = _anchor_unit(
        kind=kind,
        pipeline=pipeline_name,
        coverage=coverage,
    )
    fallback_sections = normalize_sections(
        fallback_sections or metadata.get("sections"),
        fallback=[],
        anchor_unit=anchor_unit,
    )

    if not body.strip():
        return PipelineResult(
            summary=f"No {kind} content extracted.",
            description={
                "sections": [],
                **({"coverage": coverage} if coverage else {}),
                "text": "No non-whitespace text content was extracted.",
                "source": "heuristic",
            },
            kind=kind,
            extra=None,
            entry_extra=None,
            entry_catalog_path=None,
            entry_tags=[],
        )

    try:
        with measure_stage("intelligence"):
            if len(body) > SINGLE_INDEX_CHARS:
                return await _run_chunked_index(
                    body=body,
                    ctx=ctx,
                    kind=kind,
                    coverage=coverage,
                    fallback_sections=fallback_sections,
                    pipeline=pipeline_name,
                    metadata=metadata,
                    anchor_unit=anchor_unit,
                )
            return await _run_single_index(
                body=body,
                ctx=ctx,
                kind=kind,
                coverage=coverage,
                fallback_sections=fallback_sections,
                pipeline=pipeline_name,
                metadata=metadata,
                anchor_unit=anchor_unit,
            )
    except Exception as exc:  # noqa: BLE001 - ingest must fail soft
        warning_text = "; ".join(str(item) for item in (warnings or []) if item)
        suffix = f" ({warning_text})" if warning_text else ""
        log.warning(
            "%s pipeline indexer failed for file %s%s: %s",
            kind,
            ctx.file_id,
            suffix,
            exc,
        )
        return _heuristic_result(
            body=body,
            ctx=ctx,
            kind=kind,
            coverage=coverage,
            fallback_sections=fallback_sections,
            anchor_unit=anchor_unit,
        )


async def _run_single_index(
    *,
    body: str,
    ctx: PipelineContext,
    kind: str,
    coverage: dict[str, Any],
    fallback_sections: list[dict[str, Any]],
    pipeline: str,
    metadata: dict[str, Any],
    anchor_unit: str,
) -> PipelineResult:
    settings = get_settings()
    body_for_index, compression_meta = maybe_compress_ingest_view(
        body,
        kind=kind,
        context=ctx.display_name or "",
    )
    if compression_meta is not None:
        coverage = {**coverage, "compression": compression_meta}
    payload = _base_payload(ctx, coverage=coverage, metadata=metadata)
    payload.update({
        "kind": kind,
        "pipeline": pipeline,
        "anchor_unit": anchor_unit,
        "fallback_sections": fallback_sections,
    })
    stable_prefix = (
        f"Index the extracted {kind} view below. Hints are advisory; supplied "
        "content takes precedence. If coverage.indexed_partial is true, "
        "describe only indexed content.\n\n"
        + render_format_hint()
        + "\n"
        + render_sections_hint(
            anchor_unit=anchor_unit,
            anchor_example=_anchor_example(anchor_unit),
        )
    )
    file_content = (
        f"<context>\n{_json_dumps(payload)}\n</context>\n\n"
        f"<document>\n{body_for_index}\n</document>"
    )
    response = await get_chat_client("ingest").complete(ChatRequest(
        system=INDEXER_SYSTEM,
        messages=cacheable_prompt_messages(stable_prefix, file_content),
        max_tokens=_index_output_tokens(
            len(body_for_index),
            configured=settings.llm_ingest_max_tokens,
        ),
        temperature=0.2,
        cache_breakpoints=[0],
    ))
    fields = parse_index_response(
        response,
        anchor_unit=anchor_unit,
        fallback_sections=fallback_sections,
    )
    if not fields.summary:
        raise ValueError(f"{kind} pipeline produced empty summary")
    sections = fields.sections or _fallback_sections(
        body=body,
        summary=fields.summary,
        fallback_sections=fallback_sections,
        anchor_unit=anchor_unit,
    )
    return _result_from_fields(
        fields=fields,
        sections=renumber_sections(sections),
        coverage={**coverage, "chunked": False, "chunk_count": 1},
        source="llm",
        kind=kind,
    )


async def _run_chunked_index(
    *,
    body: str,
    ctx: PipelineContext,
    kind: str,
    coverage: dict[str, Any],
    fallback_sections: list[dict[str, Any]],
    pipeline: str,
    metadata: dict[str, Any],
    anchor_unit: str,
) -> PipelineResult:
    chunks = list(enumerate(
        _iter_line_chunks(body, max_chars=TEXT_CHUNK_CHARS),
        start=1,
    ))
    sem = asyncio.Semaphore(llm_ingest_concurrency())
    settings = get_settings()
    client = get_chat_client("ingest")

    async def _index_chunk(
        chunk_no: int,
        line_start: int,
        line_end: int,
        text: str,
    ) -> dict[str, Any]:
        async with sem:
            payload = _base_payload(ctx, coverage=coverage, metadata=metadata)
            payload.update({
                "kind": kind,
                "pipeline": pipeline,
                "chunk_no": chunk_no,
                "line_start": line_start,
                "line_end": line_end,
                "anchor_unit": "lines",
            })
            try:
                stable_prefix = (
                    "Index this line range from a larger document. Use stable "
                    "line-range anchors.\n\n"
                    + render_format_hint()
                    + "\n"
                    + render_sections_hint(
                        anchor_unit="lines",
                        anchor_example=f"lines {line_start}-{line_end}",
                    )
                )
                file_content = (
                    f"<context>\n{_json_dumps(payload)}\n</context>\n\n"
                    f"<document>\n{text}\n</document>"
                )
                response = await client.complete(ChatRequest(
                    system=CHUNK_SYSTEM,
                    messages=cacheable_prompt_messages(stable_prefix, file_content),
                    max_tokens=_index_output_tokens(
                        len(text),
                        configured=settings.llm_ingest_max_tokens,
                    ),
                    temperature=0.2,
                    cache_breakpoints=[0],
                ))
                fields = parse_index_response(response, anchor_unit="lines")
            except Exception as exc:  # noqa: BLE001 - one chunk may degrade
                log.warning(
                    "%s chunk index failed for file %s lines %s-%s: %s",
                    kind,
                    ctx.file_id,
                    line_start,
                    line_end,
                    exc,
                )
                fields = IndexFields(
                    summary="",
                    description_text=None,
                    sections=[],
                    extra=None,
                    entry_extra=None,
                    catalog_path=None,
                    tags=[],
                )
        summary = (
            fields.summary
            or fields.description_text
            or plain_summary(text)
            or f"Lines {line_start}-{line_end}"
        )
        sections = fields.sections or [fallback_section(
            title=f"Lines {line_start}-{line_end}",
            anchor_unit="lines",
            anchor_value=f"{line_start}-{line_end}",
            summary=summary,
        )]
        return {
            "sections": sections,
            "summary": {
                "line_start": line_start,
                "line_end": line_end,
                "summary": summary,
                "description": fields.description_text or "",
            },
        }

    chunk_results = await asyncio.gather(*(
        _index_chunk(chunk_no, line_start, line_end, text)
        for chunk_no, (line_start, line_end, text) in chunks
    ))
    sections: list[dict[str, Any]] = []
    chunk_summaries: list[dict[str, Any]] = []
    for result in chunk_results:
        sections.extend(result["sections"])
        chunk_summaries.append(result["summary"])
    sections = renumber_sections(sections or fallback_sections)
    chunked_coverage = {
        **coverage,
        "chunked": len(chunks) > 1,
        "chunk_count": len(chunks),
    }

    payload = _base_payload(ctx, coverage=chunked_coverage, metadata=metadata)
    payload.update({
        "kind": kind,
        "pipeline": pipeline,
        "anchor_unit": anchor_unit,
        "chunk_summaries": chunk_summaries,
    })
    try:
        stable_prefix = (
            "Summarize indexed coverage from this section map. The caller "
            "already has sections; produce file-level recall fields only. "
            "Do not output a sections block.\n\n"
            + render_format_hint()
        )
        aggregate_content = (
            f"<context>\n{_json_dumps(payload)}\n</context>\n\n"
            "<section_map>\n"
            f"{render_sections_digest(sections, max_chars=TEXT_SECTION_DIGEST_CHARS)}\n"
            "</section_map>"
        )
        aggregate_content, aggregate_meta = maybe_compress_ingest_aggregate_view(
            aggregate_content,
            kind=f"{kind}_aggregate",
            context=ctx.display_name or "",
        )
        if aggregate_meta is not None:
            chunked_coverage["aggregate_compression"] = aggregate_meta
        response = await client.complete(ChatRequest(
            system=AGGREGATE_SYSTEM,
            messages=cacheable_prompt_messages(stable_prefix, aggregate_content),
            max_tokens=_index_output_tokens(
                len(aggregate_content),
                configured=settings.llm_ingest_max_tokens,
            ),
            temperature=0.2,
            cache_breakpoints=[0],
        ))
        fields = parse_index_response(
            response,
            anchor_unit=anchor_unit,
            fallback_sections=sections,
        )
    except Exception as exc:  # noqa: BLE001 - preserve the completed map
        log.warning(
            "%s aggregate index failed for file %s: %s",
            kind,
            ctx.file_id,
            exc,
        )
        first = chunk_summaries[0]["summary"] if chunk_summaries else kind
        fields = IndexFields(
            summary=(
                f"Long {kind} indexed into {len(chunks)} ranges. "
                f"First range: {first}"
            ),
            description_text=None,
            sections=sections,
            extra=None,
            entry_extra=None,
            catalog_path=None,
            tags=_heuristic_tags(kind=kind, body=body, ctx=ctx),
        )
    if not fields.summary:
        first = chunk_summaries[0]["summary"] if chunk_summaries else kind
        fields.summary = (
            f"Long {kind} indexed into {len(chunks)} ranges. First range: {first}"
        )
    return _result_from_fields(
        fields=fields,
        sections=sections,
        coverage=chunked_coverage,
        source="llm",
        kind=kind,
    )


def _result_from_fields(
    *,
    fields: IndexFields,
    sections: list[dict[str, Any]],
    coverage: dict[str, Any],
    source: str,
    kind: str,
) -> PipelineResult:
    description: dict[str, Any] = {
        "sections": sections,
        "coverage": coverage,
        "source": source,
        "text": fields.description_text or fields.summary,
    }
    return PipelineResult(
        summary=fields.summary,
        description=description,
        kind=kind,
        extra=build_retrieval_extra(
            sections=sections,
            coverage=coverage,
            base_extra=fields.extra,
        ),
        entry_extra=fields.entry_extra or _json_dumps({"summary": fields.summary}),
        entry_catalog_path=fields.catalog_path,
        entry_tags=fields.tags,
    )


def _heuristic_result(
    *,
    body: str,
    ctx: PipelineContext,
    kind: str,
    coverage: dict[str, Any],
    fallback_sections: list[dict[str, Any]],
    anchor_unit: str,
) -> PipelineResult:
    summary = plain_summary(body) or f"No {kind} content extracted."
    sections = renumber_sections(_fallback_sections(
        body=body,
        summary=summary,
        fallback_sections=fallback_sections,
        anchor_unit=anchor_unit,
    ))
    fields = IndexFields(
        summary=summary,
        description_text=summary,
        sections=sections,
        extra=None,
        entry_extra=_json_dumps({"summary": summary}),
        catalog_path=None,
        tags=_heuristic_tags(kind=kind, body=body, ctx=ctx),
    )
    chunk_count = (
        len(_iter_line_chunks(body, max_chars=TEXT_CHUNK_CHARS))
        if len(body) > SINGLE_INDEX_CHARS
        else 1
    )
    return _result_from_fields(
        fields=fields,
        sections=sections,
        coverage={
            **coverage,
            "chunked": chunk_count > 1,
            "chunk_count": chunk_count,
        },
        source="heuristic",
        kind=kind,
    )


def _fallback_sections(
    *,
    body: str,
    summary: str,
    fallback_sections: list[dict[str, Any]],
    anchor_unit: str,
) -> list[dict[str, Any]]:
    if fallback_sections:
        return fallback_sections
    lines = max(1, len(body.splitlines()))
    return [fallback_section(
        title="Document",
        anchor_unit="lines" if anchor_unit in {"lines", "text"} else anchor_unit,
        anchor_value=f"1-{lines}" if anchor_unit in {"lines", "text"} else "document",
        summary=summary,
    )]


def _base_payload(
    ctx: PipelineContext,
    *,
    coverage: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "context": {
            "file_id": ctx.file_id,
            "storage_key": ctx.storage_key,
            "sha256": ctx.sha256,
            "size_bytes": ctx.size_bytes,
            "mime_type": ctx.mime_type,
            "original_ext": ctx.original_ext,
            "display_name": ctx.display_name,
            "folder_path": ctx.folder_path,
            "sibling_names": ctx.sibling_names,
            "catalog_sketch": ctx.catalog_sketch,
            "tag_vocabulary": ctx.tag_vocabulary,
        },
        "coverage": coverage,
        "extraction_metadata": _prompt_metadata(metadata),
    }


def _prompt_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in metadata.items():
        if key == "members" and isinstance(value, list):
            out[key] = value[:60]
        elif key == "sections" and isinstance(value, list):
            out[key] = value[:80]
        elif key not in {"pages", "ocr_pages"}:
            out[key] = value
    return out


def _anchor_unit(
    *,
    kind: str,
    pipeline: str,
    coverage: dict[str, Any],
) -> str:
    unit = str(coverage.get("unit") or "").strip().lower()
    if unit in {"pages", "rows", "members", "blocks", "lines", "slides"}:
        return unit
    if pipeline in {"text", "markdown", "log"} or kind in {"text", "markdown", "log"}:
        return "lines"
    if pipeline == "pdf" or kind == "pdf":
        return "pages"
    return "text"


def _anchor_example(anchor_unit: str) -> str:
    if anchor_unit in {"pages", "slides"}:
        return "1-4"
    if anchor_unit == "rows":
        return "1-200"
    if anchor_unit == "members":
        return "path/to/member.txt"
    if anchor_unit == "blocks":
        return "1-12"
    if anchor_unit == "lines":
        return "100-160"
    return "stable heading or text anchor"


def _index_output_tokens(char_count: int, *, configured: int) -> int:
    return ingest_output_tokens(char_count, configured=configured)


def _iter_line_chunks(body: str, *, max_chars: int) -> list[tuple[int, int, str]]:
    lines = body.splitlines()
    if not lines:
        return [(1, 1, "")]
    chunks: list[tuple[int, int, str]] = []
    current: list[str] = []
    current_start = 1
    current_len = 0
    for index, line in enumerate(lines, start=1):
        line_cost = len(line) + 1
        if current and current_len + line_cost > max_chars:
            chunks.append((current_start, index - 1, "\n".join(current)))
            current = []
            current_start = index
            current_len = 0
        current.append(line)
        current_len += line_cost
    if current:
        chunks.append((
            current_start,
            current_start + len(current) - 1,
            "\n".join(current),
        ))
    return chunks


def _heuristic_tags(
    *,
    kind: str,
    body: str,
    ctx: PipelineContext,
) -> list[TagSuggestion]:
    source = " ".join(
        part
        for part in (
            ctx.display_name or "",
            ctx.mime_type or "",
            ctx.original_ext or "",
            kind,
            body[:4000],
        )
        if part
    ).lower()
    tags: list[TagSuggestion] = []
    for word in (
        "release",
        "rollback",
        "security",
        "support",
        "deploy",
        "incident",
    ):
        if word in source:
            tags.append(TagSuggestion(name=word, facet="topic"))
    if kind:
        tags.append(TagSuggestion(name=kind, facet="form"))
    return _dedupe_tags(tags)[:12] or [
        TagSuggestion(name="document", facet="form"),
    ]


def _dedupe_tags(tags: list[TagSuggestion]) -> list[TagSuggestion]:
    out: list[TagSuggestion] = []
    seen: set[tuple[str, str]] = set()
    for tag in tags:
        key = (tag.facet.casefold(), tag.name.casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append(tag)
    return out


def _json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
