# 审查：检索

父任务：`08-31-feature-code-review`

## Goal

审查词法 FTS、semantic index（含 sqlite-vec 开关）、rerank 的五个角度。只出报告。

## Scope

- `src/library/semantic/index.py` `embeddings.py` `rerank.py`
- `src/library/db/fts.py`
- `src/library/api/routes_semantic_index.py`
- `src/library/agent/text_query.py`（检索入口，非 runtime 循环）
- handlers：`rebuild_semantic_index.py` `refresh_semantic_file.py`
- 测试：`test_semantic*` `test_entry_metadata_fts*` `test_search_and_misc*` `test_search_metadata*` `test_gui_search*` `test_eval_ranking*`（仅检索指标相关结论，eval 框架归 access-surfaces）

## Extra angles

- 索引与文件快照一致性、锁、rebuild 中断恢复
- 开关：未装 sqlite-vec / 未开 embedding 时的降级是否可观察
- 查询缓存正确性（脏缓存）

## Out of Scope

- Chat 如何消费检索结果（归 agent-chat）；前端 Search 页 UI（归 frontend-pages，本任务可指出 API 形状）

## Acceptance Criteria

- [ ] 五个角度均有结论
- [ ] `semantic/index.py` 标明哪些函数逐行、哪些结构扫描
- [ ] FTS 与 semantic 两条路径都有结论
- [ ] finding 含 `file:line` + 失败场景
- [ ] 无产品代码改动
