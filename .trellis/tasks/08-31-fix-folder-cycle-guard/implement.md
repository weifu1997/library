# 执行计划 — 修复目录环

## 顺序（止血优先，每步独立可验证）

### Step 1 — `_folder_path` 加环保护【止血】
- [x] `services/webdav_sync.py:2431` 按 design.md 决策 2 加 `seen` + `while/else` 告警
- 验证：`uv run pytest tests/ -k webdav`

### Step 2 — 提升 `would_create_cycle` 到仓储层
- [x] `repositories/folders.py` 新增公开 `would_create_cycle(db, *, child_id, new_parent_id)`
      （从 `services/folders.py:223` 原样搬迁，语义不变）
- [x] `services/folders.py` 删除 `_would_cycle`，`move_folder:351` 改调仓储层
- 验证：`uv run pytest tests/ -k folder`（move_folder 的既有环测试必须仍绿）

### Step 3 — 导入路径接入环校验【治本】
- [x] `services/webdav_sync.py:1626` 之后按 design.md 决策 3 插入校验块
- [x] 补 import：`from library.repositories import folders as folders_repo`
- 验证：`uv run pytest tests/ -k webdav`

### Step 4 — 回归测试
- [x] `test_folder_path_survives_cycle`：直接构造成环的 Folder 行，断言 `_folder_path`
      有限步返回且不抛异常
- [x] `test_webdav_import_rejects_folder_cycle`：本地已存在 A、B；快照含 A(parent=B)、
      B(parent=A)；导入后断言 **无环**（沿 parent 链遍历能到根）且 `conflicts` 增加
- 验证：两个新测试均**先红后绿**（先注释掉修复确认能复现）

### Step 5 — 全量校验
- [x] `uv run ruff check src tests`
- [x] `uv run pytest tests/ -k "webdav or folder"`
- [x] `git diff --stat` 确认只动了预期的 3 个文件 + 测试

## 回滚点

每个 Step 都是独立 commit 粒度。Step 1 单独落地即可消除挂死风险，
后续 Step 出问题不影响止血效果。


---

## 执行结果（2026-08-31）

全部 Step 完成。验证记录：

| 检查 | 结果 |
|---|---|
| `uv run ruff check src tests scripts` | ✅ All checks passed |
| `uv run pytest tests/test_webdav_conflict_guard_e2e.py` | ✅ 10 passed |
| `uv run pytest tests/ -k "webdav or folder"` | ✅ 26 passed, 1 skipped |
| `uv run pytest tests/` **全量** | ✅ **575 passed, 1 skipped** |
| `git diff --stat` | ✅ 只动 3 个源文件 + 1 个测试文件 |

### 先红后绿已验证

临时移除两处 guard 后重跑，两个新测试均失败，且**失败模式正是审计预测的**：

- `test_folder_path_survives_existing_cycle` → `asyncio.TimeoutError`
  （10s 超时触发 = 真实的无限循环被复现，不是断言不满足）
- `test_webdav_import_rejects_folder_cycle` → `AssertionError: folder cycle through <uuid>`
  （导入后库中确实成环）

恢复 guard 后全绿。

### 与计划的偏差

1. `design.md` 决策 2 的 `while/else` 方案在实施时被推翻（原因见 design.md 内的修正块）
2. 额外改了 `repositories/folders.py` 的模块 docstring——它原本声明
   "cycle detection 由 service 层负责"，函数搬迁后该描述变成错的
