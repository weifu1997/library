# 按功能切片的全量代码审查 — 总报告

- 父任务：`.trellis/tasks/08-31-feature-code-review`
- 日期：2026-08-31
- 分支：`v4.0`
- 本轮**未修改任何产品代码**

11 个子任务均已写出 `report.md` 并通过主会话核对（入库子任务曾漏写文件，已补写；知识库组织子代理误报「无问题」，已由主会话重写）。

---

## 1. 方法与覆盖

每个功能面覆盖正确性 / 安全 / 架构 / 契约 / 测试。已修复项只做回归；上一轮未修项在所属子任务复验。

| # | 子任务 | 报告 |
|---|---|---|
| 1 | Agent / 聊天 / 引用 | `08-31-review-agent-chat/report.md` |
| 2 | 入库与管线 | `08-31-review-ingest-pipelines/report.md` |
| 3 | WebDAV | `08-31-review-webdav/report.md` |
| 4 | 检索 | `08-31-review-search/report.md` |
| 5 | 上传 / 扫描 / 同步 | `08-31-review-upload-scan-sync/report.md` |
| 6 | 知识库组织 | `08-31-review-library-org/report.md` |
| 7 | Worker / 任务 | `08-31-review-worker-tasks/report.md` |
| 8 | 设置与配置 | `08-31-review-settings/report.md` |
| 9 | 接入面 | `08-31-review-access-surfaces/report.md` |
| 10 | 前端其余页 | `08-31-review-frontend-pages/report.md` |
| 11 | 横切 | `08-31-review-cross-cutting/report.md` |

大文件：`runtime.py` 三个主函数、`pdf.py`、`webdav_sync.py` `_import_metadata` / `publish_selected`、`semantic/index.py` 均标明逐行范围。

---

## 2. 上一轮修复 — 回归总表

| ID | 状态 |
|---|---|
| H-1 CORS 顺序 | 仍有效 |
| M-5 CORS origins 可配置 | 仍有效 |
| H-2 Host 白名单 | 仍有效（空 Host 见 CROSS-M1） |
| M-1 迁移 silent pass | 仍有效（schema 变更项 raise） |
| M-2/M-3/L-5/L-6 SSE | 仍有效 |
| A-3 ESLint | 仍有效（31 warning 预算，FE-L2） |
| AH-1 目录环 | 仍有效（catalog 导入是 WEBDAV-H3） |
| AH-2 OCR 部分失败 | 仍有效 |
| coverage UI | 仍有效 |
| user_files 循环导入 | 仍有效 |

仍未修的旧项：M-4（CROSS-L1）、L-1（CROSS-M2）、L-2（CROSS-L2）、L-3（设置）、L-4（WORKER-L1）、AM-1/AM-2（入库）、AL-1/AL-2（Agent）、A-1/A-2。

---

## 3. 去重后的问题清单（本轮新发现 + 仍成立的旧项）

### Critical

无。

### High（建议优先拆修复任务）

| ID | 一句话 | 建议 slug |
|---|---|---|
| **CHAT-H1** | Stop 把 session id 发到 `/conversations/{id}/cancel`，后台 turn 继续跑 | `fix-chat-stop-cancels-conversation` |
| **CHAT-H2** | `user_artifact`（图表/导出）GUI 不渲染 | `fix-chat-user-artifact-ui` |
| **INGEST-H1** | 长 PDF/文本分块索引一块 LLM 失败则整文件失败 | `fix-chunked-index-degrade` |
| **WEBDAV-H1** | `publish_selected` 丢掉远端已有关系 | `fix-webdav-selected-relations-merge` |
| **WEBDAV-H2** | `recover=True` 可把远端覆盖成「仅本次选中」 | `fix-webdav-selected-recover` |
| **WEBDAV-H3** | catalog 导入不查环（文件夹已修） | `fix-webdav-catalog-cycle`（可与 ORG-M1 共用 `catalogs.would_create_cycle`） |
| **SEARCH-1** | 语义索引三文件非原子 replace，搜索无锁，崩溃后向量错位 | `fix-semantic-index-atomic-publish` |
| **UPLOAD-1** | Finder 改文件 `/sync` 不清 `ingested_at`，新摘要写不进去 | `fix-apply-modified-reingest` |
| **ORG-H1** | 软删嵌套文件夹后同名重建 500（unique 含墓碑） | `fix-folder-live-unique-name` |
| **WORKER-H1** | recover 只靠 periodic_tick；tick 崩溃或关调度器则 running 永不恢复 | `fix-recover-stuck-on-runner-start` |

