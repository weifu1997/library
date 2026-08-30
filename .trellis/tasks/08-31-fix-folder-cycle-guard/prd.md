# 修复目录环：`_folder_path` 无限循环与导入路径缺环校验

父任务：`08-31-full-code-review`
来源：`.trellis/tasks/08-31-audit-agent-runtime/report.md` **AH-1**

## Problem

两个缺陷叠加成一个可挂死 worker 的故障：

1. **缺检查**：`services/folders.py:223` 的 `_would_cycle` 只被 `move_folder`(`:351`) 使用。
   WebDAV 导入 `services/webdav_sync.py:1648` 直接写 `row.parent_id`，**不做环校验**。
2. **缺保护**：`services/webdav_sync.py:2431` 的 `_folder_path` 向上遍历 parent 链时
   **没有 `seen` 集合**——同文件其它 4 处 parent 遍历全都有。

### 复现序列

前提：本地已存在 live 目录 A、B；快照含 `A(parent=B)`、`B(parent=A)`（对端互相 reparent 后同步）。

1. `_order_by_parent_chain`(`:2347`) 遇环按"chain order"输出 `B, A`
2. 处理 B：`_nearest_live_folder_id("A")` → A 本地 live → `B.parent = A`，flush
3. 处理 A：`_nearest_live_folder_id("B")` → B live → `A.parent = B`，flush
4. 库中成环。SQLite 自引用 FK 允许成环，逐行 flush 时两行都存在，无约束拦截

此后任意一次 publish 走到 `:1068` 的 `_folder_path` → `cur` 在 A/B 间振荡 →
**协程死循环 + `parts` 无限增长直到 OOM**，任务卡在 `running`，无超时无日志。

## Requirements

- **止血**：`_folder_path` 必须在任何 parent 链上有界终止，成环时返回可用结果而非挂死
- **治本**：导入路径写 `parent_id` 前必须拒绝成环；被拒绝的行 re-home 到 root
- 被拒绝的成环行必须计入既有的 `imported["conflicts"]` 计数并留日志
- 环校验逻辑**复用**已有 `_would_cycle`，不得复制第二份实现
- 不改变无环快照的导入行为（现有 WebDAV 测试全绿）

## Acceptance Criteria

- [ ] 新增回归测试：构造 A/B 互为父子的快照 + 本地已存在 A/B，导入后库中**无环**，`conflicts` 计数增加
- [ ] 新增回归测试：直接在库里写入一个环，`_folder_path` 在有限步内返回（不挂死）
- [ ] `_would_cycle` 只有一份实现
- [ ] `uv run pytest tests/ -k "webdav or folder"` 全绿
- [ ] `uv run ruff check src tests` 全绿
- [ ] 无环快照的导入结果与修复前逐字节一致（用既有测试保证）

## Non-Goals

- 不修 AH-2（OCR），另有子任务
- 不给 folders 表加数据库层的防环约束（SQLite 做不到，且超出本次范围）
