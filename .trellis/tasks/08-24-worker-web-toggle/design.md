# Design — 网页端控制任务执行器启停 + 修复默认禁用坑

## 1. 架构总览

现有能力：`config_overlay.json` 是 GUI 可写设置层（白名单 + 原子写 + 启动时 merge）；`TaskRunner` 是任务轮询执行器，但只在 `main.py` lifespan 里按 `worker_enabled` 启动一次、没有全局句柄。

本次改动引入 **`worker_lifecycle` 进程内单例** 作为 TaskRunner 的唯一所有权者，把"持久化意图"（overlay 的 `worker_enabled`）与"运行时实际状态"（`is_running()`）分离，供 API 与 UI 使用。

```
Settings 页开关
   │ PUT /settings/llm {patch:{worker_enabled: v}}
   ▼
config_overlay.py: validate_and_normalize → write_overlay（持久化）
   ▼
routes_settings.update_llm_settings: cache 失效
   ▼
worker_lifecycle.start()/stop()  ──▶ TaskRunner（进程内，运行时启停）
   ▲
GET /settings/server ── worker_running = worker_lifecycle.is_running()
```

## 2. 新增模块：`src/library/services/worker_lifecycle.py`

进程内单例，持有唯一的 `TaskRunner` 实例。

```python
# 模块级单例状态（进程内，单 worker 语义）
_runner: TaskRunner | None = None
_lock: asyncio.Lock | None = None   # 惰性初始化，防并发 toggle

async def start() -> bool:   # 已运行 → False；否则创建+start → True
async def stop() -> bool:    # 未运行 → False；否则 stop 并清空 → True
def is_running() -> bool:    # _runner 存在且其 _loop_task 未结束
```

设计要点：
- **幂等**：重复 start/stop 是 no-op 返回 bool，调用方据此决定是否需要刷新 UI。
- **并发安全**：`asyncio.Lock` 包裹 start/stop，防止 toggle 与 lifespan 竞态。
- **优雅停**：直接复用 `TaskRunner.stop()`（内部 `self._stop.set()` + await 在途任务）。
- **重启语义**：每次 `start()` 都会执行 `TaskRunner.start()` 内的 `_sweep_llm_dependent_if_no_key()`，与后端进程启动行为一致（无 key 时清扫 pending LLM 任务），予以保留。
- **重置**：测试场景需要 `_reset()`（清空 `_runner`/`_lock`）以便隔离。

`main.py` lifespan 改造：
- 启动：`if settings.worker_enabled: await worker_lifecycle.start()`（替换直接 new TaskRunner）。
- 关闭：`finally: await worker_lifecycle.stop()`（无论是否通过网页开过，都能收尾）。

## 3. 持久化：`src/library/services/config_overlay.py`

- `_ALLOWED_FIELDS` 增加 `"worker_enabled"`。
- `validate_and_normalize()` 的 bool 强转元组增加 `"worker_enabled"`（复用现有字符串→bool 语义）。

生效优先级已由现有 merge 逻辑保证：overlay > `.env` > 默认 `true`。

## 4. API：`src/library/api/routes_settings.py`

### 4.1 `GET /settings/server`
返回 dict 增加：
```python
"worker_running": worker_lifecycle.is_running(),
```
紧邻现有 `"worker_enabled": s.worker_enabled`。

### 4.2 `PUT /settings/llm`
在写完 overlay、清缓存之后追加：
```python
if "worker_enabled" in clean:
    desired = bool(clean["worker_enabled"])
    try:
        if desired and not worker_lifecycle.is_running():
            await worker_lifecycle.start()
        elif not desired and worker_lifecycle.is_running():
            await worker_lifecycle.stop()
    except Exception:
        log.exception("worker enable/disable after settings PUT failed")
        payload["worker_error"] = "start/stop failed; see server log"
```
- 设置写失败时同样报 422（沿用现有 validate 路径）。
- **关键约束**：启停异常不得回滚设置写入，也不得让 PUT 整体失败——配置已持久化，仅运行时动作失败，用 `worker_error` 字段上报，前端据此提示"已保存但未生效"。
- 响应 `payload = llm_settings()` 保持不变；运行态由前端后续 `GET /settings/server` 拉取（避免扩大 `LlmSettings` 类型面）。

## 5. 默认值修复

### 5.1 `src/library/cli/init_cmd.py`
`_STARTER_ENV` 中：
```diff
-# Set WORKER_ENABLED=true for development mode (TaskRunner runs in the
-# uvicorn process). Production: keep this false and run `library-worker`
-# as a separate process.
-WORKER_ENABLED=false
+# TaskRunner runs in the uvicorn process by default. Only flip this off
+# when running `library-worker` as a separate process (split deployment).
+WORKER_ENABLED=true
```
同时更新 `init_cmd.py:141` 附近的提示文案（"start the worker" 步骤），注明默认已内置。

