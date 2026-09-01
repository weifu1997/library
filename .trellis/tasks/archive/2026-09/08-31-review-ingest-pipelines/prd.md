# 审查：入库与管线

父任务：`08-31-feature-code-review`

## Goal

审查所有入库管线（PDF / Office / 图片 / 表格 / 日志 / 压缩包 / 邮件 / 文本 / markitdown / git metadata / document vision）的正确性、安全、架构、契约与测试。只出 `report.md`，不改产品代码。

## Scope

- `src/library/pipelines/` 全部模块（含 `registry.py` `base.py` `_text_indexer.py` `_long_index.py`）
- `src/library/tasks/handlers/ingest_file.py`
- `src/library/services/ingest_status.py`
- 相关测试：`test_ingest*` `test_pdf*` `test_office*` `test_image*` `test_email*` `test_archive*` `test_markitdown*` `test_pipeline*` `test_supplemental*` `test_long_document*` `test_shared_text_indexer*` `test_document_vision*` `test_rar*` `test_container*` `test_git_repo*` `test_ingest_coverage*`

## Extra angles

- 部分失败 vs 成功状态是否可区分（coverage / partial_reasons）
- 资源：PDF 句柄、临时文件、解码内存上限
- 设置项运行时生效 vs import 时固化（复验 AM-1）

## Regression only

- AH-2 OCR 逐页失败被吞（`08-31-fix-ocr-partial-failure`）
- 前端 coverage 展示不在本任务（归 `review-frontend-pages`），本任务只确认后端 coverage 字段仍能表达部分失败

## Re-verify still-open

- AM-1 `OCR_MAX_PAGES` import 时求值
- AM-2 每批 OCR 重新解析整个 PDF

## Out of Scope

- 改代码；上传 HTTP 面（归 upload 子任务）；语义索引重建（归 search）

## Acceptance Criteria

- [ ] 五个角度均有结论
- [ ] 每种格式管线至少完成结构扫描；`pdf.py` 在 AH-2 之外的路径明确写清逐行/未逐行
- [ ] finding 含 `file:line` + 失败场景
- [ ] AH-2 / AM-1 / AM-2 有回归或复验结论
- [ ] 无产品代码改动
