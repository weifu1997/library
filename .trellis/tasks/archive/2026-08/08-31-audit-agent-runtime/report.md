# 三大文件深入审计报告

- 任务：`.trellis/tasks/08-31-audit-agent-runtime`（父：`08-31-full-code-review`）
- 分支：`v4.0` @ `a35f654`
- 本轮**未修改任何源码**

补上父任务 report.md §7 第 6 项标记的缺口。

---

## 覆盖情况

| 文件 | 行数 | 本轮覆盖 |
|---|---:|---|
| `agent/runtime.py` | 3585 | `_run_execute_phase`(2081-2757)、`_dispatch_tool_calls`(2899-3561) 逐行；其余结构扫描 |
| `pipelines/pdf.py` | 2536 | OCR / 渲染 / 资源管理路径逐行；`read_segment` 系列结构扫描 |
| `services/webdav_sync.py` | 2468 | `_import_metadata` 及全部 parent-chain 辅助函数逐行；`publish_selected` 结构扫描 |

---

## 🔴 High

### AH-1 WebDAV 二次导入可造出目录环，随后 `_folder_path` 无限循环
`src/library/services/webdav_sync.py:2431`（无环保护）+ `:1616-1654`（导入写 parent_id 时不做环校验）

`services/folders.py:223` 有一个完整的 `_would_cycle`，`move_folder`(`:351`) 会调用它拒绝成环的移动。
**WebDAV 导入路径完全绕开了这个检查**，直接 `row.parent_id = parent_id`（`:1648`）。

**触发序列**（每一步都可复现）：

1. 快照里含 `A(parent=B)`、`B(parent=A)`，且本地**已存在** A、B 两个 live 目录
   （二次同步的常态：对端做过一次互相 reparent）。
2. `_order_by_parent_chain`(`:2347`) 遇环时按注释"cycles emit in chain order"输出 `B, A`。
3. 处理 B：`_nearest_live_folder_id(session, "A")` → A 本地存在且 live → 返回 `"A"` → **B.parent_id = A**，flush。
4. 处理 A：`_nearest_live_folder_id(session, "B")` → B 存在且 live → 返回 `"B"` → **A.parent_id = B**，flush。
5. 库中 `A.parent = B, B.parent = A`。SQLite 自引用 FK 允许成环，每步 flush 时两行都在，无约束拦截。

之后任意一次 WebDAV publish 走到 `:1068` 的 `await _folder_path(session, entry.folder_id)`：

```python
while cur:                                   # ← 没有 seen 集合
    folder = await session.get(Folder, cur)
    if folder is None or folder.deleted_at is not None: break
    parts.append(folder.name)                # ← 无限增长
    cur = folder.parent_id
```

`cur` 在 A、B 之间永远振荡 → **worker 协程死循环 + `parts` 持续吃内存直到 OOM**。
没有超时、没有日志、任务停在 `running` 状态。

**这个不对称本身就是证据**：同文件里 `_nearest_live_folder_id`(`:2334` `seen`)、
`_order_by_parent_chain`(`:2367` `on_chain`)、`_folder_path_from_export`(`:1567` `seen`)、
`repositories/folders.py:232`（注释明写"guards against parent_id cycles (a corrupt/imported chain)"）
**全部**做了环保护。唯独 `_folder_path` 漏了——作者显然知道环是可能的。

**修复**：① 给 `_folder_path` 加 `seen` 保护（一行，止血）；
② 导入路径复用 `folders_repo` 侧的 `_would_cycle`，成环的行 re-home 到 root 并计入 `conflicts`。
两者都要做——①防挂死，②防脏数据。

---

### AH-2 PDF OCR 逐页失败被静默吞掉，文档以"成功入库"状态缺页
`src/library/pipelines/pdf.py:1795-1798`（吞异常）+ `:263-267`（调用方只判全空）

```python
except Exception as exc:  # noqa: BLE001
    log.warning("OCR call failed for page %d: %s", i + 1, exc)
    return                      # ← out[i] 保持 ""
```

`out[i]` 的 `""` 有**两种完全不同的含义**：该页确实没有文字 / 该页 OCR 调用失败。
调用方只能区分"全部为空"：

