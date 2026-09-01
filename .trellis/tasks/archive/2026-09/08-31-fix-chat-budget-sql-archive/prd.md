# 修复预算升级、SQL 误伤与压缩包内存

父：`08-31-fix-review-mediums` 来源：CHAT-M1+M2+M3

## Requirements

- CHAT-M1：`successful_new_results` 仅在 `result_ok` 时增加；SSE `ok` 跟 `result_ok`。
- CHAT-M2：`SELECT REPLACE(...)` / `LIKE '%DROP%'` 不被关键字 denylist 误伤。
- CHAT-M3：压缩包在解压前有压缩体积上限。

## Acceptance Criteria

- [x] `{ok: False}` 不升级预算
- [x] `SELECT REPLACE` 与 `LIKE '%DROP%'` 通过校验
- [x] 超大压缩流在 extract 前失败
- [x] 现有 duckdb / chat quick mode 测试绿