### Medium（第二批）

| 簇 | IDs |
|---|---|
| Agent | CHAT-M1 失败工具仍升级预算；CHAT-M2 SQL 关键字误伤；CHAT-M3 压缩包先整包进内存 |
| 入库 | AM-1 OCR 页数 import 固化；AM-2 每批重解析 PDF；INGEST-M1 git ref 穿越；M2 表格 read 无行帽；M3/M5 coverage 不全；M4 文本层缺页当空白 |
| WebDAV | M1 快照路径 `..`；M2 status 原文含 URL；M3 坏字段整次 pull 回滚 |
| 检索 | SEARCH-2 resume 不能自愈；SEARCH-3 `index_name=..`；SEARCH-4 不兼容索引像「无命中」；SEARCH-5 sqlite-vec 强制后端先 embed 再失败 |
| 上传 | UPLOAD-2 文件夹名与磁盘 sanitize 不一致；UPLOAD-3 文件夹 zip 内存 |
| 组织 | ORG-M1 catalog merge_into 不查环；ORG-M2 删文件不失效 journal |
| Worker | WORKER-M1 GUI 看不到 daemon；WORKER-M2 删 blob TOCTOU |
| 设置 | SET-M1 损坏 overlay + merge 会清空其它覆盖；SET-M2 PUT 可存掩码当密钥 |
| 接入 | ACCESS-M1 eval 写进生产库；ACCESS-M2 MCP/eval 路径无沙箱；ACCESS-M3 导出 zip 内存 |
| 前端 | FE-M1 目录树竞态；FE-M2 metadata 错误被吞 |
| 横切 | CROSS-M1 空 Host 绕过白名单；CROSS-M2 非 ASCII token 500 |

### Low

AL-1/AL-2、A-1 大文件、A-2 199×`except Exception`、L-3 掩码、L-4 docstring、FE-L i18n/ESLint 预算、CROSS-L health 字段等。详见各子报告 §3 Low。不要和 High 捆在一起修。

---

## 4. 建议的修复任务地图（本轮不创建）

按独立可验收、不要把重构和热修捆在一起：

1. `fix-chat-stop-cancels-conversation` — CHAT-H1  
2. `fix-chat-user-artifact-ui` — CHAT-H2  
3. `fix-apply-modified-reingest` — UPLOAD-1  
4. `fix-recover-stuck-on-runner-start` — WORKER-H1  
5. `fix-semantic-index-atomic-publish` — SEARCH-1  
6. `fix-webdav-selected-publish` — H1+H2 同一文件，或拆两条  
7. `fix-catalog-parent-cycle` — WEBDAV-H3 + ORG-M1（抽 `catalogs.would_create_cycle`）  
8. `fix-chunked-index-degrade` — INGEST-H1  
9. `fix-folder-live-unique-name` — ORG-H1（含 Alembic）  
10. `fix-ocr-max-pages-runtime` — AM-1（不要和 AM-2、拆 pdf.py 捆）  
11. 其余 Medium 按子报告 §6 拆，一条缺陷簇一个任务  

内存/zip 流式（UPLOAD-3、ACCESS-M3、CHAT-M3）可共享设计，但验收场景不同，不要做成一个无限 PR。

---

## 5. 验收对照（父任务 PRD）

| 验收项 | 状态 |
|---|---|
| 11 份子报告，五个角度都有结论 | ✅ |
| finding 有 `file:line` + 失败场景 | ✅ |
| Fixed 表均有回归结论 | ✅ |
| 父任务去重 + 修复拆分建议 | ✅ 本文件 |
| 产品路径 `git status` 干净 | ✅ 仅 `.trellis/tasks/*`（及既有 `package-lock.json`） |

---

## 6. 风险与诚实边界

- 没有对 90k 行做「每一行都读」。子报告写了逐行 vs 结构扫描。未逐行的分支不能当成已证明无 bug。
- 前端没有测试运行器；Chat Stop / 目录树竞态只能靠代码阅读。
- `08-27-architecture-audit-open-source-options` 的选型结论未并入本报告。
