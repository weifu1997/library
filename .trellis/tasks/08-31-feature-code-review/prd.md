# 按功能切片的全量代码审查

## Goal

对 Library 全部产品功能做一次可独立验收的代码审查，每个功能面覆盖正确性、安全、架构、契约、测试五个角度，产出可定位的问题报告。本轮只出报告，不改产品代码。发现的问题在审查完成后再拆修复子任务。

用户价值：上一轮全量审查是扫描级 + 三个大文件精读，随后修了 10 个问题；多数功能面仍未按功能走完。本轮补上那次明确承认的缺口，避免把「没查」当成「没问题」。

## Background

- 仓库是单仓：后端 `src/library/`（FastAPI / SQLAlchemy async / Alembic），前端 `frontend/src/`（React / Vite / TypeScript）。
- 上一轮父任务 `08-31-full-code-review` 及其 10 个修复子任务已归档。扫描结论与三大文件审计见 `research/prior-findings.md`。
- 并行存在的 `08-27-architecture-audit-open-source-options` 做架构选型，不替代本轮按功能的正确性/安全审查；本轮不重复做开源方案调研。
- 工作区在规划时为干净的 `v4.0` 分支。

## Confirmed Facts

- 用户已确认：父任务 + 11 个按功能切片的子任务；每子任务覆盖全部审查角度；本轮只出报告；已修复项只做回归核对、不重复开题。
- 产品功能面与代码落点（规划时核对过目录，不保证行数不变）：

| 子任务 | 主要代码 |
|---|---|
| `08-31-review-ingest-pipelines` | `pipelines/*`（pdf 2611 行、text 1038、pptx 735、docx 651、archive 575、image 524、…）、`tasks/handlers/ingest_file.py` |
| `08-31-review-library-org` | `services/folders.py` `entries.py` `recommend.py` `relation_vetting.py`；`api/routes_folders.py` `routes_file_entries.py` `routes_files.py`；mining/tag/view/catalog handlers |
| `08-31-review-upload-scan-sync` | `services/upload.py` `user_files.py` `scan.py` `sync.py` `reprocess.py`；对应 routes 与 `bulk_reprocess_files` |
| `08-31-review-search` | `semantic/index.py`（1872 行）`embeddings.py` `rerank.py`；`db/fts.py`；`api/routes_semantic_index.py`；rebuild/refresh handlers |
| `08-31-review-agent-chat` | `agent/runtime.py`（3585 行）+ tools + compaction/citations；`api/routes_chat.py` `routes_agent.py`；`frontend/src/pages/ChatPage.tsx` `api/chatStream.ts` |
| `08-31-review-settings` | `services/config_overlay.py`；`api/routes_settings.py`（827 行）；`frontend/src/pages/SettingsPage.tsx`（1717 行）`LlmProfileEditor.tsx` |
| `08-31-review-webdav` | `services/webdav_sync.py`（2500 行）；`api/routes_webdav_sync.py`；`tasks/handlers/webdav_publish.py` |
| `08-31-review-worker-tasks` | `worker.py` `tasks/runner.py` `enqueue.py` `repositories/tasks.py` `services/worker_lifecycle.py`；`api/routes_tasks.py` `routes_tend.py` |
| `08-31-review-access-surfaces` | `mcp_server.py` `cli/*` `eval/*` `services/exports.py` `knowledge_pack.py`；`api/routes_mcp.py` `routes_exports.py` |
| `08-31-review-frontend-pages` | `LibraryPage` `SearchPage` `OverviewPage` 及 `components/library/*`；`frontend/src/api/client.ts` 与 OpenAPI 契约 |
| `08-31-review-cross-cutting` | `main.py` 鉴权/Host/CORS；`storage/*`；`db/session.py` `bootstrap.py` `alembic/`；全库测试盲区收口 |

- 已修复、只做回归的项与仍未修复的旧 finding 清单见 `research/prior-findings.md`。

## Requirements

