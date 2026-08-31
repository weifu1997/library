# 执行 — 横切

遵循父任务 `research/review-protocol.md`。必须在功能面子报告齐套后执行。

## Checklist

- [ ] 读 1–10 的 `report.md`，列出已覆盖 finding ID，避免重复计条
- [ ] `main.py` 中间件、鉴权、Host、CORS、health（H-1/H-2/M-5/L-1/L-2）
- [ ] `storage/*` 路径穿越、zip slip、S3
- [ ] `db/session.py` `bootstrap.py` `alembic/versions/*`（M-4、M-1）
- [ ] `provider_http.py` SSRF / 超时 / 重试
- [ ] 全库测试 skip、无断言、功能面未认领的盲区
- [ ] 写 `report.md`

## Validation

```bash
git status --short
uv run ruff check src tests scripts
```

只读。
