# 修复 eval 写库、MCP 路径与导出内存

父：`08-31-fix-review-mediums` 来源：ACCESS-M1+M2+M3

## Requirements

- ACCESS-M1：`eval import-beir` 默认拒绝写入看起来像生产库的 `LIBRARY_HOME`，除非 `--write-library`。
- ACCESS-M2：eval `name` 不得含 `/` `\\` `..`；MCP `destination_path` 必须落在 `$HOME` 下。
- ACCESS-M3：对话 zip 导出限制未压缩总量（413），避免无界 `bytearray`。

## Acceptance Criteria

- [x] `name=../x` 被拒绝
- [x] MCP destination 在 home 外被拒绝
- [x] 无 `--write-library` 且 home 名不含 eval 时 import 拒绝
- [x] 现有 mcp/eval/export 测试绿
