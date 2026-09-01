# 清掉剩余 13 条 exhaustive-deps 警告

## Goal

清掉 `frontend/src/components/library/viewers/EpubViewer.tsx`（2 条）与 `OfficeViewer.tsx`（11 条）里剩余的 13 条 `react-hooks/exhaustive-deps` 警告，且不引入渲染/effect 重跑死循环。

## Requirements

- 全部 13 条警告清零，行为语义不得退化：
  - **ref-in-cleanup**（EpubViewer:248，OfficeViewer:1189/1190）：effect 运行时把 `hostRef.current` / `canvasRef.current` 拷到局部变量，cleanup 引用该局部变量。
  - **`t.viewer` 缺失**（OfficeViewer:485/1197）：`t.viewer` 是模块级常量 `STRINGS[locale]` 的子对象，引用稳定，直接加入依赖（换 locale 时才重跑，无循环）。
  - **`zoom.zoomRef` 缺失**（OfficeViewer:594/1197）：`zoom.zoomRef` 是稳定 ref（`useRef(1)`），直接加入依赖。
  - **`position` 缺失**（OfficeViewer:962/1008/1201/1260）：`position` 是 `useState` 对象，新版插件把 `.current` 成员访问当 ref 判为非法依赖；改为依赖整个 `position` 对象（`setPosition` 每次传新对象，重跑时机与现状一致）。
  - **`zoom` 对象缺失**（OfficeViewer:515/1227，fit-width effect）：`zoom` 对象每次 render 重建，依赖它会每次 render 重挂 ResizeObserver。改用 latest-ref：`setZoomRef` 每 render 同步 `zoom.setZoom`，effect 经 `setZoomRef.current(...)` 调用，依赖保持 `[fitMode]`。
  - **`fontSize` 缺失**（EpubViewer:250）：book-init effect 不能因字体变化重建整本书。加 `fontSizeRef` latest-ref 供 init effect 读初始值，已存在的 `[fontSize]` 独立 effect（271 行）负责后续变更。

## Acceptance Criteria

- [ ] `npx eslint src` 全仓 `react-hooks/exhaustive-deps` 警告为 0
- [ ] `npm run lint`（`tsc -b --noEmit && eslint . --max-warnings 31`）通过；总警告数由 29 降到 16（余 16 条均为 ViewerShared.tsx 的 `react-refresh/only-export-components`，与本任务无关）
- [ ] 改动仅限 `EpubViewer.tsx` / `OfficeViewer.tsx`，不动 `ViewerShared.tsx` 的 zoom hook 本身

## Notes

- 沿用项目既有 latest-ref 模式（`ViewerShared.applyZoomValueRef`）。
- 前端无测试框架；用 lint + tsc 作为验证门。
