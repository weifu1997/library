# 修复空 Host 与非 ASCII token

父：`08-31-fix-review-mediums` 来源：CROSS-M1 + CROSS-M2  
`.trellis/tasks/08-31-review-cross-cutting/report.md`

## Problem

- CROSS-M1：`if host and host not in trusted` — 空/缺失 Host 跳过白名单。
- CROSS-M2：`compare_digest` 在非 ASCII `LIBRARY_API_TOKEN` 上 TypeError → 每个鉴权请求 500。

## Requirements

- 白名单启用时，缺失或空 Host → 421（probe 路径仍豁免）。
- 非 ASCII token：启动 ValidationError **或** 鉴权 401，**禁止 500**。
- 正常带 Host 的请求、ASCII token 的 401/200 不变。

## Acceptance Criteria

- [x] 测试：无 Host（或空 Host）→ 421
- [x] 测试：非 ASCII token 不 500
- [x] 现有 host allowlist / CORS 测试绿

## Out of Scope

CROSS-L2 `/health` 字段；CROSS-L3 `0.0.0.0`。
