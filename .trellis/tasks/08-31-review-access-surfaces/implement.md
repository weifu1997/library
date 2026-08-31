# 执行 — 接入面

遵循父任务 `research/review-protocol.md`。

## Checklist

- [ ] `mcp_server.py` `api/routes_mcp.py`
- [ ] `cli/`：repl 命令、oneshot、init、storage、client 发现
- [ ] `eval/` + `cli/eval_cmd.py`
- [ ] `exports.py` `knowledge_pack.py` `routes_exports.py`
- [ ] `server_discovery.py` `server_main.py`
- [ ] 对应测试盲区
- [ ] 写 `report.md`

## Validation

```bash
git status --short
uv run pytest tests/ -k "mcp or cli or eval or export or discover or server_main or server_discovery" --collect-only
```
