# Host 白名单防 DNS rebinding

父任务：`08-31-full-code-review`
来源：`.trellis/tasks/08-31-full-code-review/report.md` **H-2**

## Problem

默认配置下 `LIBRARY_API_TOKEN` 为空，`optional_bearer_auth`（`main.py`）直接放行；
同时**没有任何 Host 头校验**。

### 失败场景（DNS rebinding）

用户以默认配置在 `127.0.0.1:8000` 运行 Library，然后浏览了恶意页面。
攻击者控制的域名 `evil.com` 先解析到自己的 IP，随后 rebind 到 `127.0.0.1`。
此后浏览器认为 `http://evil.com:8000` 与页面**同源**——CORS 完全不参与——
攻击者脚本可以调用任意端点：下载全部已入库文档、改写 `/v1/settings/llm` 的
`base_url` 把后续 prompt 和已存 API key 转发到攻击者服务器、上传或删除数据。

`main.py:_warn_if_unauthenticated_bind` 的启动警告只覆盖"绑定非回环地址"这一种情况；
**回环 + rebinding 这条路径不在警告范围内**，因为绑定的确实是 127.0.0.1。

## Requirements

- 校验 `Host` 头，非白名单请求直接拒绝，**在任何业务逻辑之前**
- 默认白名单：`localhost` / `127.0.0.1` / `[::1]` + 配置的 `LIBRARY_API_HOST`，
  各自允许带端口
- 提供逃生阀：反代场景下运维必须能显式扩充白名单
- 显式关闭的开关（明确关掉才算数），供确有需要的部署使用
- 探针路径（`/health` `/live` `/ready`）的处理必须与认证中间件一致，
  否则健康检查会因 Host 不匹配而挂掉
- 拒绝响应必须能被浏览器读到（CORS 在最外层，H-1 已保证）
- 不得破坏 CLI（httpx ASGITransport 的 Host 是 `base_url` 的主机名）

## Acceptance Criteria

- [x] 测试：`Host: evil.com` 被拒（4xx），`Host: 127.0.0.1:8000` 通过
- [x] 测试：`LIBRARY_API_HOST` 设为某个地址时，该 Host 自动进入白名单
- [x] 测试：`LIBRARY_TRUSTED_HOSTS` 可显式扩充
- [x] 测试：通配开关打开时任意 Host 放行
- [x] 测试：探针路径不因 Host 被拒（健康检查不能被这道防线打死）
- [x] 测试：中间件位置——必须在 auth 之内、CORS 之外
- [x] 现有 e2e（`base_url="http://t"`）全部仍通过，或明确说明如何兼容
- [x] `.env.example` 记录新设置
- [x] `uv run pytest tests/` 全量通过；`ruff` 通过

## Non-Goals

- 不改认证机制、不强制要求 token
- 不做 IP 层访问控制（那是防火墙的事）


---

## 执行结果（2026-08-31）

| 检查 | 结果 |
|---|---|
| `uv run ruff check src tests` | ✅ |
| `npx tsc -b --noEmit` | ✅ |
| `uv run pytest tests/` 全量 | ✅ **611 passed, 1 skipped**（本任务前 592，新增 19） |

中间件栈（外 → 内）：
`CORSMiddleware → host_allowlist → request_diagnostics → optional_bearer_auth → UploadSizeLimit`

### 先红后绿已验证

把 `trusted` 强制设为 `None`（等价于修复前无 Host 校验）后，19 个测试中 3 个转红：
`test_rebinding_host_is_rejected`、`test_explicit_allowlist_entry_passes`、
`test_rejection_is_readable_by_the_browser`。其余 16 个是辅助函数单测与
"应当放行"的用例，两种状态下都该绿。

### 过程中发现的真实回归风险

启用 Host 校验后全量跑挂了 **63 个测试**，逐一排查后是两类：

1. **e2e 用合成 Host**（`base_url="http://t"` / `"http://test"`）——在 `tests/conftest.py`
   声明 `LIBRARY_TRUSTED_HOSTS=t,test,testserver`。选择在 conftest 声明而不是放宽校验
   或改写 58 处 base_url。
2. **`Host: embedded` 会打断真实 CLI，不只是测试** ——
   `cli/repl.py`、`cli/oneshot.py`、`mcp_server.py` 都用 `http://embedded` 走
   ASGITransport 驱动应用。这些请求根本不经过 socket，不存在 rebinding 风险，
   但确实带着 `Host: embedded`。已加入默认白名单（`EMBEDDED_HOST_NAME`）并注明理由。
   **如果只跑单测不跑全量，这条会直接发布出去把 `library` 命令打死。**

### 一个刻意的取舍

探针路径（`/health` `/live` `/ready`）豁免 Host 校验，与 `optional_bearer_auth` 一致。
代价是 rebinding 攻击者仍能读到 `/health` 的版本号与 `storage_backend`
（父任务报告 L-2 已记录）。理由：编排器常用容器 IP 或 service name 做健康检查，
让存活探针 fail-closed 去换一个版本字符串不值得。
