# 网页端控制任务执行器启停 + 修复默认禁用坑

## Goal

让用户可以从设置页（web/桌面 UI）**运行时开启/关闭后台任务执行器（TaskRunner / worker）**，选择持久化并在重启后生效；同时修复"worker 默认被禁用"的静默坑，避免新装用户不手动配置就永远等不到文件分析完成。

背景：当前 `library init` 脚手架默认写入 `WORKER_ENABLED=false`，而 `library serve` 进程内 worker 是否启动完全取决于该开关。只跑 `serve` 不单独跑 `library-worker` 时，所有 ingest / 重建索引等 pending 任务永远无人处理，UI 一直显示"等待中"，且没有任何启动警告。

## Requirements

### R1 运行时启停（核心）
- 新增进程内 worker 生命周期管理器（单例），可随时 `start()` / `stop()` 进程内 TaskRunner，无需重启后端进程。
- `stop()` 必须优雅排空：等待在途任务完成后再停（复用现有 `TaskRunner.stop()` 语义）。

### R2 设置页开关
- 设置页 "Server status" 卡片中，将 worker 由只读显示改为可交互开关。
- 开关应反映并区分两个状态：**配置态**（`worker_enabled`，持久化意图）与**运行态**（`worker_running`，此刻是否真的在跑）。
- 关闭后 UI 仍能显示 pending 任务堆积情况，提示用户原因。

### R3 持久化
- `worker_enabled` 加入 `config_overlay.json` 白名单，可通过现有 `PUT /settings/llm` 路径写入。
- 生效优先级：overlay > `.env` > 默认值 `true`（复用现有 merge 逻辑）。
- 重启后按最后写入的 overlay 值启动 worker。

### R4 后端 API
- `GET /settings/server` 返回新增的 `worker_running`（生命周期实时状态）。
- `PUT /settings/llm` 在 patch 含 `worker_enabled` 时，除写 overlay 外还要触发对应的即时 start/stop；启停异常不得破坏设置写入本身。

### R5 修默认坑
- `library init` 脚手架默认改为 `WORKER_ENABLED=true`（进程内 worker 默认开启），注释说明拆分部署时显式关闭并单独跑 `library-worker`。
- `library serve` 启动时：若 worker 被禁用且 DB 中存在 pending 任务，打印明确的启动警告（提示去设置页开启或运行 `library-worker`）。

### R6 前端文案
- 新增中英双语 i18n：开关、运行态显示、拆分部署提示。

### R7 测试
- 后端：overlay 校验接受 `worker_enabled`；生命周期 start/stop 幂等；init 脚手架默认值；启动守卫告警。
- 前端：`tsc --noEmit` 通过。

## Acceptance Criteria

- [ ] 设置页可开关 worker；开关后 `worker_running` 实时更新，无需刷新页面。
- [ ] 关闭时优雅排空在途任务，pending 任务保留在队列。
- [ ] 开关选择持久化：重启后 worker 按上次选择启动。
- [ ] 全新 `library init` 脚手架为 `WORKER_ENABLED=true`。
- [ ] `library serve` 在 worker 禁用且存在 pending 任务时打印告警。
- [ ] `GET /settings/server` 返回 `worker_running`。
- [ ] 后端测试覆盖 R7 所列场景并通过；前端 `tsc --noEmit` 通过。

## Constraints

- 开关只控制**进程内 runner**。拆分部署（外部 `library-worker` 守护进程）时，网页开关不管理外部进程；UI 文案需说明。两个 worker 并存是安全的（依赖 DB claim/lease 协调）。
- 不暴露任何密钥。
- 保留现有"无 LLM key 时启动即清扫 pending LLM 任务"的语义。
- 不改变 `worker_scheduler_enabled` 等其他配置（超出范围）。

## Notes

- 本任务为复杂任务，配套 `design.md`（技术设计）与 `implement.md`（执行计划）。
- 相关规格：`.trellis/spec/backend/*`、`.trellis/spec/guides/cross-layer-thinking-guide.md`。
