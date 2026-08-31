# 执行计划 — 按功能切片的全量代码审查

父任务本身不审代码。执行单元是子任务。

## 0. Planning gate (this document)

- [x] 父任务与 11 个子任务已创建并链接
- [ ] 用户批准本规划后，对**第一个子任务**执行 `task.py start`（不要 start 父任务）
- [ ] 每个子任务 start 前确认其 `prd.md`、`implement.md`、jsonl 已有真实条目

## 1. Child execution order

按 `prd.md` Task Map 的 1→11。每次只 start 一个子任务。

每个子任务内部：

1. 读父任务 protocol + prior-findings + 本子任务 `prd.md` / `implement.md`
2. 按清单审查，写 `report.md`
3. 跑该子任务的 trellis-check（确认报告完整、无产品改动）
4. 不 archive 到全部集成完成之后也可；但父任务集成前 11 份 `report.md` 必须都在

## 2. Parent integration (after children)

- [ ] 读齐 11 份 `report.md`
- [ ] 去重、校准严重级
- [ ] 写父任务 `report.md`
- [ ] 给出后续修复子任务拆分表（标题、来源 finding ID、建议 slug）
- [ ] 确认产品路径 `git status` 干净

## 3. Validation

```bash
git status --short
# 期望：仅 .trellis/tasks/08-31-feature-code-review 与 11 个 review-* 目录
```

不要跑会改文件的 formatter。子任务如需静态信号，只用只读命令（`ruff check` 不加 `--fix`，`pytest --collect-only` 等）。

## 4. Rollback

只读。误改则 `git checkout -- <file>`。

## 5. What not to do

- 不要 `task.py start 08-31-feature-code-review`，除非将来父任务自己写总报告时需要（届时仍不改产品代码）。
- 不要在审查中途创建修复子任务。
- 不要把 `08-27-architecture-audit-open-source-options` 切进本会话当当前任务。
