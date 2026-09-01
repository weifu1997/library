# 启动时恢复卡住的任务

父：`08-31-fix-review-highs` 来源：WORKER-H1

## Problem

`recover_stuck_tasks` 只由 `periodic_tick` 派发。`TaskRunner.start` 不跑 recover。bootstrap 把 **running** 的 tick 当成 inflight 而跳过。tick 崩溃在 self-enqueue 之前，或 `WORKER_SCHEDULER_ENABLED=false`，过期 `running` 永不恢复。

## Requirements

- `TaskRunner.start` 在 bootstrap tick **之前**无条件跑 recover（不依赖 LLM key、不依赖 scheduler）。
- bootstrap：lease 已过期的 running tick **不算** inflight。
- 关调度器时，过期 ingest 仍能在 start 时回到 pending。
- 不误杀仍在心跳的 running（现有 lease 比较逻辑保留）。

## Acceptance Criteria

- [x] 测试：running + 过期 lease 的 tick，start 后被恢复或新 tick 能入队
- [x] 测试：scheduler disabled + 过期 ingest_file running，start 后变 pending
- [x] 现有 fencing / dispatcher recover 测试绿

## Out of Scope

WORKER-M1 GUI vs daemon。
