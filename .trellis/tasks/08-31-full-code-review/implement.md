# 执行计划 — 全量代码审查

本任务为**只读审查**，产出 `report.md`。不修改任何源码。

## 审查通道（按顺序执行，每通道结束即向 `report.md` 追加发现）

### Pass 0 — 基线与自动化信号
- [ ] 统计规模：`src/library` / `frontend/src` / `tests` 文件数与行数
- [ ] 读取 `pyproject.toml`、`.trellis/spec/*/index.md`，确定既有约定与工具链
- [ ] 运行只读静态检查：`uv run ruff check src tests`（不加 `--fix`）
- [ ] 运行类型检查（若配置）：`uv run mypy src` 或 pyright
- [ ] 前端：`npm run lint`、`npx tsc --noEmit`（若脚本存在）
- 验证：命令输出全部记录，失败/告警条目进入报告"自动化信号"章节

### Pass 1 — 安全面
- [ ] 认证/授权：`src/library/api/**` 全部路由的依赖注入是否一致覆盖
- [ ] 路径处理：`storage/`、上传、WebDAV、`data/library` 路径拼接是否防穿越
- [ ] 注入面：原始 SQL、shell 调用、模板渲染
- [ ] SSRF：`provider_http.py`、`provider_clients.py`、任何用户可控 URL 出站
- [ ] 密钥：硬编码凭据、日志泄漏、错误信息回显
- 验证：每类给出"已检查 + 结论"，有问题的定位到 file:line

### Pass 2 — 后端正确性
- [ ] `services/`、`repositories/`、`db/` 事务边界与会话生命周期
- [ ] `tasks/`、`worker.py` 并发、重试、幂等
- [ ] `llm/`、`pipelines/`、`semantic/` 错误处理与降级路径
- [ ] `capacity.py`、`model_rate_limit.py`、`upload_limits.py` 边界条件
- 验证：每条发现附具体触发输入/状态

### Pass 3 — 架构与可维护性
- [ ] 分层越界（api 直接触 db、repository 里写业务）
- [ ] 重复实现与可复用点
- [ ] 超大文件/函数热点（按行数排序 Top 20）
- [ ] 死代码与未引用导出

### Pass 4 — 前端
- [ ] `frontend/src/api` 与 `openapi/` 契约一致性
- [ ] `hooks/`、`pages/`、`components/` 状态管理、竞态、错误边界
- [ ] i18n 缺失键、可访问性显著问题

### Pass 5 — 支撑面与测试
- [ ] `alembic/versions` 迁移可逆性与顺序
- [ ] `scripts/` 危险操作与参数校验
- [ ] `tests/` 无断言/被跳过/脆弱用例；关键路径覆盖盲区

### Pass 6 — 汇总
- [ ] 去重、按严重级排序、逐条复核（剔除无法给出失败场景的猜测项）
- [ ] 写 `report.md`，给出后续修复子任务拆分建议

## Rollback

只读任务，无回滚需求；若误改文件，`git checkout -- <file>` 复原。