```python
ocr_pages_done = sum(1 for t in ocr_text_per_page if t.strip())
if ocr_pages_done == 0:
    raise PdfNeedsOcrError(...)     # 只有 0 页成功才报错
```

**失败场景**：20 页扫描版 PDF，vision provider 在第 5–18 页返回 429（并发 `llm_ingest_concurrency()`
下很容易触发）。这 14 页变成 `""`，`ocr_pages_done = 6 > 0`，文件被标记为**入库成功**。
用户之后检索第 10 页的内容，命中为空——没有报错、没有重试、没有"部分失败"标记，
唯一痕迹是 6 条 `log.warning`。这是**静默数据丢失**，且用户没有任何办法察觉。

同一函数里没有任何重试，而逐页 OCR 恰恰是重试收益最大、最安全（幂等）的地方。

**修复**：把失败页与空白页区分开（`out[i] = None` vs `""`），对失败页做有限退避重试；
仍失败的页计入 `partial_reasons`（该机制在 `:244` 已经存在，用于 `text_page_cap`），
让文件带"OCR 部分失败"状态入库而不是伪装成完整。

---

## 🟠 Medium

### AM-1 `OCR_MAX_PAGES` 在模块导入时求值，GUI 改设置不生效
`src/library/pipelines/pdf.py:90`

```python
OCR_MAX_PAGES: int | None = get_settings().ocr_max_pages   # import 时固化
```

注释说明是为了让测试直接覆盖模块常量。代价是：本项目其它地方（`worker_lifecycle`、
`config_overlay`）都刻意支持**设置页改动即时生效**，唯独 OCR 页数上限需要重启进程。

**失败场景**：用户在设置页把 `OCR_MAX_PAGES` 从 50 调到 500 以处理一本长书，重新触发 ingest，
仍然只 OCR 前 50 页，且**没有任何提示**。用户会认为功能坏了。

**修复**：`_ocr_configured_page_cap()` 改为运行时读 settings（它已经是个函数了，`:1578`），
测试改用 monkeypatch settings 而不是覆盖模块常量。

### AM-2 每批 20 页都重新解析整个 PDF
`src/library/pipelines/pdf.py:1802-1808` → `:1837`

`_render_pdf_pages_to_jpeg` 每次调用都 `pdfium.PdfDocument(pdf_bytes)`。
`OCR_RENDER_BATCH_PAGES = 20`，所以一本 500 页的书要把整个 PDF 结构解析 **25 次**。
分批本身是对的（控制 JPEG 内存峰值），但文档对象应该在批次间复用。

**修复**：把 `PdfDocument` 提到批次循环外，只让**页面渲染**分批。

---

## 🟡 Low

### AL-1 `finish_research` 的 `dup_prior` 分支是死代码
`src/library/agent/runtime.py:3081-3085`

预检阶段 `:3059` 明确排除了 `finish_research`：

```python
if tc.name != "finish_research" and guard.is_duplicate(key):
    statuses.append("dup_prior")
```

因此 `finish_research` **永远不可能**是 `dup_prior` 状态。但同步解析阶段仍写着：

```python
if s == "dup_prior":
    if stats is not None and tc.name == "finish_research":   # ← 不可达
        stats.finish_research_requested = True
```

不是 bug（正常路径由 `:3355-3360` 处理），但会让读者以为 finish_research 的重复调用有去重兜底，
维护时容易据此做错误推断。建议删除，或改成 `assert` 说明不变量。

### AL-2 轮次耗尽的告警打印了错误的数字
`src/library/agent/runtime.py:2741-2742`

循环上界是 `max_total_turns`（`:2154`，含 continuation / 修复 / finalization 配额），
但日志打印的是 `max_execute_turns`（软预算，`:2222` 每轮被重新赋值）：

```python
log.warning("conversation %s hit agent_execute_max_turns=%d", conversation_id, max_execute_turns)
```

排障时看到 "hit agent_execute_max_turns=8" 会去调 execute 预算，而实际耗尽的是总轮次。

### AL-3 `PREMATURE_NO_TOOL_NUDGE` 消耗的轮次未计入总预算
`src/library/agent/runtime.py:2494-2500`、`:2632-2644`

