# 不可逆迁移的 downgrade 改为显式失败

父任务：`08-31-full-code-review`
来源：`.trellis/tasks/08-31-full-code-review/report.md` **M-1**

## Problem

7 个迁移的 `downgrade()` 是 `pass`。审计时按"6 个裸 pass"记录，
实施前逐个读过 upgrade 后发现要分两类：

### 类别 A — 改了 schema，静默 pass 是 bug（5 个）

| 迁移 | upgrade 做了什么 | 静默 pass 的后果 |
|---|---|---|
| `0002_additive_columns` | 加列 | 列仍在 |
| `0003_file_entries_folder_id_nullable` | `folder_id` 放宽为可空 | 约束仍是宽的 |
| `0005_sessions_end_reason_check` | 放宽 CHECK | 约束仍是新的 |
| `0012_journal_invalidation` | 加列 | 列仍在 |
| `0014_files_kind_check` | 放宽 CHECK | 约束仍是新的 |

**失败场景**：运维执行 `alembic downgrade 0004`，命令**成功返回**，
`alembic_version` 退到 0004，但 0005 放宽后的 CHECK 仍在库上。
数据库进入"版本号说 0004、实际 schema 是 0005"的漂移状态，无任何提示。
随后重新 `upgrade head` 时 0005 再次执行，在已有约束上二次操作 → 报错或产生不同的表结构。

### 类别 B — 纯数据修复，空 downgrade 是正确的（2 个）

`0004_repair_dangling_file_entries_fks`、`0013_reconcile_dead_ingest_files`
只改数据不改 schema，且修复是幂等的、不可"反修复"。
问题只在于**没有写明这是刻意为之**，读代码的人无法与类别 A 区分。

## Requirements

- 类别 A 的 downgrade 必须**响亮失败**，而不是静默成功
- 失败信息必须说明：为什么不可逆、要真的回滚该怎么做
- 类别 B 保持 no-op，但必须有注释说明"无 schema 变更，故无需回滚"
- 需要一个测试锁定这条策略，防止以后新增迁移又写裸 `pass`
- 不改任何 `upgrade()` 行为；`alembic upgrade head` 结果逐字节不变

## Acceptance Criteria

- [x] 类别 A 的 5 个迁移 `downgrade()` 抛异常，信息含迁移用途与手工回滚指引
- [x] 类别 B 的 2 个迁移保留 `pass` 并有解释性注释
- [x] 测试：遍历 `alembic/versions/*.py`，任何 `downgrade()` 不得是**无注释的裸 pass**
- [x] 测试：类别 A 的 downgrade 确实 raise
- [x] `alembic heads` 仍是单一 head
- [x] `uv run pytest tests/` 全量通过；`ruff` 通过

## Non-Goals

- 不实现真正的逆向迁移（对加列/放宽约束而言意味着数据丢失，不是本任务该替用户做的决定）
- 不改动 `db/bootstrap.py` 里被复用的那些函数


---

## 执行结果（2026-08-31）

| 检查 | 结果 |
|---|---|
| `uv run ruff check src tests alembic` | ✅ |
| `uv run alembic heads` | ✅ 单一 head `0016_scale_safety_indexes` |
| `uv run pytest tests/` 全量 | ✅ **649 passed, 1 skipped**（本任务前 611，新增 38） |

### 先红后绿已验证

`git stash -- alembic` 回到旧迁移后重跑：**17 个转红**
（5 个 `test_irreversible_migrations_raise_with_guidance`，
以及若干 `test_downgrade_is_never_an_undocumented_pass` /
`test_no_op_downgrades_are_data_only_migrations`）。恢复后 38 全绿。

### 对审计结论的修正

报告 M-1 记的是"6 个裸 pass"。实施前逐个读 upgrade 后发现是 **7 个**，且要分两类：
`0004` 和 `0013` 是**纯数据修复、无 schema 变更**，空 downgrade 本身正确，
只是没写明。把它们一并改成 raise 会是错的——那会让一个合法的回滚路径失败。
最终 5 个 raise、2 个保留 no-op 并加注释说明与前者的区别。

### 过程中修掉的一个自造 bug

`test_no_op_downgrades_are_data_only_migrations` 最初用
`[n for n in body if not isinstance(n, ast.Expr)]` 剥离 docstring，
但 `op.execute(...)` / `op.drop_table(...)` 同样是 `ast.Expr`，
导致 7 个**有真实 downgrade 实现**的迁移被误判成 no-op。
改为只剥离首个 docstring 节点。测试自身写错会造出假信号，比没测更糟。