Tauri 桌面端 starter env（`desktop/src-tauri/src/lib.rs ensure_starter_env`）不写 `WORKER_ENABLED`，依赖默认 `true`，无需改动。

### 5.2 启动守卫：`src/library/main.py` lifespan
在 `bootstrap_schema()` 之后、决定是否启动 worker 处：
```python
if not settings.worker_enabled:
    pending = await tasks_repo.count_running_and_pending(db)  # 仅 pending 数
    if pending_pending > 0:
        log.warning(
            "worker disabled (WORKER_ENABLED=false) but %d task(s) pending; "
            "enable the worker in Settings or run `library-worker`",
            pending_pending,
        )
```
- 复用 `tasks_repo.count_running_and_pending()` 或在 repositories 增加 `count_pending()`（按需）。守卫仅告警，不阻断启动。
- 桌面路径（`LIBRARY_DESKTOP=1`）同样适用——这就是本次要消除的静默坑。

## 6. 前端：`desktop/`

### 6.1 `desktop/src/types/api.ts`
`ServerSettings` 增加 `worker_running?: boolean`。

### 6.2 `desktop/src/pages/SettingsPage.tsx`
- `ServerBooleanField` 联合类型增加 `"worker_enabled"`。
- `setServerBoolean` 特判：`field === "worker_enabled"` 时，PUT 成功后额外 `await settings.server()` 刷新 `server`（同步 `worker_running` / 权威 `worker_enabled`）；失败回滚。
- Server status 卡片中替换只读 worker 行（现 `SettingsPage.tsx:1181-1184`）为 checkbox + 运行态徽标 + pending 提示。
  - 显示逻辑：勾选 = `server.worker_enabled`；徽标文字 = `server.worker_running ? t.settings.kv.workerRunning : t.settings.kv.workerStopped`；当 `worker_enabled && !worker_running` 时显示 warning 色提示"已配置但未运行（可能启停失败）"。
  - 校验提示：`worker_running === false` 且存在 pending 时显示"任务将不被处理"提示（数据可复用 StatusBar 的 `tasks.runningCount()`）。

### 6.3 i18n（`desktop/src/lib/i18n.ts`，en + zh 两处）
新增：
- `settings.kv.workerRunning` / `settings.kv.workerStopped`
- `settings.workerToggleHint`（拆分部署提示："如另跑 `library-worker` 守护进程请保持关闭，避免重复 worker"）
- `settings.workerNotRunningWarning`（"已启用但执行器未运行"）
- `settings.workerPendingWarning`（"存在 N 个待处理任务"）

## 7. 边界情况

| 场景 | 处理 |
|---|---|
| 无 LLM key 时开启 worker | `TaskRunner.start()` 沿用清扫逻辑：pending LLM 任务置 dead；前端靠 pending/failed 可见。保留现状 |
| 并发 toggle | `worker_lifecycle` 的 Lock 串行化；幂等 |
| 拆分部署 | 网页开关只管进程内 runner；外部 daemon 不受影响；两个 worker 靠 DB claim/lease 协调，安全。UI 文案提示 |
| 重启 | overlay 持久化 `worker_enabled` → 生效优先级 overlay > env > true |
| PUT 启停失败 | 设置已保存，返回 `worker_error`，UI 显示"已保存但未生效"，不阻断 |
| `worker_scheduler_enabled` | 不动，超范围 |

## 8. 兼容性与回滚

- **向后兼容**：已部署实例若 `.env` 里 `WORKER_ENABLED=false` 且 overlay 无该键，行为不变（保持禁用）。默认翻转只影响新建 `library init`。
- **回滚**：overlay 是 JSON 文件，撤掉 whitelist 键 + 生命周期接线即可回滚；无数据迁移。lifespan 接线若回滚需同步还原 `main.py`。

## 9. 关键文件清单

- 新增：`src/library/services/worker_lifecycle.py`
- 修改：`src/library/main.py`、`src/library/services/config_overlay.py`、`src/library/api/routes_settings.py`、`src/library/cli/init_cmd.py`、`src/library/repositories/tasks.py`（如加 count_pending）
- 前端：`desktop/src/types/api.ts`、`desktop/src/pages/SettingsPage.tsx`、`desktop/src/lib/i18n.ts`
- 测试：`tests/test_settings_routes_e2e.py`、`tests/test_worker_e2e.py`、`tests/test_task_runner_concurrency_unit.py`、`tests/test_runner_no_llm_key_e2e.py` 附近
