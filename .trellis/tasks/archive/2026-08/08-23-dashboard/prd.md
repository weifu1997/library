# UI 可见功能任务规格：知识库概览仪表盘（供 AI 编码评测用）

> 父任务：`.trellis/tasks/08-23-project-requirements`（编码评测基准任务套件）。本任务为其中一份**独立交付**的基准任务。

## Goal

产出一份**可直接交付给其他 AI 实现**的全栈功能任务规格，用于**评测目标模型的编码能力**。功能是**知识库概览仪表盘**（Dashboard）：打开前端页面即可看到知识库统计（条目 / 文件夹 / 标签 / 任务数、最近入库文件、存储与语义索引状态）。

硬性约束：
- **页面肉眼可见**：功能落地后打开页面（或截图）即可看出效果。
- **可目视验收**：验收以"页面上观察到什么"为准。
- **自包含**：另一 AI 拿到本需求 + 可运行环境即可动手，无需深度背景。
- **不入库**：本次改动不提交、不并入项目（本机验证后丢弃或隔离）。
- **全栈 + 测试**：需要新增一个后端只读统计端点 + 前端仪表盘页 + 单元测试。

## 背景（给目标 AI 的最小上下文）

- Library v0.3.6：本地优先私人 AI 知识库。后端 FastAPI（`src/library/api/`，`library serve` 起在 127.0.0.1:8000），前端 React + Vite（`desktop/`，`npm run dev` 起在 127.0.0.1:5173，`/v1` 与 `/health` 由 Vite 代理到后端）。
- 前端结构：页面在 `desktop/src/pages/`；API 封装在 `desktop/src/api/client.ts`（类型在 `desktop/src/types/api.ts`）；路由在 `desktop/src/App.tsx`；侧栏在 `desktop/src/components/Sidebar.tsx`；i18n 文案在 `desktop/src/lib/i18n.ts`。
- 后端结构：路由在 `src/library/api/routes_*.py`（`APIRouter`，统一挂在 `/v1` 前缀下）；数据访问走仓储层 `src/library/repositories/`（异步 SQLAlchemy session）；模型定义在 `src/library/db/models/`。
- 现有页面：Settings、Library、Chat、Activity、Help/About。

## 已确认事实（数据源勘察结论）

- 现有公开 API **没有**提供全库统计：`GET /v1/folders` 只返回当前层的 folders + entries；`GET /v1/search` 必须带 `q`（`min_length=1`）；无公开 tags 端点。因此**需要新增后端统计端点**。
- 可直接复用的现有端点：`GET /v1/tasks/running-count`、`GET /v1/settings/server`（含 `storage_backend`、`embedding_api_key_set`、`semantic_recall_enabled`、`rerank_configured`）、`GET /v1/semantic-index/status`。
- DB 有 `tags` 表（tag 计数可查）；条目/文件夹均有仓库层可计数。

## 需求

### 后端（新增只读统计端点）

- **R1** 新增 `GET /v1/stats/overview`（只读，无副作用），返回：
  - `totals.entries`：全库有效条目数
  - `totals.folders`：文件夹总数
  - `totals.tags`：标签总数
  - `tasks.running` / `tasks.pending`：运行中 / 等待中的任务数
  - `recent`：最近入库文件列表（建议 N=10，按入库时间倒序；每项含 `entry_id`、`display_name`、`folder_path`、`created_at`、`ingest_status`）
  - `storage_backend`：存储后端（`mirror` / `local` / `s3`）
  - `semantic`：语义索引状态（是否启用、是否有有效 index）
- **R2** 实现遵循项目约定：在 `src/library/api/routes_stats.py` 建 router 挂 `/v1`；查询走仓储层或直接会话查询；JSON 序列化对齐现有路由风格。
- **R3** 单元测试：至少覆盖 —— 空库返回零值；有数据时计数正确；`recent` 排序正确（最新在前）；任务计数正确。

### 前端（仪表盘页）

- **R4** 新增「概览」页（route 建议 `/overview`），侧栏加入口。
- **R5** 页面内容：
  - 统计卡片：条目数 / 文件夹数 / 标签数 / 运行中+等待任务数
  - 最近入库列表（文件名、时间、ingest 状态徽章，可点击跳转对应条目）
  - 状态行：存储后端、语义索引状态
- **R6** 状态处理：加载中 loading；空库空态（友好提示）；请求失败错误态（可重试）。
- **R7** 样式对齐现有页面：主题 token（`desktop/src/styles/globals.css`）、i18n 文案、组件风格。

### 整体

- **R8** 改动**不提交**到项目（仅本机验证）。

## 非目标

- 不把改动并入项目 / 不提交（评测环境或临时分支）。
- 不做与现有产品长期演进兼容的完整打磨。
- 不做依赖外部付费服务的功能（本任务不需要 LLM 调用即可完成）。
- 不做权限/多租户/迁移等与评测无关的能力。

## 验收标准（目视 + 测试）

- [ ] 启动前后端后，侧栏出现「概览」，点击进入仪表盘页。
- [ ] 统计卡片显示**真实数字**（与 `data/library` 实际内容一致）。
- [ ] 最近入库列表按时间倒序显示真实文件（名称 / 时间 / 状态）。
- [ ] 状态行正确显示存储后端（mirror）与语义索引状态。
- [ ] 空库时页面显示空态而非报错/白屏。
- [ ] 后端 `GET /v1/stats/overview` 返回符合契约的 JSON；对应单元测试全部通过。
- [ ] 本机验证后改动未提交（git status 干净或改动仅存在于未跟踪状态）。

## 开放问题

- 无（已收敛：交付形态 / 功能选型 / 后端范围均已确定）。

## Notes

- 具体验收演示：用户可先手动灌入 `samples/` 素材再让目标 AI 实现，便于目视对比。
- 技术设计见本任务 `design.md`；交付与验证见 `implement.md`。
