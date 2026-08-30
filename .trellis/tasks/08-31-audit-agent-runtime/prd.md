# 审计三个大文件

父任务：`08-31-full-code-review`（其 report.md §7 第 6 项）

## Goal

补上全量审查中**未逐行覆盖**的三个最大后端文件的深入审计。只出报告，不改代码。

## Scope

| 文件 | 行数 | 重点函数 |
|---|---:|---|
| `src/library/agent/runtime.py` | 3585 | `_run_execute_phase`(676) / `_dispatch_tool_calls`(663) / `run_turn`(363) |
| `src/library/pipelines/pdf.py` | 2536 | 全文件 |
| `src/library/services/webdav_sync.py` | 2468 | `_import_metadata`(535) / `publish_selected`(229) |

## Review Dimensions

1. 状态机正确性：循环边界、计数器、提前返回、不可达分支
2. 并发：任务池、取消、异常传播、DB 会话生命周期
3. 协议契约：tool_use ↔ tool_result 配对完整性（Anthropic 会硬拒）
4. 资源：文件句柄、临时目录、内存峰值
5. 安全：远端可控输入（WebDAV 快照、PDF 结构）

## Acceptance Criteria

- [ ] 三个文件的重点函数均已逐行阅读，非重点部分至少完成结构+模式扫描
- [ ] 每条 finding 含 `file:line` + 具体失败场景
- [ ] 显式记录"已检查未发现问题"项，避免"没查"被当成"没问题"
- [ ] 结果写入 `report.md`
- [ ] 无源码改动

## Non-Goals

- 不做 A-1 的拆分重构（另开任务）
- 不修复本轮发现的问题
