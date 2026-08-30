# 技术设计 — 展示 ingest coverage

## 决策 1：后端出口放在哪

`GET /v1/file-entries/{entry_id}/metadata` → `services/user_files.py:get_user_metadata`。
它已经是"用户可见元数据"的唯一聚合点（summary / preview / tags / webdav_remote 都在这里），
coverage 属于同一类"关于这条记录的事实"，加在这里而不是新开端点。

`coverage` 存在 `File.description["coverage"]`。`description` 是 AI 生成的 JSON 列，
形状不受约束（可能是 `None`、非 dict、或缺 `coverage` 键），必须安全提取：

```python
def _coverage_summary(description: Any | None) -> dict[str, Any] | None:
    if not isinstance(description, dict):
        return None
    coverage = description.get("coverage")
    if not isinstance(coverage, dict):
        return None
    ...  # 白名单取字段，类型不符则丢弃该字段
```

**只透出用户能理解的字段**，`chunked` / `chunk_count` / `unit` 等纯内部诊断不外泄
（PRD Non-Goals）。透出：`indexed_partial`、`partial_reasons`、`total_pages`、
`indexed_pages`、`ocr_used`、`ocr_pages_done`、`ocr_failed_pages`。

## 决策 2：不给这个端点加 response_model

PRD 原文要求"OpenAPI 响应模型同步更新"。核实后调整：

`routes_user_files.py` 里 8 个路由**只有 `/search` 有 `response_model`**，其余（含 metadata）
都返回 `dict[str, Any]`。给 metadata 单独补一个 15 字段的响应模型，等于在本任务里顺带做
一次 API 契约改造——那是 `08-30-api-contract-openapi-ts` 那条线的工作，不是本任务的。

**本任务的处理**：保持 `dict[str, Any]`，但仍然跑 `python -m library.openapi_export` +
`npm run gen:api`，确认**没有契约漂移**（CI 的 contract job 会 `git diff --exit-code`）。
前端类型走手写的 `types/api.ts:FileMetadata`——那才是应用实际消费的类型，
且它已有 `[key: string]: unknown` 索引签名，加字段是兼容的。

> 已在 prd.md 的 Non-Goals 记下这条范围调整。

## 决策 3：未知 `partial_reasons` 的兜底

后端会持续新增 reason（本轮就新增了 `ocr_page_failures`）。前端**不能**用
`t.library.coverage.reasons[key]` 直接索引后渲染 `undefined`。

```ts
const reasonLabel = (key: string): string =>
  t.library.coverage.reasons[key] ?? t.library.coverage.unknownReason(key);
```

兜底文案把原始 key 显示出来（"部分内容未索引（ocr_page_failures）"），
这样即使前端没跟上后端，用户和支持人员仍拿得到可搜索的线索。

## 决策 4：视觉权重

部分索引是**正常降级**，不是错误——ingest 本身是成功的。所以：

- 用 amber（`border-amber-500/20 bg-amber-500/5`），不用 red（red 是 ingest failed 的语义）
- 放在 File Info 卡之后、AI Summary 之前：它是"读这份摘要前你该知道的前提"
- `indexed_partial` 为 false 时**整块不渲染**，不占视觉空间

主行给出可量化的事实（"已索引 50 / 300 页"），次行列原因。OCR 失败单独一行，
因为它是唯一"本可以成功却失败了"的原因，其余都是配置上限。

## 影响面

- `services/user_files.py`：+1 私有提取函数，`get_user_metadata` 返回值 +1 键
- `frontend/src/types/api.ts`：+1 interface，`FileMetadata` +1 可选字段
- `frontend/src/components/library/MetaPanel.tsx`：+1 卡片
- `frontend/src/lib/i18n.ts`：中英各 +1 文案块
- `openapi/openapi.json` / `generated/openapi.d.ts`：预期**无变化**（端点无 response_model）

## 风险

`ocr_failed_pages` 只在 `08-31-fix-ocr-partial-failure`（已落地 db2c86d）之后写入的记录里存在。
历史记录没有该字段——提取函数必须容忍缺失，前端也要容忍 `undefined`。
