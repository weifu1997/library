# 审查：WebDAV

父任务：`08-31-feature-code-review`

## Goal

审查 WebDAV 同步、导入、冲突处理的五个角度。只出报告。

## Scope

- `src/library/services/webdav_sync.py`
- `src/library/api/routes_webdav_sync.py`
- `src/library/tasks/handlers/webdav_publish.py`
- 测试：`test_webdav*` `test_publish_selected*` `test_mirror*`（仅当与 WebDAV 发布/镜像相关；纯 local mirror 归 cross-cutting storage）

## Extra angles

- 远端快照为不可信输入：路径、parent 链、冲突
- `_import_metadata` / `publish_selected` 必须写明逐行或未逐行
- 与 `folders.would_create_cycle` 的复用（回归 AH-1）

## Regression only

- AH-1 目录环与 `_folder_path`（`08-31-fix-folder-cycle-guard`）

## Out of Scope

- 通用文件夹 API；存储后端 path resolve（可引用 cross-cutting 结论）

## Acceptance Criteria

- [ ] 五个角度均有结论
- [ ] AH-1 回归：导入不再成环，`_folder_path` 有界
- [ ] 冲突计数与 publish 范围有明确结论
- [ ] finding 含 `file:line` + 失败场景
- [ ] 无产品代码改动
