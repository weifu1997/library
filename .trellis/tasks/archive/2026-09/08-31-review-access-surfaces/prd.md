# 审查：接入面

父任务：`08-31-feature-code-review`

## Goal

审查 MCP、CLI、eval、导出/knowledge pack 的五个角度。只出报告。

## Scope

- `src/library/mcp_server.py` `api/routes_mcp.py`
- `src/library/cli/` 全部（repl、commands、oneshot、eval_cmd、init、storage_cmd、client、render）
- `src/library/eval/` 全部
- `src/library/services/exports.py` `knowledge_pack.py` `api/routes_exports.py`
- `src/library/server_discovery.py` `server_main.py`
- 测试：`test_mcp*` `test_cli*` `test_eval*` `test_export*` `test_discover*` `test_server_*`

## Extra angles

- MCP / CLI 是否绕过 API 鉴权或写路径校验
- eval 是否对真实库做破坏性写
- 导出是否泄漏 API key 或超出用户选中范围

## Out of Scope

- Web GUI 页面；agent 工具实现（CLI 只是调用方）

## Acceptance Criteria

- [ ] 五个角度均有结论
- [ ] MCP、CLI、eval、导出四条接入都有结论
- [ ] finding 含 `file:line` + 失败场景
- [ ] 无产品代码改动
