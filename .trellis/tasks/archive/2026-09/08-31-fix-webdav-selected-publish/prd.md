# 修复选择性 WebDAV 发布

父：`08-31-fix-review-highs` 来源：WEBDAV-H1 + WEBDAV-H2

## Problem

- H1：`scoped=True` 时 `relation_scope = selected_entry_ids`，远端已发布的 E1–E2 关系被丢掉，条目还在。
- H2：`publish_selected` 用 `recover=True`，损坏 latest 变成空快照再发布，远端目录被选中子集覆盖。

## Requirements

- 选择性发布：过滤**本地**关系为两端都在 selected；与**全部远端关系** merge；再保留两端都在 **merged entry ids** 里的关系。
- `publish_selected` 不得 `recover=True`（404 missing 仍可用 `allow_missing`）。损坏 latest 应失败并保留旧 latest，不得空覆盖。
- 空远端 + 首次 selected 发布行为不变（现有 e2e）。
- 不改变 `publish_snapshot` 全量备份（含 sessions）除非为修 H2 必须把 recover 留在全量路径。

## Acceptance Criteria

- [x] e2e：远端已有 E1,E2+R，publish_selected(E3) 后 R 仍在 relations.jsonl
- [x] e2e 或单测：latest 损坏时 publish_selected 失败且不写出空 latest
- [x] `test_publish_selected_scope*` 仍绿

## Out of Scope

WEBDAV-H3 catalog 环（下一子任务）；M1 路径 `..`。
