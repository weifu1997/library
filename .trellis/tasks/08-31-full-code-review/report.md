# 全量代码审查报告

- 任务：`.trellis/tasks/08-31-full-code-review`
- 分支：`v4.0` @ `a35f654`
- 日期：2026-08-31
- 本轮**未修改任何源码**

---

## 0. 覆盖范围与方法（先说清楚边界）

| 面 | 规模 |
|---|---|
| 后端 `src/library/**` | 227 个文件 / **68,997 行** |
| 前端 `frontend/src/**` | 47 个文件 / **21,656 行** |
| 测试 `tests/**` | 142 个文件 / 38,254 行 |
| 迁移 `alembic/versions` | 16 个 |

方法：全量自动化检查（lint / typecheck / AST 度量 / 模式扫描覆盖 100% 文件）+ 对高风险模块的人工精读。

**诚实声明**：129k 行代码没有做到逐行人工阅读。自动化信号与模式扫描是全量的；人工精读集中在
`main.py`、`storage/`(local/mirror/sanitize/decompress)、`api/http_headers.py`、`provider_http.py`、
`api/routes_settings.py`、`db/session.py`、`repositories/tasks.py`、`semantic/index.py`、
`agent/tools/query_sql.py`、`frontend/src/api/*`。`agent/runtime.py`(3585 行)、`pipelines/pdf.py`(2536 行)、
`services/webdav_sync.py`(2468 行) 只做了结构与度量层面的检查，**未逐行审计**——见 §7 建议。

---

## 1. 自动化信号（全量）

| 检查 | 结果 |
|---|---|
| `uv run ruff check src tests scripts` | ✅ **All checks passed** |
| `npx tsc -b --noEmit`（前端） | ✅ **exit 0** |
| `alembic heads` | ✅ 单一 head `0016_scale_safety_indexes`，无分叉 |
| `eval(` / `exec(` / `pickle.loads` / `yaml.load` | ✅ 零命中 |
| `subprocess` / `shell=True` / `os.system` | ✅ 无 shell 注入面（仅 `_regex_subprocess` 用于隔离正则回溯） |
| 前端 `any` / `as any` | ✅ **0 处**，且 API 类型由 `openapi-typescript` 生成 |
| 无断言测试 | ✅ 仅 1 例误报（`test_config_validation_unit.py` 用 `pytest.raises`） |

**基线质量高于多数同规模项目**。以下问题是在这个高基线之上找出来的。

---

## 2. 问题清单

### 🔴 High

#### H-1 CORS 中间件被放在最内层，认证失败的响应丢失 CORS 头
`src/library/main.py:229`（CORS 注册）vs `:247`（auth）、`:245`（upload limit）

Starlette `add_middleware` 使用 `insert(0, ...)`，**最后注册的最外层**。运行时实测栈序为：

```
request_diagnostics → optional_bearer_auth → UploadSizeLimitMiddleware → CORSMiddleware → router
```

CORS 在**最内层**，意味着任何在它之前短路返回的响应都不带 `Access-Control-Allow-Origin`。

**失败场景**：设了 `LIBRARY_API_TOKEN`，浏览器 GUI（`localhost:5173`）用过期 token 请求 →
`optional_bearer_auth` 返回 401，该响应不经过 CORSMiddleware → 浏览器判定 CORS 失败，
`fetch` 直接 reject，前端 `_request` 走 `catch (e)` 分支（`client.ts:163`）打印 "fetch failed"，
**永远拿不到 401**，无法提示"令牌无效，请重新登录"。同理，`UploadSizeLimitMiddleware` 返回的 413
也读不到，超大文件上传只会得到一个无信息的网络错误。

**修复**：把 `app.add_middleware(CORSMiddleware, ...)` 移到所有其它中间件**之后**注册（即成为最外层）。

---

#### H-2 无 Host / Origin 校验 —— 默认无令牌部署可被 DNS rebinding 攻破
`src/library/main.py:247` `optional_bearer_auth`

默认 `LIBRARY_API_TOKEN` 为空时中间件直接放行；同时没有任何 `Host` 头白名单。

