# 修复 overlay 损坏合并与掩码密钥

父：`08-31-fix-review-mediums` 来源：SET-M1 + SET-M2  
`.trellis/tasks/08-31-review-settings/report.md`

## Problem

- SET-M1：`read_overlay` 在 JSON 损坏时返回 `{}`。merge PUT 从空 dict 起步再 `write_overlay`，其它 overlay 键被抹掉。
- SET-M2：PUT 接受 GET 回显的掩码（含 `***`）当真实 API key。models 端点会丢掉掩码；PUT 不会。

## Requirements

- 损坏 / 非 dict overlay：GET 仍可降级为 `.env`（不砖掉进程）；**merge PUT 必须拒绝**（409 或 422），不得写出只含本次 patch 的文件。
- 缺失 overlay 文件仍视为空，merge PUT 合法。
- `replace: true` 仍整文件替换（不读旧 overlay）。
- `*_api_key` / `*_password` 含 `***` 的写入 → 422，overlay 不变。
- 不改变完好 overlay 的 merge 成功路径。

## Acceptance Criteria

- [x] 测试：损坏 JSON + merge PUT 一字段 → 非 2xx，磁盘仍是损坏原文（或未变成单键 overlay）
- [x] 测试：PUT `llm_default_api_key: "sk-***ab"` → 422，overlay 不变
- [x] 现有 settings / overlay 测试绿

## Out of Scope

SET-L1 改掩码格式；SET-L3 overlay allowlist 扩字段。
