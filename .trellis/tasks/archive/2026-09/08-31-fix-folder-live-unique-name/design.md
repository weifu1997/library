# Design — ORG-H1

Alembic 新版本：

- 删除 `uq_folders_parent_name`（全表 unique）。
- 创建部分 unique：`(parent_id, name) WHERE deleted_at IS NULL`。
- SQLite：`parent_id IS NULL` 的多行 live 同名仍可能被 SQLite 当成不冲突（NULL≠NULL）。应用层 `find_child_by_name` 已挡 live 根同名；加测试锁住。Postgres 用 `NULLS NOT DISTINCT` 若版本支持，否则同样靠应用层。

`create_folder` / `_find_or_create_child`：仍先查 live；若仍 IntegrityError，映射 `FolderNameConflictError` → 409，永不 500。

bootstrap.py 若维护基线 schema，按项目惯例同步一处，避免只改 Alembic。