**失败场景**：用户以默认配置在 `127.0.0.1:8000` 运行 Library，然后浏览了恶意页面。
攻击者控制的域名 `evil.com` 先解析到自己的 IP，随后 rebind 到 `127.0.0.1`。此后浏览器认为
`http://evil.com:8000` 与页面**同源**，CORS 完全不参与——攻击者脚本可以调用任意端点：
下载全部已入库文档、改写 `/v1/settings/llm` 的 `base_url` 把后续 prompt 和已存 API key 转发到
攻击者服务器、上传或删除数据。`main.py:110` 的启动警告只覆盖"绑定非回环地址"这一种情况，
回环 + rebinding 这条路径不在警告范围内。

**修复**：加一条 Host 白名单中间件（默认只允许 `localhost` / `127.0.0.1` / `[::1]` +
`LIBRARY_API_HOST`），非白名单直接 421/403。这对反代部署也只需一个配置项。

---

### 🟠 Medium

#### M-1 6 个迁移的 `downgrade()` 是静默空实现，回滚会造成 schema 漂移
`alembic/versions/0003…:29`、`0004…:27`、`0005…:28`、`0013…:28`、`0014…:27`（以及 `0002`、`0012`，后两者有注释说明是刻意为之）

`0003`（列改可空）、`0005`（加 CHECK 约束）、`0014`（加 CHECK 约束）的 `downgrade` 都是裸 `pass`，
无注释。

**失败场景**：运维执行 `alembic downgrade 0004` 期望回到旧 schema，命令**成功返回**但
`0005` 的 CHECK 约束仍在库上。随后重新 `upgrade head` 时 `0005` 再次尝试创建同名约束 → 报错，
或（SQLite 重建表路径下）产生与 `0002` 迁移不同的列顺序。数据库进入"版本号说是 0004、
实际 schema 是 0005"的漂移状态，且没有任何提示。

**修复**：要么实现真正的 downgrade，要么显式 `raise NotImplementedError("irreversible: …")`
让回滚**响亮地失败**。像 `0002`/`0012` 那样至少写清楚原因。静默 `pass` 是最坏选项。

---

#### M-2 SSE 重连时对每次瞬时失败都回调 `onError`，用户会看到并不存在的错误
`frontend/src/api/chatStream.ts:52-74`

```ts
} catch (error) {
  if (opts.signal?.aborted) throw error;
  opts.onError?.(error);          // ← 每次瞬时中断都上报
}
…
await reconnectDelay(…);           // 然后照常重试
```

**失败场景**：网络抖动导致第一次 SSE 连接中断，`onError` 触发使聊天界面弹出错误提示；
250ms 后重连成功，回答正常流式输出完毕。用户同时看到"出错了"和一条完整正确的回答，
无从判断这轮是否可信。

**修复**：把瞬时失败记入局部变量，只在 4 次尝试全部耗尽、真正抛出前调用一次 `onError`。

---

#### M-3 SSE 断线重连对无 `eventCursor` 的事件不去重
`frontend/src/api/chatStream.ts:97-99`

```ts
if (ev.eventCursor && ev.eventCursor <= cursor) return;   // 无 cursor 的事件直接放行
```

**失败场景**：服务端某类事件（如 `tool_call` 或纯文本 token 帧）未携带 `event_cursor`，
连接在该事件之后断开。重连按 `after_cursor=<上一个有 cursor 的事件>` 拉取，
这批无 cursor 事件被再次下发并再次 `publish` → 聊天区出现重复的工具调用卡片或重复文本段。

**修复**：要求服务端为**所有**事件分配 cursor（在 `routes_chat.py` 侧统一编号），
或在客户端对无 cursor 事件做基于内容哈希的去重。

---

#### M-4 `get_session` 与 `session_scope` 事务语义不一致
`src/library/db/session.py:23-27`

`session_scope`（后台任务用）在异常时显式 `await session.rollback()`；FastAPI 依赖 `get_session`
没有对应处理。实践中 `AsyncSession.close()` 会在归还连接池时回滚，**因此不构成数据泄漏**——
但两条路径的显式契约不同，读代码的人无法一眼确认哪条是安全的。

