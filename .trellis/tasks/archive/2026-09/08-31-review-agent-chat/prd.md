# 审查：Agent / 聊天 / 引用

父任务：`08-31-feature-code-review`

## Goal

审查 agent runtime、工具、compaction、citations、聊天 API 与前端 Chat 的五个角度。只出报告。

## Scope

- `src/library/agent/` 全部（`runtime.py` 3585 行、tools、compaction、citation_manifest、compression、scheduler、locks）
- `src/library/api/routes_chat.py` `routes_agent.py`
- `src/library/citations.py`
- `src/library/llm/`（聊天路径用到的 adapter/factory/prompt_cache/tagged_response）
- `frontend/src/pages/ChatPage.tsx` `frontend/src/api/chatStream.ts` `frontend/src/components/TurnView.tsx` `SessionList.tsx` `frontend/src/lib/chatSession.ts`
- handlers：`reflect_turn.py` `summarize_session.py`
- 测试：`test_agent*` `test_chat*` `test_citation*` `test_session*` `test_tool*` `test_compression*` `test_conversation_compaction*` `test_read_files*` `test_recall*` `test_runtime*` `test_multimodal_chat*` `test_duckdb*` `test_generate_chart*` `test_reflect*` `test_tagged_response*`

## Extra angles

- tool_use / tool_result 配对（Anthropic 硬拒）
- 预算、取消、会话恢复、event cursor
- 引用 locator 与原文片段是否对得上

## Regression only

- M-2 / M-3 / L-5 / L-6 SSE 重连（`08-31-fix-chat-stream-resume`）

## Re-verify still-open

- AL-1 `finish_research` `dup_prior` 死代码
- AL-2 轮次耗尽日志打错数字

## Out of Scope

- Settings 里的 LLM profile 表单（归 settings）；检索索引实现（归 search）

## Acceptance Criteria

- [ ] 五个角度均有结论
- [ ] `runtime.py` 的 `run_turn` / `_run_execute_phase` / `_dispatch_tool_calls` 写明逐行或未逐行边界
- [ ] 每个 agent tool 至少结构扫描；`query_sql` `read_files` `analyze_container` 必须逐行安全面
- [ ] SSE 旧修复回归；AL-1/AL-2 复验
- [ ] finding 含 `file:line` + 失败场景
- [ ] 无产品代码改动
