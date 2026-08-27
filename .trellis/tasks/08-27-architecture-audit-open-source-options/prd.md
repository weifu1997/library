# 架构审查与开源方案选型

## Goal

在不改动现有业务代码的前提下，形成一份基于仓库证据和近期可维护开源项目的架构审查与集成选型方案，为后续 v4.0 功能开发提供明确、低风险的实施边界。

## Background

- 后端位于 `src/library/`，目标运行时为 Python ≥3.11，技术栈包含 FastAPI、SQLAlchemy 2 async、aiosqlite/asyncpg、Alembic 和 Pydantic v2。
- 前端位于 `frontend/`，技术栈包含 React 18、Vite、TypeScript、Zustand、React Router v7、Tailwind，并支持中英双语、Markdown/KaTeX/代码高亮。
- 领域能力包含多格式摄取、文件夹/目录/标签/视图/元数据/日志、词法检索、可选嵌入与重排、带引用问答、研究笔记、WebDAV 同步、统计仪表盘、CLI REPL、MCP server 和独立 worker。
- 近期已移除桌面端 Tauri 壳与 Docker 发布链路，并完成依赖瘦身、路由懒加载和设置页 LLM 配置重构。
- 当前分支 `v4.0` 有两个未提交改动：`frontend/src/components/LlmProfileEditor.tsx`、`frontend/src/lib/i18n.ts`；审查期间须保留并单独核对其影响。

## Scope

### In scope

- 梳理后端核心目录和请求数据流，重点核对 `api → services → repositories → db` 分层、异步数据库双轨、错误处理和日志边界。
- 梳理前端 `pages/components/api/hooks` 划分、路由懒加载、状态与后端 schema 的契合度。
- 评估 ingest、citation、settings overlay 等核心能力的稳定性，并识别技术债、职责过重文件、残留桌面端/Docker 引用和前后端 schema 漂移。
- 评估可选语义索引（含 sqlite-vec）开关、SQLite/Postgres 兼容性和继续沿用当前架构的风险。
- 研究可直接集成的 GitHub、PyPI、npm 开源库或参考实现，核对技术兼容性、许可证、近期维护情况、测试/发布信号、传递依赖和集成成本。
- 输出分层决策：继续沿用、适合引入、必须自研；对候选引入项给出 MVP 集成步骤、Alembic/构建/懒加载影响、风险和回滚思路。
- 明确可改动边界：Trellis 托管块、已归档任务产物、markitdown/glowpy fork、以及未提交 LLM 配置改动的处理原则。

### Out of scope

- 在本次审查和选型确认前修改产品代码、数据库 schema、依赖文件或构建配置。
- 替换已经与本地文件树、引用溯源模型、摄取 fork 深度耦合的核心实现，仅评估替代可能性。
- 直接创建 PR、提交代码、发布包或删除历史任务/依赖。
- 选择或实现用户尚未指定的具体“下一步功能”；如需进入实现阶段，应在方案确认后另行冻结 MVP 范围。

## Requirements

- R1. 审查报告必须以仓库中的文件、测试、配置、任务记录或提交历史为证据；发现需标注路径和行号（能确定时）。
- R2. 对每个重点模块给出当前状态（稳定/可接受技术债/高风险）及理由，不只列目录清单。
- R3. 对后端分层、前端分层、跨层 schema、桌面/Docker 残留和异步/语义索引风险给出可执行结论。
- R4. 外部候选方案必须注明项目、版本或检索日期、许可证、维护/测试信号、栈兼容性、依赖风险和预估集成面；不能只凭项目宣传页推荐。
- R5. 方案须区分“整体可替换”“局部可复用”“必须保留自研”，并尊重 MIT 商用/修改约束。
- R6. 最终建议须包含按优先级排序的 MVP 路径、明确不改动项、引入项的迁移/回滚注意事项，以及需要用户确认的决策。
- R7. 研究阶段不得覆盖或合并两个未提交前端文件；须先识别其差异、归属和对审查结论的影响。

## Acceptance Criteria

