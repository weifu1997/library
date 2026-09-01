# 分块索引单块失败降级

父：`08-31-fix-review-highs` 来源：INGEST-H1

## Problem

`_text_indexer._index_chunk` 捕获单块 LLM 失败并降级启发式章节。`PdfPipeline._run_chunked_index` 与 `TextPipeline` 的分块 `gather` 无 try、无 `return_exceptions`，一块 429 则整次 ingest `failed`。

## Requirements

- PDF 与 text 的 chunked index 单块失败时：该块启发式 section，文件仍可 `done`。
- `coverage.indexed_partial` + `partial_reasons` 含失败标记（如 `chunk_index_failures`）。
- 全部块失败：行为明确（仍可 heuristic 整篇或保持现有硬失败——PRD 选择：**与 office 一致，整篇 heuristic + partial**，不要 `pipeline_exception`）。
- 全部成功路径输出不变。

## Acceptance Criteria

- [x] 测试：mock 中间块抛错，文件 `done`、`indexed_partial`、有启发式 section
- [x] 测试：全成功 coverage 与修前一致
- [x] office `_text_indexer` 路径不回归

## Out of Scope

AM-1/AM-2、拆 pdf.py。
