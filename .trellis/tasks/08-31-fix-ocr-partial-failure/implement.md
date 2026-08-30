# 执行计划 — OCR 部分失败可见化

## 前置复核
- [ ] `grep -rn "_ocr_pdf_pages" src tests` 确认调用方只有 `pdf.py:262`
- [ ] 确认前端对未知 `partial_reasons` 值有兜底渲染
      （`grep -rn "partial_reasons" frontend/src`）——若无，本任务范围内补一个 fallback

## Step 1 — `_ocr_pdf_pages` 返回 `list[str | None]`
- [ ] `out: list[str | None] = [None] * pages_to_ocr`
- [ ] 成功路径显式写入（含 `""`）
- [ ] 尾部 padding 改为 append `""`（超出 cap 的页是"未处理"而非"失败"，语义要分清）
- 验证：`uv run pytest tests/ -k pdf`（此时应有测试因类型/断言失败 → 预期）

## Step 2 — `_ocr_one` 加退避重试
- [ ] 新增模块常量 `OCR_PAGE_RETRIES = 2`
- [ ] 按 design.md 决策 2 实现：sem 外 sleep、`CancelledError` 原样上抛
- [ ] 日志区分"单次失败重试中"与"重试耗尽最终失败"

## Step 3 — 调用方归一化 + 填 partial_reasons
- [ ] `pdf.py:262` 后计算 `failed_pages`，归一 `None → ""`
- [ ] `:275` 后追加 `ocr_page_failures` reason
- [ ] 全部失败时仍走 `PdfNeedsOcrError`（`ocr_pages_done == 0` 判据不变）

## Step 4 — `_coverage` 接入
- [ ] 加 `ocr_failed_pages` 参数，`indexed_partial` 补 `or ocr_failed_pages > 0`
- [ ] `ocr_used` 分支输出 `ocr_failed_pages`
- [ ] 更新两处调用点（`:305`、`:318`）

## Step 5 — 测试
- [ ] `test_ocr_partial_failure_marks_coverage`：部分页抛异常
- [ ] `test_ocr_retries_transient_failure`：前 N 次失败后成功
- [ ] `test_ocr_all_pages_fail_raises_needs_ocr`
- [ ] `test_ocr_all_success_coverage_unchanged`（防回归，对比修复前的期望字典）
- 验证：新测试先红后绿

## Step 6 — 全量校验
- [ ] `uv run ruff check src tests`
- [ ] `uv run pytest tests/ -k pdf`
- [ ] `git diff --stat` 只动 `pipelines/pdf.py` + 测试文件

## 回滚点

Step 1-2 可独立于 3-4 落地（重试单独就有价值）。
若 Step 4 的 coverage 字段引发前端问题，可只 revert Step 4 保留重试与日志改进。
