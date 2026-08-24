# Implement — 网页端控制任务执行器启停 + 修复默认禁用坑

## 执行顺序（按依赖排序）

### Step 1 · worker 生命周期单例（后端核心）
新增 `src/library/services/worker_lifecycle.py`：
- 模块级 `_runner` / `_lock`；`async start()` / `async stop()` / `is_running()` / `_reset()`（测试用）。
- start = `TaskRunner()` + `await runner.start()`；stop = `await runner.stop()`；均幂等、Lock 保护。
- `src/library/main.py` lifespan：`runner = TaskRunner(); await runner.start()` → `await worker_lifecycle.start()`；finally 里 `await worker_lifecycle.stop()`。

**验证**：`pytest tests/test_task_runner_concurrency_unit.py tests/test_runner_no_llm_key_e2e.py -q`

### Step 2 · overlay 持久化 `worker_enabled`
`src/library/services/config_overlay.py`：
- `_ALLOWED_FIELDS` 加 `"worker_enabled"`。
- bool 强转元组加 `"worker_enabled"`。

**验证**：新增/扩展现有 overlay 单测（validate_and_normalize 接受 true/false，拒绝非法时不破坏其他字段）。

### Step 3 · API
`src/library/api/routes_settings.py`：
- `server_settings()` 返回增加 `"worker_running": worker_lifecycle.is_running()`。
- `update_llm_settings()`：`"worker_enabled" in clean` 时按新值调 `worker_lifecycle.start()/stop()`，try/except，失败写入 `payload["worker_error"]`。

**验证**：`pytest tests/test_settings_routes_e2e.py -q`；新增用例：PUT `{worker_enabled:false}` → server 返回 `worker_running:false`；PUT `{worker_enabled:true}` → `worker_running:true`。

### Step 4 · 启动守卫
`src/library/main.py` lifespan：worker 禁用时查询 pending 任务数，>0 则 `log.warning`（含"设置页开启或运行 library-worker"指引）。
- `src/library/repositories/tasks.py`：如需仅 pending 计数，加 `count_pending()`（否则复用 `count_running_and_pending`）。

**验证**：新增单测（守卫在 pending>0 且禁用时产生告警；0 或启用时静默）。

### Step 5 · init 脚手架默认翻转
`src/library/cli/init_cmd.py`：`WORKER_ENABLED=false` → `true`，更新注释与 `init_cmd.py:141` 提示文案。

**验证**：临时目录跑 `python -m library init`，断言 .env 内容含 `WORKER_ENABLED=true`。

### Step 6 · 前端
- `desktop/src/types/api.ts`：`ServerSettings.worker_running?: boolean`。
- `desktop/src/pages/SettingsPage.tsx`：
  - `ServerBooleanField` 加 `"worker_enabled"`。
  - `setServerBoolean` 特判 worker_enabled → PUT 成功后 refetch `settings.server()`。
  - Server status 卡片 worker 行改 checkbox + 运行态徽标 + 未运行/pending 提示。
- `desktop/src/lib/i18n.ts`：en/zh 各新增 workerRunning/workerStopped/workerToggleHint/workerNotRunningWarning/workerPendingWarning。

**验证**：`cd desktop && npm run lint`（tsc -b --noEmit）通过。

### Step 7 · 手工端到端验证
- 临时目录 `python -m library init` + `python -m library serve`（LIBRARY_HOME 指向临时 data），确认启动告警逻辑；用 curl 走 PUT/GET 验证开关 + `worker_running`。
- 打开桌面 dev 前端（`npm run dev`），验证设置页开关即时反映运行态、重启后持久化。
- 回归：确认无 key 场景下开启 worker 仍按既有清扫语义处理 pending 任务。

## 验证命令汇总

```bash
.venv/bin/python -m pytest tests/test_settings_routes_e2e.py tests/test_task_runner_concurrency_unit.py tests/test_runner_no_llm_key_e2e.py -q
cd desktop && npm run lint
```

## 审查门禁（task.py check 前）

1. `worker_lifecycle` start/stop 幂等 + 并发安全（Lock）。
2. PUT 启停失败不破坏设置写入（worker_error 语义）。
3. `GET /settings/server` 含 `worker_running`。
4. init 脚手架默认 `true`；启动守卫存在。
5. 前端 tsc 通过；i18n en/zh 双写。
6. 未改动 `worker_scheduler_enabled` 等其他配置。

## 回滚点

- 每步独立可提交；Step 1/3 回滚即撤 `worker_lifecycle` + 接线 + server 字段；Step 2 撤 whitelist 键；Step 5 撤脚手架默认。overlay 无迁移。
