# 审查：Worker / 任务

父任务：`08-31-feature-code-review`

## Goal

审查任务领取、重试、幂等、启停、tend 的五个角度。只出报告。

## Scope

- `src/library/worker.py`
- `src/library/tasks/runner.py` `enqueue.py` `kinds.py` `usage.py` `maintenance_budget.py`
- `src/library/repositories/tasks.py` `task_outcomes.py`
- `src/library/services/worker_lifecycle.py`
- `src/library/api/routes_tasks.py` `routes_tend.py`
- 通用 handlers：`periodic_tick.py` `prune.py` `purge_deleted_files.py` `recover_stuck_tasks.py` `delete_storage_object.py`
- 测试：`test_worker*` `test_task_*` `test_runner*` `test_tend*` `test_purge*` `test_maintenance*` `test_dispatcher*` `test_lifecycle_switch*` `test_worker_web_toggle*` `test_worker_lifecycle*`

## Extra angles

- CAS 领取、多 worker、fencing
- 启停与默认禁用；GUI toggle 是否真的停掉 runner
- 卡住任务恢复是否误杀仍在跑的任务

## Re-verify still-open

- L-4 `claim_pending_ids` docstring 与真实 CAS 保证

## Out of Scope

- 功能型 handler（ingest / webdav / semantic / mining）归对应功能子任务；本任务只查它们如何被 runner 调度

## Acceptance Criteria

- [ ] 五个角度均有结论
- [ ] 领取/重试/启停/tend 四条路径都有结论
- [ ] L-4 复验
- [ ] finding 含 `file:line` + 失败场景
- [ ] 无产品代码改动
