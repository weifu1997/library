# 修复全量审查 High 级问题

## Goal

落实 `.trellis/tasks/08-31-feature-code-review/report.md` 中的 **High** 级缺陷。每个子任务独立可验收。本轮不修 Medium/Low（列在总报告 §3 Medium，另开任务）。

用户价值：Stop 真的停、改文件能再索引、崩溃后任务能恢复、同步/索引不再丢数据或挂死。

## Background

来源：`08-31-feature-code-review` 及其 11 份子报告。证据与失败场景以各审查 `report.md` 为准，本 PRD 不重复设计。

## Requirements

- R1. 只实现下表 High 项；不顺手做 A-1 拆大文件、ESLint 清零、Medium 列表。
- R2. 每个子任务带回归测试，覆盖审查里的失败场景。
- R3. 不改变无缺陷的成功路径输出（ingest 全成功、无环 WebDAV、Stop 之外的聊天）。
- R4. 父任务在 9 个子任务完成后做一次集成：相关 pytest 绿、产品行为与各 PRD 验收一致。

## Task Map

| 顺序 | 子任务 | 来源 | 验收口径 |
|---|---|---|---|
| 1 | `fix-chat-stop-cancels-conversation` | CHAT-H1 | Stop 取消的是 conversation id，后台 turn 停 |
| 2 | `fix-chat-user-artifact-ui` | CHAT-H2 | 图表/CSV 在 Chat 可见 |
| 3 | `fix-apply-modified-reingest` | UPLOAD-1 | Finder 改文件 + sync 后新摘要写入 |
| 4 | `fix-recover-stuck-on-runner-start` | WORKER-H1 | start 时恢复过期 running；关调度器也恢复 |
| 5 | `fix-semantic-index-atomic-publish` | SEARCH-1 | 三文件发布原子或带代校验，错位不可搜索 |
| 6 | `fix-webdav-selected-publish` | WEBDAV-H1+H2 | 选择性发布保留远端关系；损坏 latest 不空覆盖 |
| 7 | `fix-catalog-parent-cycle` | WEBDAV-H3 + ORG-M1 | 导入与 merge_into 不成环 |
| 8 | `fix-chunked-index-degrade` | INGEST-H1 | 单块 LLM 失败仍 `done` + partial |
| 9 | `fix-folder-live-unique-name` | ORG-H1 | 软删后同名不 500 |

## Out of Scope

- Medium/Low（含 AM-1/AM-2、CROSS-M1/M2、SET-M*、FE-M*、ACCESS-M*）
- 拆 `runtime.py` / `pdf.py`（A-1）
- 开源选型任务

## Acceptance Criteria

- [ ] 9 个子任务验收项均勾选
- [ ] 父任务集成：`uv run pytest tests/ -q` 中与上述表面相关的子集全绿；无产品回归测试被跳过当通过
- [ ] 审查 Fixed 表中的旧修复不被这次改动破坏

## Risks

- SEARCH-1 与 WebDAV 发布改动面大，必须有失败注入/崩溃窗口测试。
- ORG-H1 可能要 Alembic；SQLite 部分唯一索引语法要核对。