**修复**：给 `get_session` 加同样的 try/except rollback，或在 docstring 写明"回滚依赖
`async with factory()` 的 close 语义"。这属于 `.trellis/spec/backend/database-guidelines.md`
应当固化的契约。

---

#### M-5 CORS 允许来源硬编码，构建版前端无法跨源部署
`src/library/main.py:231-234`

`allow_origins` 写死 `http://localhost:5173` / `http://127.0.0.1:5173`（Vite dev server）。

**失败场景**：用户把 `frontend/dist` 部署到 nginx 的 `:8080`，后端在 `:8000`。
所有 API 调用被 CORS 拒绝，且因 H-1 连错误信息都读不到。当前唯一出路是改源码重新构建。

**修复**：从 settings 读取 `LIBRARY_CORS_ORIGINS`（默认保留现有两项）。

---

### 🟡 Low

#### L-1 `hmac.compare_digest` 对非 ASCII token 抛 TypeError → 全站 500
`src/library/main.py:259`

`compare_digest` 的 `str` 重载要求两侧都是 ASCII-only。用户若设置了含中文或 emoji 的
`LIBRARY_API_TOKEN`，**每一个**请求在中间件里抛 `TypeError`，返回 500 且无可诊断信息。
修复：在 `config.py` 校验 token 为 ASCII，或先 `.encode()` 再比较。

#### L-2 `/health` 未认证暴露构建与部署信息
`src/library/main.py:330-340`，`PUBLIC_PROBE_PATHS`

`/health` 返回 `git_sha`、`build_id`、`environment`、`storage_backend`。探针端点免认证是合理的，
但 `/live` 已经承担了纯存活探测；`/health` 的这些字段建议在设了 token 时要求认证，
或移到 `/v1/stats`。

#### L-3 `_mask` 泄漏 API key 首 3 尾 2 字符
`src/library/api/routes_settings.py:99-104` — `sk-abc***xy`。对 GUI 回显是常见取舍，
但配合前缀可识别的 key 格式会缩小暴力搜索空间。建议只回显后 4 位。

#### L-4 `claim_pending_ids` 的 docstring 低估了自身安全性
`src/library/repositories/tasks.py:47-50` 写"SQLite 无 FOR UPDATE，因此调用方需保证是唯一 worker"。
实际上 `mark_running`（`:78`）的 `WHERE status == 'pending' … RETURNING` 是一个正确的
compare-and-swap，**即使多 worker 并发也不会重复领取**。当前文档会误导后来者以为存在竞态，
或反过来促使有人去加一个不必要的进程锁。建议改为描述真实保证。

#### L-5 `reconnectDelay` 每次成功计时都残留一个 abort 监听器
`frontend/src/api/chatStream.ts:122-130`。`{ once: true }` 只在 abort 真正触发时移除；
正常超时路径下监听器永久挂在 signal 上。单轮最多 3 个，影响很小，但长会话共享 signal 时会累积。

#### L-6 重连前未取消旧的 response body
`frontend/src/api/chatStream.ts:56-70`。`consumeResponse` 抛出后没有 `res.body?.cancel()`，
底层连接可能延迟释放。

---

## 3. 架构与可维护性

### A-1 超大函数集中在 3 个模块（**主要技术债**）

| 行数 | 位置 | 函数 |
|---:|---|---|
| 676 | `src/library/agent/runtime.py:2081` | `_run_execute_phase` |
| 663 | `src/library/agent/runtime.py:2899` | `_dispatch_tool_calls` |
| 535 | `src/library/services/webdav_sync.py:1576` | `_import_metadata` |
| 363 | `src/library/agent/runtime.py:737` | `run_turn` |
| 349 | `src/library/cli/eval_cmd.py:32` | `cmd_eval_main` |
| 257 | `src/library/semantic/index.py:531` | `_refresh_semantic_index_for_file` |

全库 2080 个函数中 **61 个超过 100 行**。两个近 700 行的函数是本次审查未能逐行覆盖的直接原因——
它们也正是最容易藏 bug 的地方。

