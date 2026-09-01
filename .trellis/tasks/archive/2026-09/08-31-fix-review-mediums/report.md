# Medium 修复集成 — SET / CROSS / FE

父：`08-31-fix-review-mediums`  
来源：`08-31-feature-code-review/report.md` §3 Medium 中用户点名的三簇。

## 子任务

| 子任务 | 来源 | 结果 |
|---|---|---|
| `fix-settings-overlay-merge` | SET-M1+M2 | merge PUT 拒绝损坏 overlay；掩码密钥 422 |
| `fix-host-token-auth` | CROSS-M1+M2 | 空 Host 421；非 ASCII token 401 不 500 |
| `fix-folder-tree-meta-errors` | FE-M1+M2 | FolderTree generation 守卫；metadata 失败可见+重试 |

## 验证

- `uv run pytest tests/ -k "settings or overlay or config_validation" -q` — 33 passed
- `uv run pytest tests/test_host_allowlist_unit.py tests/test_cors_middleware_order_unit.py -q` — 26 passed
- `cd frontend && npm run lint` — 0 errors, 31 existing warnings

## 未做

- ORG-H1（High 第 9 子任务）仍 open：软删文件夹 live unique 未落地
- ACCESS-M*、CHAT-M*、其余 Medium、Low
- 未 git commit
- FE 无浏览器工具，未做 GUI 点击验证
