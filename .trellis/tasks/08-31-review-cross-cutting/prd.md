# 审查：横切

父任务：`08-31-feature-code-review`

## Goal

审查鉴权、存储路径、DB/迁移、全库测试盲区等横切面。只出报告。本任务最后执行，不把功能面子任务已记录的缺陷再计一条。

## Scope

- `src/library/main.py`（中间件顺序、鉴权、Host、CORS、health）
- `src/library/api/http_headers.py` `pagination.py`
- `src/library/storage/`（local / mirror / s3 / sanitize / decompress）
- `src/library/db/session.py` `engine.py` `bootstrap.py` `models/`
- `alembic/` 全部 versions
- `src/library/capacity.py` `model_rate_limit.py` `provider_http.py` `provider_clients.py`
- 测试：`test_cors*` `test_host_allowlist*` `test_migration*` `test_storage*` `test_mirror*` `test_import_cycles*` `test_sqlite_performance*` `test_scale_safety*` `test_openapi_contract.py`（鉴权/契约横切部分）

## Extra angles

- 默认无 token 部署的攻击面（回归 H-2）
- 路径穿越、zip slip、符号链接
- session 回滚契约（复验 M-4）
- 迁移不可逆策略（回归 M-1）
- 全库 skip / 无断言 / 关键路径无测试（只收口功能面没写的）

## Regression only

- H-1 / M-5 CORS
- H-2 Host 白名单
- M-1 迁移 downgrade

## Re-verify still-open

- M-4 `get_session` vs `session_scope`
- L-1 非 ASCII token
- L-2 `/health` 信息
- A-2 `except Exception` 密度（只给全库统计与收口建议，具体吞异常归功能面）

## Out of Scope

- 重复计条功能面已写的 finding；开源选型

## Acceptance Criteria

- [ ] 五个角度均有结论
- [ ] CORS / Host / downgrade 回归
- [ ] M-4 / L-1 / L-2 复验
- [ ] 对 1–10 子任务 `report.md` 做了去重对照（报告中写明引用而非复述）
- [ ] finding 含 `file:line` + 失败场景
- [ ] 无产品代码改动
