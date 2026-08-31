# 执行 — High 修复

不要 `task.py start` 本父任务来写代码。每次 start **一个子任务**，按 Task Map 1→9。

每个子任务：`trellis-before-dev` → 实现 → 该表面测试 → `trellis-check`。

父任务最后：跑相关 pytest 子集，写一句集成结论到本目录（可附在 journal，不必再写 report.md）。

## Validation (integration)

```
uv run pytest tests/ -q -k "chat or ingest or webdav or semantic or sync or folder or worker or catalog or pdf or ocr"
uv run ruff check src tests
npm --prefix frontend run lint
```
