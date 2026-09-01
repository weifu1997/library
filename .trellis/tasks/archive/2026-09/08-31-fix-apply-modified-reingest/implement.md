# 执行 — UPLOAD-1

- [x] `services/sync.py` `apply_modified` 走 `reprocess_file` 或等价清 `ingested_at` + dedup_key
- [x] 新测试紧挨 scan/sync e2e
- [x] `uv run pytest tests/ -k "sync or scan or reprocess or ingest_file" -q`