- [ ] 生成一份完成的架构审查结论，覆盖后端、前端、跨层契约、残留引用、稳定性和主要风险，并含可复核证据。
- [ ] 生成一份开源候选对照，至少覆盖候选的兼容性、许可证、维护/测试、依赖和集成成本，并说明取舍。
- [ ] 形成“沿用 / 引入 / 自研”的分区方案和最小 MVP 集成路径，包含 Alembic、异步数据库、前端懒加载和回滚风险。
- [ ] 明确未提交改动、Trellis 托管内容、历史任务产物和 fork 依赖的可改动边界。
- [ ] `prd.md`、`design.md`、`implement.md` 完成规划收敛；在用户明确批准最终规划前，不执行 `task.py start`，不改产品代码。

## Confirmed Findings (Phase 1 evidence)

### Repository baseline

- The current branch is `v4.0`, based on `origin/v4.0`; the working tree already contains the user-owned edits in `frontend/src/components/LlmProfileEditor.tsx` and `frontend/src/lib/i18n.ts`. The two files pass `git diff --check`; the current frontend typecheck also passes (`npm --prefix frontend run lint`). They are not to be overwritten or folded into this audit.
- `pyproject.toml:1-65` confirms Python `>=3.11`, FastAPI, SQLAlchemy asyncio, aiosqlite/asyncpg, Alembic, Pydantic v2, the two maintained fork dependencies, and an optional `semantic` extra containing `sqlite-vec`.
- `src/library/main.py:224`, `src/library/main.py:317-331` assemble one FastAPI app with 58 OpenAPI paths when imported through `.venv/bin/python`. `.github/workflows/ci.yml:4-8,41-80` runs the backend test tree and frontend build/typecheck; the repository currently has 141 Python test modules.

### Backend boundary assessment

- The intended `api → services → repositories → db` direction is only partially enforced. Repositories do not import API/services, but multiple routes own ORM queries and transactions directly: `src/library/api/routes_stats.py:12-21,28-96`, `src/library/api/routes_files.py:23-39,44-175`, `src/library/api/routes_upload.py:20-40,113-175`, and `src/library/api/routes_folders.py:8-18,94-236`.
- `routes_stats.py` calls the private service helper `_build_folder_display_path`; `routes_agent.py:24-38,287-322` imports private helpers from `agent.runtime`, queries `TaskOutcome` directly, and resolves citation display data in the route. These are the clearest boundary violations and should be extracted incrementally rather than triggering a broad rewrite.
- Stable areas are the ingest registry and format-specific pipelines (covered by `test_pipeline_registry_unit.py`, `test_ingest*.py`, `test_office_pipelines_e2e.py`, `test_pdf*.py`, `test_supplemental_formats_e2e.py`, and fork-specific tests); upload transaction/dedup/compensation (`src/library/services/upload.py` and `test_upload_reliability_unit.py`); citation manifest/locator/transcript replay (`src/library/agent/citation_manifest.py`, `test_agent_citation_manifest.py`, `test_citation*_locator.py`, `test_session_messages*_e2e.py`, `test_session_resume_e2e.py`); and the settings overlay (`src/library/services/config_overlay.py:1-20,30-130`, `test_settings_routes_e2e.py`).
- The main structural risks are oversized mixed-responsibility modules: `agent/runtime.py` (3,585 lines; turn orchestration, tool scheduling, budgets, compaction, citation positioning and persistence), `services/webdav_sync.py` (2,468), `pipelines/pdf.py` (2,536), `semantic/index.py` (1,872), `api/routes_settings.py` (795), and `api/routes_agent.py` (451). Their behavior is well covered in places, but private cross-module calls make future changes high-risk.
- `src/library/db/bootstrap.py:982-1036,1062-1105` maintains a baseline plus 15 post-baseline shims, executes startup DDL, and stamps `alembic_version` to head. SQLite table rebuild/FK handling and a separate Postgres branch are deliberate compatibility work, but runtime bootstrap and Alembic remain two schema authorities. This is a high-risk maintenance seam, not a reason to abandon SQLAlchemy async.
- Semantic indexing has two storage paths and several switches: `src/library/config.py:347-348`, `src/library/semantic/index.py:114-146,493-499,769-775,1248-1271`. It combines embedding calls, file snapshots, manifests, locking, optional sqlite-vec, rebuild and search in one module. The current file index plus sqlite-vec fallback should remain until a measured replacement exists.

