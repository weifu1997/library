# 修复 SSE 重连的误报与资源泄漏

父任务：`08-31-full-code-review`
来源：报告 **M-2** / **M-3** / 审计 **L-5** / **L-6**

## 逐条核实结果

### M-2 — 成立，已修
`chatStream.ts` 在每次瞬时失败时立刻 `opts.onError?.(error)`，然后照常重连。
网络抖动导致首次连接中断 → 界面弹出错误提示 → 250ms 后重连成功、回答完整流出。
用户同时看到"出错了"和一条正确回答，无从判断这轮是否可信。

**修法**：把瞬时失败存入 `lastTransientError`，只在 4 次尝试全部耗尽、真正抛出前
调用一次 `onError`。成功一次即清空。

### M-3 — **不成立，未修**

原始 finding 假设"服务端某类事件不带 `event_cursor`，重连后会被重复 publish"。
实施前逐层核实，**该前提不存在**：

- `routes_chat.py:299` 与 `:493` 两个 SSE 端点**都只经 `_replay_frames`**
- `_replay_frames`（`:453-457`）对每一行都写 `"id": str(row.cursor)`
- 全文件唯一不带 id 的帧是 `:291` 的流前错误，而它是终止事件，本就结束这一轮

也就是说客户端 `if (ev.eventCursor && ...)` 的短路分支在真实流量里走不到。
**没有为一个不存在的问题加去重机制**——那只会增加没有触发条件的代码。

### L-5 — 成立，已修
`reconnectDelay` 的 `{ once: true }` 只在 abort 真正触发时移除监听器；
正常超时路径下监听器永久留在 signal 上。改为超时回调里显式 `removeEventListener`。

### L-6 — 成立，已修
`consumeResponse` 抛出后未取消响应体，被放弃的连接要等 GC。
加 `cancelBody(res)`（吞掉自身异常，绝不掩盖原始错误）。

## Acceptance Criteria

- [x] 瞬时失败不再即时上报；成功重连后不留错误提示
- [x] 最终失败仍然上报且抛出（不吞错）
- [x] `reconnectDelay` 正常路径不残留监听器
- [x] 放弃的响应体被取消
- [x] `npm run lint`（tsc + eslint）通过，0 error
- [x] `npm run build` 通过

## ⚠️ 验证缺口（如实记录）

**前端没有任何测试框架**——`frontend/package.json` 无 `test` 脚本，
无 vitest / jest，全仓库无 `*.test.*` 文件。因此本次行为改动
**没有自动化回归测试**，只有 tsc + eslint + build 与代码审阅。

这是本轮第 5 个出自前端的缺陷（M-2/M-3/L-5/L-6 + coverage 展示），
却依然没有一条前端断言。已另记为后续任务 `frontend-test-runner`。
在那之前，`chatStream.ts` 的重连语义只能靠人工验证。

## Non-Goals

- 不引入 vitest（另开任务）
- 不改服务端 SSE 协议