### A-2 199 处 `except Exception`，且 `BLE001` 在 ruff 中被全局关闭
`pyproject.toml` 的 lint 配置显式 ignore 了 `BLE001` / `B904` / `E501`，注释说明是"留待单独清理"。
这是被记录过的技术债，但 199 这个量级意味着**异常吞掉后静默降级**的路径很多，
是后续排障时最可能踩坑的区域。建议按模块分批收窄，而不是一次性全清。

### A-3 前端无 ESLint
`frontend/package.json` 的 `lint` 脚本实际是 `tsc -b --noEmit`（只有类型检查）。
React hooks 依赖数组、条件调用 hook、`useEffect` 竞态这类问题**没有任何自动化拦截**，
而 M-2/M-3/L-5/L-6 全部出自流式/副作用代码。建议接入 `eslint` +
`eslint-plugin-react-hooks`。

---

## 4. 明确"已检查且未发现问题"的项

诚实记录，避免把"没查"当成"没问题"：

- **路径穿越**：`storage/local.py:20`、`storage/mirror.py:51` 都用
  `(root / key).resolve()` + `relative_to(root.resolve())` 做兜底；绝对路径 key 会被正确拒绝。
  `mirror.py:187,268` 处理大小写重命名时刻意绕过 `resolve()`，注释清楚，逻辑正确。
- **Zip slip / 压缩炸弹**：`storage/decompress.py` 有预检清单、`..`/绝对路径/盘符检测（`:225`）、
  解压后累计字节上限、`_walk_files:313` 跳过符号链接。这块防护是**教科书级**的。
- **HTTP 头注入**：`api/http_headers.py:25` 用 `quote(name, safe='')` 全量百分号编码，
  CR/LF 无法穿透。
- **SQL 注入**：`db/bootstrap.py` 的 f-string DDL 全部作用于内部常量标识符并经 `_quote_ident`；
  `agent/tools/query_sql.py:479` 的表名是内部生成的 `t1`/`t2`，用户数据一律走 `?` 占位符。
- **密钥泄漏**：全库扫描未发现任何把 api_key / token / password 写入日志或 print 的路径；
  `routes_settings.py:352` 的 `_safe_error` 还会主动从上游错误消息里抹掉 key。
- **事件循环阻塞**：`semantic/index.py:185` 的 `time.sleep` 忙等锁**已**通过
  `asyncio.to_thread`（`:227`）正确隔离，不阻塞事件循环。API 层未发现同步 IO。
- **任务并发**：见 L-4，`mark_running` 的 CAS 保证了不会重复领取。
- **迁移分叉**：单 head，无多头。

---

## 5. 测试

- 141 个测试模块，38k 行，仅 6 处 skip —— 覆盖意愿很强。
- 未发现无断言的空测试。
- **盲区**：`agent/runtime.py` 那两个 ~670 行的函数缺少针对内部分支的单元测试
  （现有覆盖偏 e2e），是 A-1 重构前必须先补的安全网。

---

## 6. 验收对照

| 验收项 | 状态 |
|---|---|
| 5 个维度均有结论（含"未发现问题"显式说明） | ✅ §2 §3 §4 §5 |
| 每条 finding 可定位 `file:line` + 具体失败场景 | ✅ |
| 后端与前端均覆盖，alembic/scripts 完成扫描级检查 | ✅ |
| 报告写入 `report.md` | ✅ |
| 本轮无源码改动 | ✅ |

---

## 7. 建议的后续子任务拆分

| 优先级 | 子任务 | 内容 |
|---|---|---|
| 1 | `fix-cors-middleware-order` | H-1 + M-5，一并把 origins 做成可配置 |
| 2 | `add-host-allowlist` | H-2，含默认值与反代逃生阀 |
| 3 | `fix-chat-stream-resume` | M-2 + M-3 + L-5 + L-6，同一文件一次改完 |
| 4 | `harden-migration-downgrades` | M-1，不可逆迁移改为显式抛错 |
| 5 | `frontend-eslint-baseline` | A-3，接入 react-hooks 规则并清零 |
| 6 | `audit-agent-runtime` | **对 `agent/runtime.py` / `pipelines/pdf.py` / `services/webdav_sync.py` 做本次未完成的逐行审计**，与 A-1 拆分重构合并进行 |

§7 第 6 项需要特别说明：本轮报告**不能**代替对这三个大文件的深入审计。