### Frontend and contract assessment

- The frontend has a clear current shape (`pages/`, `components/`, `api/`, `lib/`, `types/`) but no separate `stores/` or feature/domain layer; Zustand state is in `lib/chatSession.ts`, `lib/prefs.ts`, and `lib/theme.ts`, and `hooks/` currently contains only `useTemporaryValue.ts`. `frontend/src/api/client.ts` is the central HTTP client, while pages retain substantial local state.
- Route splitting is already in place: `frontend/src/App.tsx:12-31,48-62` lazy-loads Library/Search/Overview/Settings/Help/About, keeps Chat in the landing chunk, and wraps routes in `Suspense`; `frontend/src/main.tsx:1-13` is browser-only `BrowserRouter`. Markdown code blocks and document viewers also use dynamic loading. Avoid adding a global provider or large UI runtime without a measured need.
- Large files mirror the current UI pressure points: `SettingsPage.tsx` (1,717 lines), `LlmProfileEditor.tsx` (1,028), `ChatPage.tsx` (1,019), `i18n.ts` (1,678), and `types/api.ts` (761). This is manageable for the current feature set but will make further page-local API/state growth expensive.
- The backend OpenAPI document is useful for paths and request bodies, but most route responses are annotated as `dict[str, Any]`; generation therefore does not yet prevent response-shape drift. A concrete comparison found `GET /v1/settings/server` returns 93 keys from `src/library/api/routes_settings.py:136-246`, while `ServerSettings` declares 85 keys in `frontend/src/types/api.ts:431-516`. The eight undeclared backend keys are `worker_retry_base_seconds`, `worker_retry_max_seconds`, `maintenance_daily_token_budget`, `relation_background_vetting_enabled`, `agent_cache_slo_min_hit_ratio`, `agent_cache_slo_min_eligible_requests`, `conversation_compaction_enabled`, and `conversation_compaction_reserve_tokens`.
- There is a second LLM contract hazard: `src/library/config.py:436-443` exposes four visible profiles (`chat`, `reflect`, `ingest`, `vision`), while `src/library/api/routes_settings.py:307-331` places `default` in a separate `defaults` object. `frontend/src/types/api.ts:684-731` includes `default` in `LlmProfileName` and the `profiles` record, relying on component special cases. The uncommitted LLM editor currently compiles, but this type should not be treated as proof that the wire shape is exact.

### Desktop/Docker residual audit

- No operational Tauri, Docker, Electron runtime, or release-pipeline reference remains in the shipped source/config paths after semantic exclusions. The remaining matches are intentional: the Unreleased note in `CHANGELOG.md:7-10`, upstream provenance in `scripts/UPSTREAM.md:36`, the transitive `electron-to-chromium` entry in `frontend/package-lock.json`, and domain words such as archive `container`/`analyze_container`. Archived Trellis task documents naturally retain historical terminology and are outside the product boundary.
- The prior removal decisions are documented in `.trellis/tasks/08-25-remove-desktop-app/` and `.trellis/tasks/08-25-remove-docker/`; those archived artifacts are evidence only and must not be rewritten as part of this task.

### External option shortlist (checked 2026-08-27)

