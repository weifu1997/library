# 前端接入 ESLint 基线

父任务：`08-31-full-code-review`
来源：`.trellis/tasks/08-31-full-code-review/report.md` **A-3**

## Problem

`frontend/package.json` 的 `lint` 脚本实际是 `tsc -b --noEmit`——**只有类型检查，没有 ESLint**。
React hooks 依赖数组、条件调用 hook、`useEffect` 竞态、stale closure 这类问题
**没有任何自动化拦截**。

而 M-2 / M-3 / L-5 / L-6 四条 finding 全部出自流式与副作用代码，
正是 `eslint-plugin-react-hooks` 该拦的那一类。

## Requirements

- 接入 ESLint 9 flat config + `typescript-eslint` + `eslint-plugin-react-hooks`
- `npm run lint`（CI 已在调用）必须同时跑 tsc 和 eslint
- **错误必须清零**
- 既有警告不得阻塞落地，但必须**锁住上限**：只能减少，新增即失败
- 生成的类型（`src/types/generated`）与 `dist` 排除在外

## Acceptance Criteria

- [x] `npm run lint` 同时执行 tsc 与 eslint，退出码 0
- [x] ESLint 错误数为 **0**
- [x] 警告上限锁定（`--max-warnings 31`），实测降到 30 会失败、31 通过
- [x] `npm run build` 仍然成功
- [x] `no-explicit-any` 设为 error（代码库当前 0 处 any，锁住这个状态）

## 结果

| 项 | 数量 |
|---|---|
| errors | **0**（修掉 1 处 `prefer-const`） |
| warnings | 31 = 15 × `react-hooks/exhaustive-deps` + 16 × `react-refresh/only-export-components` |

### 为什么不清零警告

15 条 `exhaustive-deps` 集中在 `OfficeViewer.tsx`(9)、`EpubViewer.tsx`(2)、
`ViewerShared.tsx`、`SettingsPage.tsx` 等复杂组件。
**给 effect 补依赖会改变重跑时机**，在这些带 zoom/position ref 与外部渲染库的组件里
很容易引入无限重渲染。在"接入 lint 工具"这个任务里顺手改它们，是拿一个可验证的
基础设施改动去赌一批未经测试的行为变更。

选择：警告可见但不阻塞，上限锁死。清理另开任务，逐个组件带验证地做。

## Non-Goals

- 不清理既有 15 条 hooks 警告（另开任务）
- 不引入 Prettier / 格式化规则（与本任务的缺陷拦截目标无关）
