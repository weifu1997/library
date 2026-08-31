# 执行 — 入库与管线

遵循父任务 `research/review-protocol.md`。只写本目录 `report.md`。

## Checklist

- [ ] `pipelines/registry.py` `base.py`
- [ ] `pipelines/pdf.py` `pdf_text.py`（AH-2 回归；AM-1/AM-2 复验；OCR/渲染/read_segment）
- [ ] `pipelines/docx.py` `pptx.py` `spreadsheet.py`
- [ ] `pipelines/image.py` `document_vision.py`
- [ ] `pipelines/text.py` `log.py` `_text_indexer.py` `_long_index.py`
- [ ] `pipelines/archive.py` `email.py` `markitdown.py` `git_metadata.py`
- [ ] `tasks/handlers/ingest_file.py` `services/ingest_status.py`
- [ ] 对应 tests：无断言、skip、部分失败未覆盖的路径
- [ ] 写 `report.md`

## Validation

```bash
git status --short
uv run pytest tests/ -k "ingest or pdf or office or pipeline or email or archive or markitdown" --collect-only
```

不要 `--fix`，不要改测试。