- `openapi-ts/openapi-typescript` / npm `openapi-typescript@7.13.0`: MIT, TypeScript 5 peer, GitHub activity through 2026-05-05. It is a development-time generator and adds no browser runtime dependency. Recommended for generated `paths`/component types after response models are added; it does not fix untyped FastAPI responses by itself.
- `openapi-fetch@0.17.0`: MIT, one small helper dependency, same actively maintained monorepo. It is a possible later typed transport, but the existing client has auth/base-url resolution, multipart upload and custom SSE reconnect behavior; do not replace that client wholesale in the MVP.
- `bm25s@0.3.11`: MIT, pure-Python implementation backed by NumPy, PyPI upload 2026-08-25 and GitHub activity the same day. Its synchronous in-memory/file index has no folder/tag filters, transactional updates, or citation identity; use only as an offline benchmark or isolated optional index, not as a replacement for current lexical search.
- `fastembed@0.8.0`: Apache-2.0, PyPI upload 2026-03-23 and GitHub activity through 2026-08-19. It brings ONNX Runtime, tokenizers, Hugging Face/model-cache behavior and a synchronous model API; it is a future local-embedding experiment, not a drop-in for the current remote embedding/file-index contract.
- `sqlite-vec@0.1.9`: PyPI metadata reports MIT/Apache-2.0 and upload 2026-03-31; GitHub activity was observed through 2026-05-18. It is already the optional backend in this repository, so adding another vector store now would duplicate the switch matrix.
- `pgvector@0.5.0`: PyPI upload 2026-07-06 and GitHub activity through 2026-07-06. It is Postgres-specific and would require `CREATE EXTENSION`, vector columns/indexes, Alembic branching and a SQLite fallback; reject for the current dual-backend scope.
- `docling@2.123.0` (MIT, 2026-08-26) and `unstructured@0.27.1` (Apache-2.0, 2026-08-21) are active parser alternatives, but their slim/standard or broad extras pull substantial model/native ecosystems. They also do not preserve this project's local-file-tree identities and citation locators automatically; keep the maintained `markitdown`/`glowpy` forks and existing pipelines as the source of truth.
- `FlashRank@0.2.10` is Apache-2.0 with PyPI upload 2025-01-06 (outside the six-month release window), although its GitHub feed shows activity through 2026-07-11. Its ONNX Runtime/tokenizer dependency footprint and stale package release make it a deferred local-reranker experiment, not an MVP dependency.
- `litellm@1.98.0` is very active (GitHub 2026-08-27) and its non-enterprise code is MIT, but the current package metadata requires `openai>=2.20`, Pydantic settings versions and a large dependency surface. It would take ownership of provider/retry semantics already covered by `llm/`, failover and the overlay; do not introduce it for this audit.
- `@tanstack/react-query@5.102.6` (MIT, React 18/19 peer, GitHub activity through 2026-08-26) is a sound future server-state option, but migrating page-local state and invalidation is broader than the current need and adds runtime weight. Keep it deferred.
- `i18next@26.4.0` plus `react-i18next@17.0.12` are MIT and active (the React binding feed shows 2026-08-20), but replacing the custom typed `i18n.ts` would migrate 1,678 lines and add runtime dependencies without solving the current contract issue. Keep the existing i18n layer.

### Initial recommendation and boundaries

- Continue using the ingest/citation/upload/settings-overlay implementations, native LLM adapters, current lexical search, current semantic file/sqlite-vec implementation, WebDAV model, and browser lazy-loading. Do not alter the two fork dependencies.
- The only low-risk external candidate for the next implementation slice is `openapi-typescript` as a dev-only contract generator, preceded by Pydantic response models for high-value endpoints. `openapi-fetch`, React Query, local embeddings, local reranking, and parser replacements remain explicitly deferred.
- The simplest self-owned MVP path is: (1) add typed response models at the HTTP boundary for settings/stats/search/upload and a documented SSE event union; (2) generate/check frontend types from a reproducible OpenAPI export; (3) extract stats/settings/agent session read models behind repositories/services; (4) make Alembic canonical and reduce bootstrap to explicit development/prepare behavior; (5) split `agent.runtime` and `semantic.index` only along tested seams.
- No Alembic migration is required for `openapi-typescript`; a parser/vector/LLM replacement would require separate adapter and compatibility tests, and a Postgres vector design would require a real migration plus an extension rollout/rollback plan. No such dependency change is authorized before plan approval.
- Do not edit `.trellis/` managed blocks, archived task products, generated/runtime data, `markitdown`/`glowpy` forks, or the two uncommitted LLM files during this audit.

## Open product decision

The current `LlmProfileEditor.tsx` and `i18n.ts` edits should either remain as the user's separate working changes or be explicitly included in a later implementation task. **Recommendation: preserve them as-is and keep them outside this audit**, because they already pass the frontend typecheck and folding them into an architecture audit would mix review baseline with product behavior. Choosing to merge them would require re-baselining the LLM contract findings and adding their intended acceptance criteria; no product code should be changed until that choice is confirmed.
