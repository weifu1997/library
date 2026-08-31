# 修复 Chat 不渲染 user_artifact

父：`08-31-fix-review-highs` 来源：CHAT-H2

## Problem

`generate_chart` / `query_sql` `export_csv` 发 `user_artifact` SSE。`applyEventToTurnList` 无该 case。Chat 只显示 tool_call 行。

## Requirements

- 直播 SSE 处理 `user_artifact`，Turn 上保存 artifact 列表。
- `TurnView` 渲染 Vega-Lite 或下载链接。
- 会话回放：从 transcript / tool result `__user_only__` 能恢复（至少新会话）。
- 不把 `__user_only__` 再喂给模型。

## Acceptance Criteria

- [x] 有图表事件时 Chat 出现可视化或明确下载入口
- [x] 现有 generate_chart e2e（SSE 帧）仍绿
- [x] 无 `any`

## Out of Scope

Stop（CHAT-H1）；CLI spinner（已可用）。
