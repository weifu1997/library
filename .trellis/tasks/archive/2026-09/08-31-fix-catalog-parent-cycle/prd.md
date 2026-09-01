# Catalog parent 环检查

父：`08-31-fix-review-highs` 来源：WEBDAV-H3 + ORG-M1

## Problem

文件夹导入已有 `folders.would_create_cycle`。Catalog 导入直接写 `parent_id`。`soft_delete` 的 `merge_into` 给子节点改 parent 也不查环。

## Requirements

- `repositories/catalogs.py` 提供与 folders 同形的 `would_create_cycle`（一份实现）。
- WebDAV catalog 导入写 parent 前调用；成环则 re-home 到 root、计 conflicts。
- `restructure_catalogs_apply` `_op_move` 与 `_op_soft_delete` 子节点 re-parent 都调用它；成环则拒绝该 op（apply 已有 per-op reject）。
- 无环快照/现有 restructure e2e 行为不变。

## Acceptance Criteria

- [x] 测试：互为父子的 catalog 快照导入后库中无环
- [x] 测试：soft_delete merge_into=孙节点被拒绝或不成环
- [x] `_would_cycle` 私有拷贝删除或改为调用 repo
- [x] webdav + restructure 测试绿

## Out of Scope

AH-1 文件夹（已修）。Agent catalog 读路径 `seen`（agent-chat Low）。
