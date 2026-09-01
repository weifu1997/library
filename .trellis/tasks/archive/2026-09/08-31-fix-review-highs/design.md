# Design — High 修复父任务

各子任务的技术设计写在自己的 `design.md`（复杂项）或 `prd.md`（轻量项）。父任务只定边界。

## Boundaries

- 父任务不改产品代码。
- 子任务只碰自己 PRD 列出的文件，除非测试必须引用邻层。
- Catalog 环：一个 `repositories/catalogs.would_create_cycle`，WebDAV 导入与 `soft_delete merge_into` 都调用它。不要两份拷贝。
- WebDAV H1 与 H2 同文件 `webdav_sync.py`，放在同一子任务以免互相打架。
- 语义索引原子发布不要顺手拆 `index.py` 模块。

## Compatibility

- 已有 WebDAV/OCR/SSE/Host/CORS 测试必须保持绿。
- 文件夹 unique 若用部分索引，SQLite 与 Postgres 都要覆盖。

## Rollback

每子任务独立；出问题只回滚该子任务的 diff。
