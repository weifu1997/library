# 修复目录树竞态与 metadata 错误吞没

父：`08-31-fix-review-mediums` 来源：FE-M1 + FE-M2  
`.trellis/tasks/08-31-review-frontend-pages/report.md`

## Problem

- FE-M1：`FolderTree` `load` / `loadDetail` 无 `cancelled`/`generation`，后到的响应会覆盖当前行。
- FE-M2：`LibraryPage` metadata `.catch` 把失败当成 `meta=null`，用户分不清「无字段」和「请求失败」。

## Requirements

- 目录树请求用 generation 或 cancelled，过期响应不得 `setChildren`/`setEntries`。
- metadata 失败要有可见错误 + 可重试；不要把 catch 当成空 metadata。
- 不改变成功加载路径。前端无 test runner：`npm run lint` 绿即可。

## Acceptance Criteria

- [x] `FolderTree` load/loadDetail 有过期守卫
- [x] metadata 失败在 MetaPanel 或 Library 可见，不是空白当无数据
- [x] `npm --prefix frontend run lint` 0 errors（31 warning 预算不变）

## Out of Scope

FE-L1 Search 中文硬编码；FE-L2 ESLint 清零。