- R1. 11 个子任务各自产出 `report.md`，覆盖本面全部五个审查角度；未发现问题必须显式写「已检查未发现」。
- R2. 每条 finding 必须有 `file:line`、具体失败场景、建议修复；禁止只有泛化建议。
- R3. 已修复项（`research/prior-findings.md` 的 Fixed 表）只做回归核对：确认修复仍在、原失败场景不再成立。若已回归，标记为 regression 并指向旧 ID，不另开同题新 finding。
- R4. 上一轮未修完的项必须在所属子任务中复验；仍成立则写入该子任务报告。
- R5. 本轮任何子任务与父任务都不得修改产品源码、测试、配置、OpenAPI、前端。允许写入各自任务目录下的 `report.md` 与 `research/`。
- R6. 子任务之间按 `design.md` 的归属规则划分，禁止同一缺陷在两份报告里各算一条新问题；横切子任务最后执行，只收口未被功能面认领的问题。
- R7. 父任务在 11 份子报告齐后做集成：去重、统一严重级、写出总报告 `report.md` 和后续修复子任务拆分建议。父任务本身不审某一功能面的代码。
- R8. 建议的修复子任务只写在报告里，本轮不创建、不实现。

## Task Map

| 顺序 | 子任务 | 独立交付物 | 验收口径 |
|---|---|---|---|
| 1 | `08-31-review-agent-chat` | 该目录 `report.md` | 五个角度 + Chat 前端；SSE 旧修复回归 |
| 2 | `08-31-review-ingest-pipelines` | `report.md` | 各格式管线；OCR 旧修复回归；AM-1/AM-2 复验 |
| 3 | `08-31-review-webdav` | `report.md` | 同步/导入/冲突；目录环旧修复回归 |
| 4 | `08-31-review-search` | `report.md` | FTS + semantic + rerank |
| 5 | `08-31-review-upload-scan-sync` | `report.md` | upload / user files / scan / reprocess；循环导入回归 |
| 6 | `08-31-review-library-org` | `report.md` | 文件夹/条目/标签/关系/journal |
| 7 | `08-31-review-worker-tasks` | `report.md` | 领取/重试/启停/tend |
| 8 | `08-31-review-settings` | `report.md` | overlay / LLM profile / Settings 页 |
| 9 | `08-31-review-access-surfaces` | `report.md` | MCP / CLI / eval / 导出 |
| 10 | `08-31-review-frontend-pages` | `report.md` | Library/Search/Overview + 契约；ESLint 回归 |
| 11 | `08-31-review-cross-cutting` | `report.md` | 鉴权/存储/DB/测试盲区；CORS/Host/downgrade 回归；不与 1–10 重复计条 |
| 12 | 父任务集成 | 本目录 `report.md` | 去重后的总清单 + 修复拆分建议 |

顺序是风险优先建议，不是硬依赖。横切必须在功能面子报告存在后做收口。父任务在全部子任务 `report.md` 齐套后才做集成。

## Out of Scope

- 修改任何产品代码、测试、依赖、CI、OpenAPI、前端。
- 本轮创建或实现修复子任务。
- 性能压测、依赖大版本升级、开源替代选型（归 `08-27-architecture-audit-open-source-options`）。
- 逐行重做已经归档的 10 个修复的设计讨论；只核对结果。
- `node_modules/`、`.venv/`、`data/`、`frontend/dist/`、根目录 `conversation-*.zip`。

## Acceptance Criteria

- [ ] 11 个子任务均有 `report.md`，且五个角度都有结论（含「未发现」）。
- [ ] 每条 finding 可定位到 `file:line` 并带具体失败场景。
- [ ] Fixed 表中的项均有回归结论（仍有效 / 已回归）。
- [ ] 父任务 `report.md` 完成去重与严重级校准，并给出后续修复子任务拆分建议。
- [ ] 本轮 `git status` 的产品路径保持干净；新增文件仅在 `.trellis/tasks/`。

## Risks

- 体量大约 90k+ 行产品代码。子任务必须写明「逐行 / 结构扫描」边界，禁止再把扫描级审查写成全量逐行。
- 功能面与横切可能重复发现同一问题；以先完成的功能面报告为归属，横切只引用。
- `08-27-architecture-audit-open-source-options` 仍为 planning，不要把它的选型结论写进本轮正确性 finding。
