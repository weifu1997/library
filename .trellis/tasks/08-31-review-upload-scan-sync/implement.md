# 执行 — 上传 / 扫描 / 同步

遵循父任务 `research/review-protocol.md`。

## Checklist

- [ ] `services/upload.py` + `api/routes_upload.py` + `upload_limits.py`
- [ ] `services/user_files.py` + `api/routes_user_files.py`（循环导入回归）
- [ ] `services/scan.py` `sync.py` `reprocess.py` `attachments.py`
- [ ] `tasks/handlers/bulk_reprocess_files.py`
- [ ] 对应测试盲区
- [ ] 写 `report.md`

## Validation

```bash
git status --short
uv run pytest tests/ -k "upload or user_files or scan or sync or reprocess" --collect-only
```
