# 文件夹 live 唯一名

父：`08-31-fix-review-highs` 来源：ORG-H1

## Problem

`uq_folders_parent_name` 是 `(parent_id, name)` 不含 `deleted_at`。`find_child_by_name` 只看 live。软删嵌套文件夹后再创建同名 → `IntegrityError` → HTTP 500。根目录因 SQLite NULL UNIQUE 语义可能反而成功。

## Requirements

- 软删后，在同一 live 父节点下再创建同名：**要么成功（墓碑不占 unique）要么 409**，**禁止 500**。
- 两个 **live** 兄弟仍不能同名（409）。
- SQLite 与 Postgres 都要成立。
- 推荐：部分唯一索引 `WHERE deleted_at IS NULL`（替换或补充现约束）。若 SQLite 版本不够，创建路径捕获 IntegrityError 映射 409，并在 purge 后允许重建——但优先部分索引。

## Acceptance Criteria

- [x] 测试：软删 nested `/work/Projects` 再 create 同名 → 非 500（成功或 409，PRD 选定后写死一种）
- [x] 测试：两个 live 同名仍 409
- [x] 迁移可升级；不可逆则 `NotImplementedError` 而非 silent pass

## Decision (this planning)

**选定：live 唯一，软删后允许重建同名**（部分 unique）。与「名字占用到 purge」相比更符合 GUI「删了就能再建」。

## Out of Scope

Catalog 同名策略；UPLOAD-2 sanitize。
