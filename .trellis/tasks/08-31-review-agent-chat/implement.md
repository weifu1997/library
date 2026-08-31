# 执行 — Agent / 聊天 / 引用

遵循父任务 `research/review-protocol.md`。建议第一个 start 的子任务。

## Checklist

- [ ] `agent/runtime.py` 三个大函数 + 状态机边界
- [ ] `agent/tools/*`（安全面优先 query_sql / read_files / analyze_container / query_log）
- [ ] compaction / citation_manifest / compression_adapter / read_compression / stable_context
- [ ] tool_scheduler / tool_locks / tool_display / cache_metrics
- [ ] `api/routes_chat.py` `routes_agent.py` `citations.py` `llm/*`
- [ ] 前端 ChatPage / chatStream / TurnView / SessionList / chatSession（SSE 回归）
- [ ] reflect / summarize handlers
- [ ] 对应测试盲区
- [ ] 写 `report.md`

## Validation

```bash
git status --short
uv run pytest tests/ -k "agent or chat or citation or session or tool or compression or runtime" --collect-only
```
