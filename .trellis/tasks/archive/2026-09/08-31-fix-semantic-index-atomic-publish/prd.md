# 语义索引原子发布

父：`08-31-fix-review-highs` 来源：SEARCH-1  
`.trellis/tasks/08-31-review-search/report.md`

## Problem

`_replace_file_index` 三次 `Path.replace`（entries.jsonl → vectors.f32 → manifest.json）。搜索不加写锁。进程在中间被杀，metadata 与向量错位，搜索命中错误文档且会在后续 refresh 固化。

## Requirements

- 发布必须让读者看不到「新 metadata + 旧向量」或反之。
- 加载时若 `len(metadata) != len(vectors)//dim`（或代/校验和不符）则拒绝搜索该索引，不得静默 `min()` 截断当命中。
- 不拆分 `index.py` 模块（A-1 另开）。
- 不改变成功路径的检索结果（同一输入同一命中集合）。

## Acceptance Criteria

- [x] 测试：模拟两次 replace 之间崩溃，随后 search 不返回错位命中（空或 error/degraded，不要错文档）
- [x] 现有 semantic unit 测试绿

## Out of Scope

SEARCH-2 resume、SEARCH-3 index_name、sqlite-vec 强制后端（SEARCH-5）。
