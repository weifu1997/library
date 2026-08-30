# 技术设计：编码评测基准任务套件（父任务）

## 结构

- 父任务持有：需求池、任务地图、共同约束、交叉验收。
- 每个子任务 = 一份独立的编码评测基准任务，各自有 `prd.md`（需求+验收）、`design.md`（技术设计）、`implement.md`（交付+验证）。
- 子任务之间零依赖，可单独转交目标 AI。

## 共同技术基线（所有子任务规格引用）

- Library v0.3.6 可运行环境：后端 `library serve`（127.0.0.1:8000）、前端 `desktop/` `npm run dev`（127.0.0.1:5173，`/v1` 代理）。
- 前端约定：页面 `desktop/src/pages/`、API 封装 `desktop/src/api/client.ts`、类型 `desktop/src/types/api.ts`、路由 `App.tsx`、侧栏 `Sidebar.tsx`、i18n `desktop/src/lib/i18n.ts`、样式主题 token `desktop/src/styles/globals.css`。
- 后端约定：路由 `src/library/api/routes_*.py`（`/v1` 前缀挂载于 `main.py`）、仓储层 `src/library/repositories/`、模型 `src/library/db/models/`。

## 规格一致性约束

- 每个规格必须自包含：目标 AI 无需追问即可开工。
- 验收必须可目视判断，辅以可运行测试。
- 明确标注"改动不入库"。
- 引用的 API/组件路径必须真实存在（已逐一勘察核实）。

## 两份任务的技术形态

| 子任务 | 技术形态 | 是否动后端 |
|---|---|---|
| 08-23-dashboard | 新后端只读端点 + 前端新页面 + 单测 | 是（只读，无副作用） |
| 08-23-settings-llm-rework | 前端预设模板 + 默认表单 + 高级折叠；`POST /v1/settings/llm/test` 加可选 `profile=default` | 小改（仅 test 端点，其余复用） |
