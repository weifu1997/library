# 修复 apply_modified 再入库

父：`08-31-fix-review-highs` 来源：UPLOAD-1  
`.trellis/tasks/08-31-review-upload-scan-sync/report.md`

## Problem

`apply_modified` 更新 hash、清 summary、`ingest_status=pending`，**不清 `ingested_at`**，enqueue **无 dedup_key**。`ingest_file` 跑完但 `_persist` 因 `ingested_at is not None` 不写新 summary。

## Requirements

- 原地修改后的 ingest 必须能写新的 summary/description/kind/extra（与 `reprocess_file` 一致：清 `ingested_at`，用 `dedup_key=ingest_file:{file_id}`）。
- 优先复用 `reprocess_file`，不要第三套半重置。
- 不改变「未修改文件」的 sync 行为。

## Acceptance Criteria

- [x] 测试：ingest 成功后改 sha、`apply_modified`、再跑 ingest handler → 新 summary 落库且只有一条 ingest 任务
- [x] `test_scan_sync*` 仍绿

## Out of Scope

UPLOAD-2 文件夹名 sanitize。