`max_total_turns`(`:2154`) 把 quick 重试、finalization 尝试、malformed 修复都显式加了配额，
唯独 `no_tool_repair_used` 这一轮没加。结果是触发过该修复的会话，实际可用的 execute 轮次比
预算少 1。影响很小，但与该表达式其它项的记账方式不一致。

---

## ✅ 已检查且未发现问题（逐条记录，避免"没查"被当成"没问题"）

**`_dispatch_tool_calls` 的协议完整性 —— 重点验证，结论是正确的。**
我原本怀疑 `fatal_failure`(`:3236`) 会让未启动的调用留下 `placeholders[idx] = None`，
导致 assistant 消息里的 `tool_use` 块数量多于 tool 消息里的 `tool_result` 块，
被 Anthropic 硬拒。实际上 `:3475-3541` 有一段专门的 drain 循环，为每个"因先前失败而未启动"的调用
补一个显式 error 结果，注释写得很清楚。`leader_followers` 的 fan-out 在成功、失败、未启动
三条路径上都完整覆盖。**这块写得很扎实。**

- **完成序 vs 源序的双不变量**（`:2914-2920`）：SSE 按完成序 yield，`result_blocks` 按源序
  append，两者用 `placeholders` 列表解耦，实现与文档一致。
- **doom-loop nudge**（`:3548-3561`）：没有伪造 `tool_use_id`，而是给最后一个真实块追加文本，
  注释说明了为什么不能伪造。正确。
- **任务取消**（`:3465-3469`）：`finally` 里 cancel + `gather(return_exceptions=True)`，
  生成器被提前关闭时不留孤儿任务。
- **pypdfium2 / PIL 资源释放**（`pdf.py:1823-1877`）：page / bitmap / image 三层都用
  `try/finally` + `getattr(x,'close',None)` 释放，嵌套顺序正确，异常路径不泄漏。
- **WebDAV 远端可控输入**：`file_id`/`entry_id` 经 `_is_canonical_uuid`(`:1809`) 强校验——
  这正是 `storage/local.py:20` 注释所依赖的那道防线，确认存在且生效；
  `_sanitize_import_name`(`:2298`) 把 `/`、`\`、控制字符替换掉并拒绝纯点名，
  traversal 无法进入 zip 成员路径或 mirror 磁盘路径。
- **其余所有 parent-chain 遍历**：`_nearest_live_folder_id`(`:2334`)、
  `_order_by_parent_chain`(`:2367`)、`_folder_path_from_export`(`:1567`)、
  `repositories/folders.py:227` 均有环保护。**唯一的漏网之鱼是 AH-1 里的 `_folder_path`。**
- **`_local_row_wins`**(`:2311`)：本地较新编辑 / 本地删除晚于远端，都不会被快照覆盖，
  冲突计入 `imported["conflicts"]`。逻辑正确。
- **compaction 后的消息视图**（`runtime.py:2283-2288`）：`messages[:] = loop_messages`
  让后续轮次在同一压缩视图上追加，避免每轮重新生成不同的隐藏前缀；持久化的会话仍是无损的。
  与 prompt cache 前缀稳定性的诉求一致。
- **finalization 重试终止性**：`finalization_attempts` 在每个 finalizing 轮次开头递增
  (`:2322-2327`)，`request_finalization_retry`(`:2207`) 以此为上界，不会无限重试。

---

## 验收对照

| 验收项 | 状态 |
|---|---|
| 三文件重点函数逐行阅读 | ✅ |
| 每条 finding 含 `file:line` + 失败场景 | ✅ |
| 显式记录"已检查未发现问题" | ✅ 见上节 |
| 结果写入 `report.md` | ✅ |
| 无源码改动 | ✅ |

## 建议的修复子任务

| 优先级 | 子任务 | 内容 |
|---|---|---|
| 1 | `fix-folder-cycle-guard` | AH-1：`_folder_path` 加 seen（止血）+ 导入路径复用 `_would_cycle`（治本） |
| 2 | `fix-ocr-partial-failure` | AH-2：区分失败页与空白页、加重试、走 `partial_reasons` |
| 3 | `fix-ocr-max-pages-live` | AM-1 + AM-2，同文件一次改完 |
| 4 | （并入父任务 A-1 重构） | AL-1 / AL-2 / AL-3 均为 `_run_execute_phase` 拆分时顺手清理 |
