# 修复 Stop 取消错误的 conversation

父：`08-31-fix-review-highs` 来源：CHAT-H1  
`.trellis/tasks/08-31-review-agent-chat/report.md`

## Problem

`ChatPage.stop` 把 **session id** 传给 `cancelChat` → `POST /v1/conversations/{id}/cancel`。路由按 Conversation 查，404。客户端把 404 当成功。`_run_durable_turn` 继续跑。

## Requirements

- Stop 必须对**当前 turn 的 conversation id** 调 cancel（事件 `conversation` 已下发则用它；尚未到达则等或走 abort+重试 cancel）。
- 404 在客户端仍认为 turn live 时不得当成功。
- 后台 `_ACTIVE_TURNS` 被 cancel，后续 send 不被已停 turn 的锁挡住过久。
- 不改变正常完成路径。

## Acceptance Criteria

- [x] 测试或 e2e：Stop 打到 `/conversations/{conversation_id}/cancel`，不是 session id
- [x] 后台 task 被 cancel（或等价：不再写后续 agent_events）
- [x] 现有 chat/session 测试绿

## Out of Scope

CHAT-H2 图表；SSE 重连（已修）。
