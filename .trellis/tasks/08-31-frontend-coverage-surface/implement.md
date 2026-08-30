# 执行计划 — 展示 ingest coverage

## Step 1 — 后端提取并透出
- [x] `services/user_files.py` 新增 `_coverage_summary(description)`，白名单取字段并做类型校验
- [x] `get_user_metadata` 返回值加 `"coverage": _coverage_summary(file_row.description)`
- 验证：`uv run pytest tests/ -k "user_files or metadata"`

## Step 2 — 后端健壮性测试
- [x] `description` 为 `None` / 字符串 / 缺 `coverage` 键 / `coverage` 非 dict → 返回 `None` 不抛错
- [x] 正常 coverage → 只透出白名单字段，`chunk_count` 等内部字段不出现
- [x] 缺 `ocr_failed_pages` 的历史记录 → 不报错

## Step 3 — 契约再生成
- [x] `uv run python -m library.openapi_export`
- [x] `cd frontend && npm run gen:api`
- [x] `git diff --exit-code -- openapi/ frontend/src/types/generated/` 应无输出（端点无 response_model）
      若有漂移，说明判断有误，停下来重新评估决策 2

## Step 4 — 前端类型与渲染
- [x] `types/api.ts` 加 `IngestCoverage` interface，`FileMetadata.coverage?: IngestCoverage | null`
- [x] `MetaPanel.tsx` 加 coverage 卡片（amber，`indexed_partial` 为假时不渲染）
- [x] 未知 reason 走兜底文案

## Step 5 — i18n
- [x] `lib/i18n.ts` 中英各加 `library.coverage` 块：标题、页数行、各 reason 文案、unknownReason 兜底

## Step 6 — 校验
- [x] `cd frontend && npx tsc -b --noEmit`
- [x] `uv run ruff check src tests`
- [x] `uv run pytest tests/` 全量
- [x] `git diff --stat` 确认改动范围

## 回滚点

Step 1-3（后端）可独立落地：即使前端不做，coverage 也已经通过 API 可查，
CLI / 脚本 / 支持人员能拿到。Step 4-5 是纯展示层，可单独 revert。


---

## 执行结果（2026-08-31）

| 检查 | 结果 |
|---|---|
| `uv run ruff check src tests` | ✅ All checks passed |
| `npx tsc -b --noEmit` | ✅ exit 0 |
| `npm run build` | ✅ built in 6.97s |
| `uv run pytest tests/` 全量 | ✅ **587 passed, 1 skipped**（本任务前 581，新增 6） |
| 契约漂移 | ✅ `git diff --exit-code -- openapi/ generated/` 无输出 |

### 范围调整（已同步进 prd.md）

不给 metadata 端点加 `response_model`，理由见 design.md 决策 2。
契约再生成后确认无漂移，符合 CI contract job 的要求。

### 顺带发现（未修，不属本任务）

`library.services.user_files` **无法作为首个模块导入**：
`user_files → pipelines.registry → … → tasks.handlers.mine_citation_graph
→ services.exports → user_files` 构成循环，裸解释器里 `import
library.services.user_files` 直接 ImportError。

已用 `git stash` 确认**这是既有问题，与本次改动无关**——测试套件因为导入顺序不同
碰不到它。新增的测试文件顶部需要 `import library.main` 才能绕开，这本身就是味道。
建议另开任务打断该环（大概率是把 `exports.py` 对 `get_user_metadata` 的依赖改成延迟导入）。
