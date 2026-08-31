# 执行 — WebDAV

遵循父任务 `research/review-protocol.md`。

## Checklist

- [ ] `webdav_sync.py`：snapshot、import、conflict、publish、parent 链辅助函数（AH-1 回归）
- [ ] `api/routes_webdav_sync.py`
- [ ] `tasks/handlers/webdav_publish.py`
- [ ] 对应测试盲区
- [ ] 写 `report.md`

## Validation

```bash
git status --short
uv run pytest tests/ -k "webdav or publish_selected" --collect-only
```
