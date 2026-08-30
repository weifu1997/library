# 技术设计 — OCR 部分失败可见化

## 决策 1：用什么表示"失败页"

`_ocr_pdf_pages` 现在返回 `list[str]`。备选：

| 方案 | 评价 |
|---|---|
| A. 返回 `list[str \| None]`，`None` = 失败 ✅ | 类型即语义；调用方必须显式处理，编译期（tsc 无、但 ruff/阅读）可见 |
| B. 返回 `(pages, failed_indices)` 元组 | 调用方容易只取第一个元素而忽略失败集 |
| C. 失败页填哨兵字符串 | 哨兵会流入索引文本，风险高 |

**选 A**。`out: list[str | None] = [None] * pages_to_ocr`，成功时写字符串（可能是 `""`），
失败时保持 `None`。这样 `""`（真空白）与 `None`（失败）天然分开。

调用方 `:262` 之后做一次归一：
```python
raw = await _ocr_pdf_pages(body, total_pages)
failed_pages = [i for i, t in enumerate(raw) if t is None]
ocr_text_per_page = [("" if t is None else t) for t in raw]
```

## 决策 2：重试策略

在 `_ocr_one` 内部重试，**不**在外层重跑整批——外层重跑会重新渲染 JPEG，浪费 CPU。

- 次数：`OCR_PAGE_RETRIES = 2`（总计 3 次尝试）
- 退避：`0.5s * 2**attempt`（0.5s、1.0s），带 ±20% 抖动避免并发同步重试
- 重试**在 `async with sem` 内部**：持有信号量重试会占着并发额度睡觉。
  → 改为退出 sem 后 sleep，再重新入 sem。
- 不重试的情形：调用被 `asyncio.CancelledError` 中断（必须原样上抛）

```python
for attempt in range(OCR_PAGE_RETRIES + 1):
    try:
        async with sem:
            resp = await client.complete(...)
        break
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if attempt == OCR_PAGE_RETRIES:
            log.warning("OCR failed for page %d after %d attempts: %s", i + 1, attempt + 1, exc)
            return                      # out[i] 保持 None
        await asyncio.sleep(_backoff(attempt))
```

注意 `except Exception` 不会捕获 `CancelledError`（Py3.8+ 它继承 `BaseException`），
显式 re-raise 只是防御性表达意图。

## 决策 3：如何接入 coverage

`_coverage`(`:694`) 已有 `partial_reasons` / `indexed_partial` / `ocr_pages_done`。
现状 `indexed_partial = indexed_pages < total_pages or text_truncated` —— **失败页不会让它为真**，
因为 `indexed_pages` 取的是页数上限而非成功页数。

改动：
1. `:275-277` 处追加 `if failed_pages: partial_reasons.append("ocr_page_failures")`
2. `_coverage` 增参 `ocr_failed_pages: int = 0`；
   `indexed_partial` 补一项 `or ocr_failed_pages > 0`
3. coverage 字典在 `ocr_used` 分支下增加 `"ocr_failed_pages": ocr_failed_pages`

`ocr_pages_done` 的语义保持不变（`sum(1 for t if t.strip())`），
但现在它与 `ocr_failed_pages` 一起才能拼出完整图景：
`total = done + failed + 真空白页`。

## 影响面

- `pipelines/pdf.py`：`_ocr_pdf_pages` 签名返回类型变化、`_ocr_one` 加重试、
  `run()` 归一化 + 填 reason、`_coverage` 加参数
- 无 schema 变更（`coverage` 是 JSON 列，加字段向后兼容）
- 无 API 变更；前端若展示 `partial_reasons` 需要新增一个文案键（本任务不改前端，
  未知 reason 应已有兜底渲染——**实施时需确认**）

## 风险

`_ocr_pdf_pages` 返回类型变了，需确认无其它调用方。
审计时只见 `pdf.py:262` 一处，实施前用 grep 复核。
