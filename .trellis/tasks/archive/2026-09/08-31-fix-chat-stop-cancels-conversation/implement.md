# 执行 — CHAT-H1

- [x] `ChatPage.tsx` `stop` 使用 live turn 的 `conversationId`
- [x] `cancelChat`：live turn 时 404 视为失败或重试
- [x] 回归测试（前端若无 runner：后端 e2e 证明 session id 404 且 task 仍跑；前端用 conversation id）
- [x] `uv run pytest tests/ -k "chat or session" -q`

证据：`frontend/src/pages/ChatPage.tsx` stop；`chatStream.ts` cancelChat；`routes_chat.py` cancel_chat_turn。
