# 全量代码审查

## Goal

对仓库进行一次全量（非增量）代码审查，产出一份可执行的问题报告。本轮**只出报告，不改代码**。

## Scope

- 后端 Python：`src/library/**`（api / services / repositories / db / llm / pipelines / semantic / storage / tasks / agent / cli / utils / vendor）
- 前端：`frontend/src/**`
- 支撑面：`alembic/`、`scripts/`、`tests/`、`openapi/`、`pyproject.toml`、CI 配置
- 排除：`node_modules/`、`.venv/`、`data/`、`frontend/dist/`、根目录 `conversation-*.zip` 等产物

## Review Dimensions（全部覆盖）

1. **正确性**：逻辑缺陷、边界条件、并发/事务、错误处理、资源泄漏
2. **安全**：认证授权、路径穿越、注入、SSRF、密钥硬编码、上传/WebDAV 面、依赖风险
3. **架构与可维护性**：分层越界、重复实现、圈复杂度热点、死代码
4. **规范一致性**：与 `.trellis/spec/` 既有约定、命名/类型/契约（OpenAPI）一致性
5. **测试**：覆盖盲区、脆弱或无断言测试

## Deliverable

`report.md`（任务目录下），结构：
- 概览与统计
- 按严重级分组的问题清单（Critical / High / Medium / Low），每条含：文件:行、问题、失败场景、建议修复
- 后续修复任务拆分建议

## Acceptance Criteria

- [ ] 上述 5 个维度均有明确覆盖结论（含"未发现问题"的显式说明）
- [ ] 每条 finding 可定位到 `file:line`，并给出具体失败场景而非泛化建议
- [ ] 后端与前端两侧均被覆盖，`alembic/`、`scripts/` 至少完成一次扫描级检查
- [ ] 报告写入 `report.md` 并在对话中给出摘要
- [ ] 本轮不产生任何源码改动（`git status` 仅新增任务目录文件）

## Non-Goals

- 不修复问题（修复留作后续子任务）
- 不做性能压测、不做依赖大版本升级
