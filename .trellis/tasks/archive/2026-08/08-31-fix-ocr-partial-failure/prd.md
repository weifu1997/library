# 修复 PDF OCR 逐页失败被静默吞掉

父任务：`08-31-full-code-review`
来源：`.trellis/tasks/08-31-audit-agent-runtime/report.md` **AH-2**

## Problem

`pipelines/pdf.py:1795-1798`：

```python
except Exception as exc:  # noqa: BLE001
    log.warning("OCR call failed for page %d: %s", i + 1, exc)
    return                      # ← out[i] 保持 ""
```

`out[i] == ""` 承载了**两种互斥语义**：该页确实无文字 / 该页 OCR 调用失败。
调用方（`:263-267`）只能区分"全部为空"：

```python
ocr_pages_done = sum(1 for t in ocr_text_per_page if t.strip())
if ocr_pages_done == 0:
    raise PdfNeedsOcrError(...)     # 只有 0 页成功才报错
```

### 失败场景

20 页扫描版 PDF，vision provider 在第 5–18 页返回 429（`llm_ingest_concurrency()` 并发下常见）。
这 14 页变成 `""`，`ocr_pages_done = 6 > 0` → 文件被标记**入库成功**。
用��检索第 10 页内容命中为空：**没有报错、没有重试、没有部分失败标记**，
唯一痕迹是 6 条 `log.warning`。这是静默数据丢失，用户无从察觉。

且逐页 OCR 是幂等的、重试收益最大的场景，当前一次重试都没有。

## Requirements

- OCR 失败页与真正空白页必须在数据结构上可区分
- 瞬时失败（限流 / 超时 / 5xx）必须有有限次退避重试
- 重试后仍失败的页必须体现在既有的 `coverage.partial_reasons` 机制里
  （`:702-724` 已支持，当前只填 `ocr_page_cap` / `text_page_cap` / `prompt_text_cap`）
- `coverage.indexed_partial` 在存在失败页时必须为 `true`
- 全部页都失败时仍走既有的 `PdfNeedsOcrError`（行为不变）
- 不改变"全部成功"路径的任何输出

## Acceptance Criteria

- [ ] 新增测试：mock vision client 让部分页抛异常，断言 `coverage.partial_reasons`
      含失败标记、`indexed_partial is True`、`ocr_pages_done` 反映真实成功数
- [ ] 新增测试：mock 让某页前 N 次失败、第 N+1 次成功，断言重试后该页有内容
- [ ] 新增测试：全部页失败仍抛 `PdfNeedsOcrError`
- [ ] 新增测试：全部成功时 `coverage` 输出与修复前一致（防回归）
- [ ] `uv run pytest tests/ -k pdf` 全绿
- [ ] `uv run ruff check src tests` 全绿

## Non-Goals

- 不改 OCR prompt、不改渲染 DPI
- 不做失败页的**异步补偿重跑**（后续可另开任务）
- AM-1 / AM-2（`OCR_MAX_PAGES` 时机、PdfDocument 复用）不在本任务范围
