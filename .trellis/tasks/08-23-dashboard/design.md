# 技术设计：知识库概览仪表盘（基准任务）

> 本文件是给目标 AI 的实现技术设计，也是本规格可落地性的依据。

## 架构与边界

- 新增一条**只读**后端端点 `GET /v1/stats/overview`（无副作用）。
- 前端新增「概览」页，调用该端点 + 现有端点渲染。
- 改动完全隔离：不提交、不并入主分支；不依赖 LLM/外部服务。

## API 契约（后端）

```
GET /v1/stats/overview
→ 200 {
  "totals": {
    "entries": <int>,   // 全库有效条目数
    "folders": <int>,   // 文件夹总数
    "tags": <int>       // 标签总数
  },
  "tasks": {
    "running": <int>,   // running 状态任务数
    "pending": <int>    // pending 状态任务数
  },
  "recent": [
    {
      "entry_id": "<uuid>",
      "display_name": "<string>",
      "folder_path": "<string|null>",   // 从根到所在文件夹的路径
      "created_at": "<iso8601|null>",
      "ingest_status": "pending|processing|done|failed|null"
    },  // 按入库时间倒序，建议 10 条
  ],
  "storage_backend": "mirror|local|s3",
  "semantic": {
    "enabled": <bool>,        // SEMANTIC_RECALL_ENABLED
    "index_ready": <bool>     // 是否有有效 index
  }
}
```

## 后端实现方式（给目标 AI）

- 新建 `src/library/api/routes_stats.py`，定义 `router = APIRouter(prefix="/stats", tags=["stats"])`，`@router.get("/overview")`。
- 在 `src/library/main.py` 用 `app.include_router(stats_router, prefix=V1_PREFIX)` 注册（参照现有 `routes_settings.py` 的注册方式）。
- 查询可复用现有仓储层（`src/library/repositories/`）：
  - 条目/文件夹计数：`repositories/files.py`、`repositories/folders.py` 的计数/list 方法（若无现成 count，用 `select(func.count(...)).where(live 条件)`，参照 `repositories/tasks.py:337` 的 `count_running_and_pending` 模式）。
  - 标签计数：`repositories/tags.py`。
  - 任务计数：可直接复用 `repositories/tasks.py` 的 `count_running_and_pending`。
  - 最近入库：查询 `file_entries`（或 join `files` 取 `ingest_status`），按入库时间倒序 limit 10；`folder_path` 参照现有 `folder_path` 序列化逻辑。
  - `storage_backend` / `semantic.enabled`：读 `library.config` 的 `get_settings()`（对齐 `routes_settings.py` 的 `server_settings` 写法）；`semantic.index_ready` 参照 `/v1/semantic-index/status` 的逻辑。
- 序列化风格对齐现有路由（`_serialize_*` 辅助 + 字典返回）。

## 单元测试（后端）

- 新建 `tests/test_stats_overview.py`（对齐现有测试的 fixture/风格，`pytest-asyncio`，`asyncio_mode=auto`）。
- 用例：
  1. 空库 → 各计数为 0、`recent` 为空数组。
  2. 灌入若干条目/文件夹/标签/任务 → 计数与种子一致。
  3. `recent` 按入库时间倒序（最新在前）。
  4. 任务 running/pending 计数正确。
  5. 只读：请求不产生写操作（不出现新增/变更记录）。

## 前端实现方式（给目标 AI）

- 新建 `desktop/src/pages/OverviewPage.tsx`；在 `desktop/src/App.tsx` 注册 route（建议 `/overview`）；在 `desktop/src/components/Sidebar.tsx` 加入「概览」入口（图标 + i18n 文案）。
- 在 `desktop/src/api/client.ts` 新增 `stats.overview()` 方法；在 `desktop/src/types/api.ts` 新增对应类型（对齐现有类型风格）。
- 页面结构（参照 `desktop/src/pages/SettingsPage.tsx` 的布局/状态管理风格）：
  - 统计卡片区：条目 / 文件夹 / 标签 / 任务（running+pending 合计）。
  - 最近入库列表：名称 + 相对时间 + ingest 状态徽章（复用现有 StatusBar/状态徽章样式）。
  - 状态行：存储后端、语义索引状态。
  - 三态：loading / 空态（`t.*.empty` 风格文案）/ 错误态（可重试）。
- 样式：主题 token（`desktop/src/styles/globals.css`）、`tailwind-merge` 的 `cn()`、i18n 文案全部走 `useI18n()`。

## 兼容与回滚

- 只读端点对现有功能零影响；新增路由不会覆盖既有路径。
- 改动即弃：实现方验证完成后不提交；若需演示，可放在独立分支或本地临时目录。
- 验证命令见 implement.md。

## 权衡

- 为什么加后端端点而非纯前端：现有公开 API 无法给出全库总条目/标签数（见 prd.md 数据源结论），纯前端仪表盘会内容偏薄，评测信号弱。
- 为什么加测试要求：把「计数正确性」变成可自动验证的硬指标，避免目视验收掩盖查询 bug。
- 一个端点 vs 多个：单端点聚合简化目标 AI 的前端拼接，也便于验收；`storage_backend`/`semantic` 虽已有其他端点，但聚合进 overview 让一次请求渲染整页。
