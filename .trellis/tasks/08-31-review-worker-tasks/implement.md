# 执行 — Worker / 任务

遵循父任务 `research/review-protocol.md`。

## Checklist

- [ ] `repositories/tasks.py` CAS / dedup（L-4）
- [ ] `tasks/runner.py` `enqueue.py` `worker.py`
- [ ] `services/worker_lifecycle.py` + 前端 toggle 的后端契约（UI 在 Settings，行为在这里）
- [ ] `api/routes_tasks.py` `routes_tend.py`
- [ ] periodic / prune / purge / recover_stuck / delete_storage_object
- [ ] 对应测试盲区
- [ ] 写 `report.md`

## Validation

```bash
git status --short
uv run pytest tests/ -k "worker or task_ or runner or tend or purge or maintenance or lifecycle_switch" --collect-only
```
