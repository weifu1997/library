# 前端展示 ingest coverage 与部分失败状态

父任务：`08-31-full-code-review`
来源：实施 `08-31-fix-folder-cycle-guard` 期间的核实发现（见下"背景"）

## Problem

后端在 ingest 时会算出一份 coverage 数据并写进 `File.description` JSON：

- `indexed_partial` — 本次索引是否不完整
- `partial_reasons` — 不完整的原因（`text_page_cap` / `ocr_page_cap` / `prompt_text_cap`，
  `08-31-fix-ocr-partial-failure` 还会新增 `ocr_page_failures`）
- `total_pages` / `indexed_pages` / `ocr_used` / `ocr_pages_done` / `text_truncated`

**这份数据目前没有任何出口。** 已核实：

| 层 | 现状 |
|---|---|
| 持久化 | ✅ 写入 `File.description.coverage`（`pipelines/_text_indexer.py:127`） |
| HTTP API | ❌ **零暴露**。`services/user_files.py:196-227` 的 `get_user_metadata` 只从 `description` 取 `preview`（`:218` 的 `_description_preview` 仅读 `sections`），coverage 字段整个被丢掉；其余端点不返回 `description` |
| 前端 | ❌ **零消费**。`grep -rn "partial_reasons\|indexed_partial\|ocr_pages_done" frontend/src` → 0 命中 |

### 后果

用户上传一份 300 页 PDF，后端因页数上限只索引了前 50 页，或（修复 AH-2 后）因 provider 限流
漏掉 14 页——**界面上这份文件与完整索引的文件长得一模一样**，状态都是"已完成"。
用户检索不到内容时无法判断是"库里没有"还是"这份文件没索引全"。

这也意味着 `08-31-fix-ocr-partial-failure` 只能解决半个问题：它让失败**可记录**，
但不让失败**可见**。那个任务 PRD 写的验收目标是"用户无从察觉"，只改后端达不到。

## Requirements

- `get_user_metadata` 返回 coverage（至少 `indexed_partial` / `partial_reasons` /
  `total_pages` / `indexed_pages`），字段缺失或格式异常时安全降级为 `null`
- 契约再生成后**不得产生漂移**（CI 的 contract job 会 `git diff --exit-code`）
  - 范围调整：**不给该端点新增 `response_model`**。核实后发现 `routes_user_files.py`
    的 8 个路由中只有 `/search` 有响应模型，其余均返回 `dict[str, Any]`；
    单独给 metadata 补一个 15 字段模型属于 API 契约改造，是另一条线的工作。
    前端消费的是手写的 `types/api.ts:FileMetadata`（已有索引签名，加字段兼容）。
- 文件详情界面在 `indexed_partial` 为真时给出明确提示，说明**哪些内容没被索引**及原因
- `partial_reasons` 的**未知值必须有兜底文案**——后端会继续新增原因，前端不能因此空白或崩溃
- 提示不得使用告警红色：部分索引是正常降级而非错误，视觉权重要低于 ingest 失败

## Acceptance Criteria

- [ ] `GET` 文件元数据接口返回 coverage 字段，含契约测试
- [ ] `description` 为 `None` / 非 dict / 缺 `coverage` 键时接口不报错
- [ ] 前端在部分索引时展示提示，含页数（"已索引 50 / 300 页"）与原因文案
- [ ] 未知 `partial_reasons` 值渲染为兜底文案而非空白（需有测试或明确验证记录）
- [ ] i18n 中英文文案齐全
- [ ] `npx tsc -b --noEmit` 通过；`uv run pytest tests/ -k "user_files or metadata"` 通过

## Dependencies

与 `08-31-fix-ocr-partial-failure` **无强制先后**：本任务展示既有的三个 reason 即可独立验收。
但若 OCR 任务先落地，本任务应一并覆盖新增的 `ocr_page_failures`。
两者都改到 coverage 的语义，**不建议并行开工**，避免字段定义打架。

## Non-Goals

- 不改 coverage 的计算逻辑（归 pipelines 侧任务）
- 不做"重新索引这份文件"的操作入口（另议）
- 不展示 `chunk_count` / `chunked` 等纯内部诊断字段
