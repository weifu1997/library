# 执行 — 知识库组织

遵循父任务 `research/review-protocol.md`。

## Checklist

- [ ] folders API/service/repository：move、create、cycle、软删
- [ ] files / file_entries 路由与条目服务
- [ ] tags / relations / journal repositories + mining handlers
- [ ] catalogs / views 重构与 propose
- [ ] recommend / relation_vetting
- [ ] 对应测试盲区
- [ ] 写 `report.md`

## Validation

```bash
git status --short
uv run pytest tests/ -k "folder or entry or tag or relation or journal or catalog or view" --collect-only
```
