# 执行 — INGEST-H1

- [x] `pipelines/pdf.py` `_run_chunked_index` / `_index_chunk`
- [x] `pipelines/text.py` 对应分块
- [x] 对齐 `_text_indexer.py:315-332`
- [x] 测试
- [x] `uv run pytest tests/ -k "long_document or pdf or ingest or text_indexer" -q`
