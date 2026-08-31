# 审查：前端其余页

父任务：`08-31-feature-code-review`

## Goal

审查 Library / Search / Overview 页面、知识库组件、HTTP 客户端与 OpenAPI 契约一致性。只出报告。Chat 与 Settings 不在本任务（分属 agent-chat / settings）。

## Scope

- `frontend/src/pages/LibraryPage.tsx` `SearchPage.tsx` `OverviewPage.tsx` `HelpPage.tsx` `AboutPage.tsx`
- `frontend/src/components/library/**` `ActivityPopover.tsx` `BackendGate.tsx` `Sidebar.tsx` `TopBar.tsx` `StatusBar.tsx`
- `frontend/src/api/client.ts` `frontend/src/types/api.ts` `frontend/src/types/generated/openapi.d.ts`
- `openapi/openapi.json` 与后端路由 response 注解（契约漂移）
- `frontend/eslint.config.js`（回归 A-3）
- 后端只读对照：`api/routes_stats.py`（Overview 数据）
- 测试：`test_stats_overview.py` `test_openapi_contract.py` `test_gui_search*` `test_ingest_coverage_surface*`

## Extra angles

- 竞态：快速切换文件夹/文件时的过期响应
- 错误是否被 `client.ts` 吞成无信息网络错误
- OpenAPI `dict[str, Any]` 导致的响应字段漂移

## Regression only

- A-3 ESLint + react-hooks（`08-31-frontend-eslint-baseline`）
- 前端 ingest coverage 展示（`08-31-frontend-coverage-surface`）

## Out of Scope

- ChatPage / chatStream（agent-chat）；SettingsPage / LlmProfileEditor（settings）

## Acceptance Criteria

- [ ] 五个角度均有结论
- [ ] Library / Search / Overview 三页均被覆盖
- [ ] ESLint 与 coverage 表面回归
- [ ] 至少列出一处契约漂移或显式写「与 OpenAPI 一致」
- [ ] finding 含 `file:line` + 失败场景
- [ ] 无产品代码改动
