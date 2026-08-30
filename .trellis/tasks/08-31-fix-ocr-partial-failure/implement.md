# 执行计划 — OCR 部分失败可见化

## 前置复核
- [x] `grep -rn "_ocr_pdf_pages" src tests` 确认调用方只有 `pdf.py:262`
- [x] 确认前端对未知 `partial_reasons` 值有兜底渲染
      （`grep -rn "partial_reasons" frontend/src`）——若无，本任务范围内补一个 fallback

## Step 1 — `_ocr_pdf_pages` 返回 `list[str | None]`
- [x] `out: list[str | None] = [None] * pages_to_ocr`
- [x] 成功路径显式写入（含 `""`）
- [x] 尾部 padding 改为 append `""`（超出 cap 的页是"未处理"而非"失败"，语义要分清）
- 验证：`uv run pytest tests/ -k pdf`（此时应有测试因类型/断言失败 → 预期）

## Step 2 — `_ocr_one` 加退避重试
- [x] 新增模块常量 `OCR_PAGE_RETRIES = 2`
- [x] 按 design.md 决策 2 实现：sem 外 sleep、`CancelledError` 原样上抛
- [x] 日志区分"单次失败重试中"与"重试耗尽最终失败"

## Step 3 — 调用方归一化 + 填 partial_reasons
- [x] `pdf.py:262` 后计算 `failed_pages`，归一 `None → ""`
- [x] `:275` 后追加 `ocr_page_failures` reason
- [x] 全部失败时仍走 `PdfNeedsOcrError`（`ocr_pages_done == 0` 判据不变）

## Step 4 — `_coverage` 接入
- [x] 加 `ocr_failed_pages` 参数，`indexed_partial` 补 `or ocr_failed_pages > 0`
- [x] `ocr_used` 分支输出 `ocr_failed_pages`
- [x] 更新两处调用点（`:305`、`:318`）

## Step 5 — 测试
- [x] `test_ocr_partial_failure_marks_coverage`：部分页抛异常
- [x] `test_ocr_retries_transient_failure`：前 N 次失败后成功
- [x] `test_ocr_all_pages_fail_raises_needs_ocr`
- [x] `test_ocr_all_success_coverage_unchanged`（防回归，对比修复前的期望字典）
- 验证：新测试先红后绿

## Step 6 — 全量校验
- [x] `uv run ruff check src tests`
- [x] `uv run pytest tests/ -k pdf`
- [x] `git diff --stat` 只动 `pipelines/pdf.py` + 测试文件

## 回滚点

Step 1-2 可独立于 3-4 落地（重试单独就有价值）。
若 Step 4 的 coverage 字段引发前端问题，可只 revert Step 4 保留重试与日志改进。


---

## 执行结果（2026-08-31）

| 检查 | 结果 |
|---|---|
| `uv run ruff check src tests scripts` | ✅ All checks passed |
| `uv run pytest tests/ -k "pdf or ocr"` | ✅ 37 passed, 1 skipped |
| `uv run pytest tests/` **全量** | ✅ **581 passed, 1 skipped**（修复前 575，新增 6） |

### 先红后绿已验证

还原"失败页填 ''、不重试、indexed_partial 不看失败页"后重跑，
6 个新测试中 **4 个行为测试转红**：

- `test_ocr_failed_page_is_none_not_blank`
- `test_ocr_retries_transient_failure`
- `test_ocr_gives_up_after_retry_budget`
- `test_coverage_marks_partial_on_ocr_failures`（`assert False is True`）

另 2 个是**防回归守卫**，两种状态下都应为绿，实测确实如此：
`test_ocr_pages_past_cap_are_blank_not_failed`（cap 语义不能被这次改动污染）、
`test_coverage_unchanged_when_all_ocr_pages_succeed`（干净路径输出形状不变）。

### 前置复核结论

1. **`_ocr_pdf_pages` 有第二个调用方**：`tests/test_pdf_ocr_uncapped_unit.py:102`。
   计划里只预期 `pdf.py:262` 一处。该测试断言全部页为 `"OCR text"`，
   在新语义下仍成立（成功页照常返回字符串），无需修改。
2. **前端 fallback 不需要做**：`grep -rn "partial_reasons|indexed_partial|coverage" frontend/src`
   → 0 命中。前端根本不消费 coverage，补 fallback 等于给不存在的 UI 写死代码。
   已另开 `08-31-frontend-coverage-surface` 承接"让用户看得见"这半个问题。

### 与计划的偏差

1. **`ocr_failed_pages` 在 `_coverage` 上保持必填，不给默认值 0。**
   默认值会让未来的调用方静默漏传失败数——正是本次要修的那类 bug。
   代价是改了 2 个既有测试的调用点。
2. 机械插入参数时误把 `ocr_failed_pages=` 传给了 `_result_from_fields`
   （它不接这个参数），被测试捕获后移除。`_result_from_fields` 只负责 OCR extras，
   不需要失败计数。
3. 新增 `_ocr_retry_backoff` 辅助函数（design.md 只写了退避公式，未单列函数）。
