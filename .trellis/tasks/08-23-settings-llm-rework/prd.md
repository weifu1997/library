# 设置界面 LLM 配置重构（前端 + 小后端改动，供 AI 编码评测用）

## Goal

把 Settings 页的 LLM 配置从"信息过载、继承逻辑隐晦"重构成"普通用户一眼能配好、进阶用户可控"的 UI。交付物为可直接转交其他 AI 实现的功能规格（**不入库**），页面肉眼可见验收。

## 背景（给目标 AI 的最小上下文）

- Library v0.3.6。后端 FastAPI（`library serve` → 127.0.0.1:8000），前端 React + Vite（`desktop/`，`npm run dev` → 127.0.0.1:5173，`/v1` 代理到后端）。
- LLM 配置在 **Settings → LLM Profiles**，当前实现：`desktop/src/components/LlmProfileEditor.tsx` + `desktop/src/pages/SettingsPage.tsx`。
- 后端 API 已完备且**大部分可复用**：`GET /v1/settings/llm`（读取各 profile，api_key 掩码 + `api_key_set` 标记）、`PUT /v1/settings/llm`（PATCH 语义写 overlay：`null`=清除覆盖回落到 .env/默认）、`POST /v1/settings/llm/test`（测试连接）。**唯一缺口**：test 端点无参数、永远批量探测 `LLM_PROFILES_VISIBLE`（chat/reflect/ingest/vision）+ embedding/rerank，响应 `profiles` 无 `default` 键，无法"只测默认"。因此本任务 = **前端重构 + 一个小后端改动**（给 test 端点加可选 `profile` 参数，见 design.md）。

## 已确认事实（现状 UX 分析，基于代码）

- **5 个 profile 平铺**：`default / chat / reflect / ingest / vision`，每行是一个 accordion（`LlmProfileEditor.tsx:23` `PROFILES`）。
- **每行展开 11 个字段**：provider、model、base_url、api_key + 进阶能力 dialect、context_window、tokenizer、supports_vision、supports_tools、supports_temperature、token_limit_param（`EDITABLE_FIELDS`，L24-28）。
- **覆盖/继承语义隐晦**（L168-206、L216-223）：输入框为空 = 继承（placeholder 显示 fromEnv/inherited）；保存时空值发 `null` = 清除该覆盖；api_key 留空 = 保留原值。普通用户很难理解为何同是"空"，行为却不同。
- **api_key 无清晰状态**：password 输入，placeholder 显示掩码（`sk-***`），仅靠 `api_key_set` 布尔判断，用户无法直观确认"已配置/未配置/配的是哪个服务商"。
- **测试连接一次测全部**：`testLlm()` 返回所有 profiles + embedding + rerank 的批量结果（L44-59），结果一大片，难以定位。
- **provider 仅 3 个硬编码选项**（openai / openai-compatible / anthropic，L308-310），无常用服务商预设（如 DashScope 通义、Ollama 本地、DeepSeek、Kimi 等）。
- **多数用户实际只需配一个 default**，chat/reflect/ingest/vision 继承即可；当前把 5 个 profile 平等摊开，逼用户理解每个。
- 后端 overlay 机制本身可用（`routes_settings.py:527 PUT`），问题集中在**前端呈现与交互**。
- **test 端点无法只测默认**：`POST /v1/settings/llm/test`（`routes_settings.py:437`）无请求参数，循环 `LLM_PROFILES_VISIBLE`（不含 default）+ 并行探测 embedding/rerank，响应 `profiles` 无 `default` 键；且 `default` 不在 `LLM_PROFILES`（`config.py:400`），`resolve_profile("default")` 会 raise。

## 需求（UX 方向：服务商预设模板）

- **R1 预设模板**：内置 ≥6 个服务商预设（OpenAI、Anthropic、通义千问/DashScope、DeepSeek、Kimi、Ollama 本地），前端常量集中管理（见 design.md 预设表）；选中预设**自动填充** provider / base_url / 推荐 model 到默认表单。
- **R2 默认配置表单**：预设区下方，展示/编辑 provider / base_url / model / api_key；api_key 密码输入 + 清晰的「已配置 ✓ / 未配置」状态徽章；留空=保留原值、有输入=替换。
- **R3 测试连接**：调用 `POST /v1/settings/llm/test?profile=default`（**需要后端小改**：test 端点加可选 `profile` 参数，`profile=default` 时只探测默认配置、跳过 embedding/rerank，响应含 `profiles.default`），前端只展示默认 profile 的测试结果（成功→实际 model；失败→错误信息），不批量测全部。
- **R4 保存**：`PUT /v1/settings/llm`（PATCH 语义，`null`=清除覆盖、api_key 空=保留），仅提交 default profile 变更；保存成功提示 + 可选「自动重试失败入库」提示（后端返回 `reprocessed_failed` 时）。
- **R5 高级配置折叠**：原 `LlmProfileEditor`（chat/reflect/ingest/vision 覆盖）折叠进「高级配置（按用途覆盖默认）」区，默认收起，保留 power user 能力。
- **R6 状态与文案**：loading / 空态 / 错误态（可重试）；全部新增文案走 i18n（`desktop/src/lib/i18n.ts`）。
- **R7 样式对齐**：主题 token（`desktop/src/styles/globals.css`）+ 现有组件风格。
- **R8 不入库**：改动不提交、不并入项目。

## 非目标

- 不改动后端 `GET/PUT /v1/settings/llm` 契约；后端改动仅限 `POST /v1/settings/llm/test` 增加可选 `profile` 参数（缺省行为保持批量探测、向后兼容）。
- 不把改动并入项目 / 不提交。
- 不做与评测无关的完整产品打磨。

## 验收标准（目视）

- [ ] 打开 Settings → LLM 配置，顶部出现「快速配置」预设区，可见 ≥6 个服务商预设。
- [ ] 选中任一预设，provider / base_url / 推荐 model 自动填充到默认表单。
- [ ] api_key 有「已配置 ✓ / 未配置」清晰状态徽章；留空保存不覆盖原 key。
- [ ] 测试连接只测默认配置（`?profile=default` 只发一次探测，响应含 `profiles.default`）：成功显示实际 model、失败显示错误信息。
- [ ] 保存后刷新仍生效（overlay 持久化），并显示保存成功。
- [ ] 高级配置（chat/reflect/ingest/vision）折叠可见、可展开覆盖。
- [ ] 页面肉眼可见改造效果（截图可验收）。
- [ ] 改动不入库（git status 干净或仅未跟踪改动）。

## 开放问题

- 无（已收敛：UX 方向 = 服务商预设模板）。
