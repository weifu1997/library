# 执行 — 检索

遵循父任务 `research/review-protocol.md`。

## Checklist

- [ ] `db/fts.py` 与 metadata FTS 迁移语义（只读理解，迁移文件本身归 cross-cutting）
- [ ] `semantic/index.py`：锁、manifest、rebuild、search、sqlite-vec 分支
- [ ] `semantic/embeddings.py` `rerank.py`
- [ ] `api/routes_semantic_index.py` `agent/text_query.py`
- [ ] rebuild/refresh handlers
- [ ] 对应测试盲区
- [ ] 写 `report.md`

## Validation

```bash
git status --short
uv run pytest tests/ -k "semantic or fts or search_metadata or gui_search" --collect-only
```
