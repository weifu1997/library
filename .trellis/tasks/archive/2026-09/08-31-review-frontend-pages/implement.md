# 执行 — 前端其余页

遵循父任务 `research/review-protocol.md`。

## Checklist

- [ ] LibraryPage + `components/library/**`（含 viewers）
- [ ] SearchPage
- [ ] OverviewPage + `routes_stats.py` 对照
- [ ] Help/About、Sidebar/TopBar/StatusBar/BackendGate/ActivityPopover
- [ ] `api/client.ts` 错误处理与竞态
- [ ] `types/api.ts` vs generated OpenAPI vs 后端实际 JSON
- [ ] ESLint 基线与 coverage 表面回归
- [ ] 写 `report.md`

## Validation

```bash
git status --short
npm --prefix frontend run lint
```

lint 只读；不要 `--fix`。
