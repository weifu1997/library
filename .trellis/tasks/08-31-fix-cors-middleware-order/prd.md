# 修复 CORS 中间件顺序

父任务：`08-31-full-code-review`
来源：`.trellis/tasks/08-31-full-code-review/report.md` **H-1**（顺带 **M-5**）

## Problem

Starlette 的 `add_middleware` 用 `insert(0, ...)`，**最后注册的在最外层**。
`main.py` 的注册顺序使运行时栈变成：

```
request_diagnostics → optional_bearer_auth → UploadSizeLimitMiddleware → CORSMiddleware → router
```

CORS 在**最内层**，任何在它之前短路返回的响应都不带 `Access-Control-Allow-Origin`。

### 失败场景

设了 `LIBRARY_API_TOKEN`，浏览器 GUI（`localhost:5173`）用过期 token 请求：
`optional_bearer_auth` 返回 401，该响应不经过 CORSMiddleware →
浏览器判定 CORS 失败、`fetch` 直接 reject → 前端 `client.ts` 走 `catch (e)` 打印
"fetch failed"，**永远拿不到 401**，无法提示"令牌无效，请重新登录"。
`UploadSizeLimitMiddleware` 的 413 同理，超大文件上传只得到一个无信息的网络错误。

### 顺带（M-5）

`allow_origins` 硬编码 `http://localhost:5173` / `http://127.0.0.1:5173`。
把 `frontend/dist` 部署到别的端口就全部被 CORS 拒绝，且因 H-1 连错误都读不到，
唯一出路是改源码重新构建。

## Requirements

- CORSMiddleware 必须是**最外层**中间件，短路响应也要带 CORS 头
- 401 / 413 等错误响应对允许来源必须可读
- OPTIONS 预检行为不得回归
- 允许来源可通过环境变量配置，默认保持现有两项（零配置开发不受影响）
- 中间件顺序必须有测试锁定——这个 bug 的本质是"顺序看不出来"，注释挡不住回归

## Acceptance Criteria

- [x] 测试：设了 token 时，带 Origin 的无效 token 请求返回 **401 且响应含
      `access-control-allow-origin`**
- [x] 测试：超限上传返回的 413 同样带 CORS 头
- [x] 测试：中间件栈顺序断言 CORSMiddleware 在最外层（防止再次被挪回去）
- [x] 测试：OPTIONS 预检仍然正常
- [x] 测试：`LIBRARY_CORS_ORIGINS` 可覆盖默认值
- [x] `uv run pytest tests/` 全量通过
- [x] `uv run ruff check src tests` 通过

## Non-Goals

- 不改认证机制本身（H-2 另有子任务）
- 不引入 `allow_credentials=True`（当前用 Bearer 头而非 cookie，无需要）


---

## 执行结果（2026-08-31）

| 检查 | 结果 |
|---|---|
| `uv run ruff check src tests` | ✅ |
| `uv run pytest tests/` 全量 | ✅ **592 passed, 1 skipped**（本任务前 587，新增 5） |

### 先红后绿已验证

把 CORS 挪回最早注册（= 最内层）后，5 个测试中 **3 个转红**：
`test_cors_is_the_outermost_middleware`、`test_invalid_token_401_carries_cors_header`、
`test_upload_too_large_413_carries_cors_header`。413 的失败输出直接显示响应头里
**没有** `access-control-allow-origin`，正是报告描述的现象。

另 2 个两种状态都绿，符合预期：预检（auth 放行 OPTIONS，CORS 在哪都能处理）
和 `_cors_origins` 纯函数单测。

### 过程中的修正

1. 413 测试最初被 `pytest.skip` 跳过（4KB 不足以触发限流）——skip 掉的测试等于没测。
   改为超过 `max_bytes + MULTIPART_NON_FILE_BUDGET` 的原始上限来真正触发。
2. 新增设置触发了 `test_env_example_documents_every_setting`，已在 `.env.example`
   补文档，并写明 CORS **不是安全边界**（它限制别的网页能读什么，不限制直连客户端），
   避免有人误以为配了它就不用 token。
