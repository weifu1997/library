# 审查：上传 / 扫描 / 同步

父任务：`08-31-feature-code-review`

## Goal

审查 upload、user files、scan、reprocess、本地文件 sync 的五个角度。只出报告。

## Scope

- `src/library/services/upload.py` `user_files.py` `scan.py` `sync.py` `reprocess.py` `attachments.py`
- `src/library/api/routes_upload.py` `routes_user_files.py`
- `src/library/upload_limits.py`
- `src/library/tasks/handlers/bulk_reprocess_files.py`
- 测试：`test_upload*` `test_user_files*` `test_user_mgmt*` `test_scan_sync*` `test_sync_failure*` `test_reprocess*` `test_bulk_reprocess*` `test_low_quality_reprocess*` `test_chat_attachments*` `test_import_cycles*`

## Extra angles

- 上传事务、去重、失败补偿
- 路径与文件名消毒（物理路径穿越归 cross-cutting storage，本任务查 API 入参如何变成 storage key）
- 扫描 diff 与 ingest 触发是否漏文件/重复入队

## Regression only

- `user_files` 循环导入（`08-31-break-user-files-import-cycle`）

## Out of Scope

- WebDAV；管线内部解析；存储后端实现

## Acceptance Criteria

- [ ] 五个角度均有结论
- [ ] 上传失败补偿与 scan 漏检有明确结论
- [ ] 循环导入回归结论
- [ ] finding 含 `file:line` + 失败场景
- [ ] 无产品代码改动
