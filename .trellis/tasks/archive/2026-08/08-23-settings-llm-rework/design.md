# 技术设计：设置界面 LLM 配置重构（服务商预设模板）

> 给目标 AI 的实现技术设计，也是规格可落地性的依据。**前端重构 + 一个小后端改动**（test 端点加 `profile` 参数）。

## 架构与边界

- 前端改动集中在 `desktop/`；后端复用 `GET/PUT /v1/settings/llm`，仅 `POST /v1/settings/llm/test` 增加可选 `profile` 参数以支持"只测默认"（缺省行为不变、向后兼容）。
- 新「快速配置」层 = 服务商预设模板 + 默认 profile 表单；原 `LlmProfileEditor` 折叠进「高级配置」。
- 改动不提交、不并入项目。

## 预设模板数据（前端常量）

新建 `desktop/src/lib/llmPresets.ts`（或 `desktop/src/constants/llmPresets.ts`），导出预设数组：

| id | 名称 | provider | base_url | 推荐 model | dialect |
|---|---|---|---|---|---|
| openai | OpenAI | `openai` | `https://api.openai.com/v1` | gpt-4o-mini | openai |
| anthropic | Anthropic | `anthropic` | `https://api.anthropic.com/v1` | claude-sonnet-5 | anthropic |
| dashscope | 通义千问 (DashScope) | `openai-compatible` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | qwen-plus | openai |
| deepseek | DeepSeek | `openai-compatible` | `https://api.deepseek.com/v1` | deepseek-chat | openai |
| kimi | Kimi (Moonshot) | `openai-compatible` | `https://api.moonshot.cn/v1` | moonshot-v1-8k | openai |
| ollama | Ollama (本地) | `openai-compatible` | `http://127.0.0.1:11434/v1` | qwen2.5 | openai |

字段对齐后端 overlay 键：`llm_default_provider / llm_default_model / llm_default_base_url / llm_default_api_key`。若预设还有进阶能力默认（supports_tools 等），一并放常量并可选写入。

## 前端交互（给目标 AI）

1. **预设选择**：Settings → LLM 配置顶部新增「快速配置」区，一排服务商卡片/下拉。选中后把 `provider / base_url / model` 填入下方表单（不立即保存）。
2. **默认表单**：展示 provider（只读来自预设或可改）、base_url、model、api_key（password + 状态徽章「已配置 ✓ / 未配置」）。api_key 留空=保留原值，有输入=替换。
3. **测试连接**：调用 `POST /v1/settings/llm/test?profile=default`，展示当前 default 的测试结果（ok/error + 实际 model），只发一次探测、跳过 embedding/rerank。
4. **保存**：`PUT /v1/settings/llm`，仅提交 `llm_default_*` 变更（PATCH 语义，`null`=清除覆盖）。成功提示 + 可选「自动重试失败入库」提示（后端返回 `reprocessed_failed` 时）。
5. **高级配置**：原 `LlmProfileEditor` 整体折叠进「高级配置（按用途覆盖默认）」区，默认收起；保留 chat/reflect/ingest/vision 的覆盖能力。

## 复用与改动点

- 新增：`desktop/src/lib/llmPresets.ts`（预设常量）、`desktop/src/components/LlmQuickConfig.tsx`（快速配置区）。
- 修改：`desktop/src/pages/SettingsPage.tsx`（LLM Profiles 区上方插入快速配置，原编辑器折叠）；`desktop/src/lib/i18n.ts`（新增预设/状态/错误文案）；`desktop/src/types/api.ts`（如需补类型）。
- 复用：`settingsApi.llm() / updateLlm() / testLlm()`（`desktop/src/api/client.ts`）、`useI18n`、主题 token、`cn()`。

## 后端（小改：test 端点加 profile 参数）

- **唯一后端改动**：`POST /v1/settings/llm/test`（`routes_settings.py:437` `test_llm_profiles`）增加可选 `profile` 查询参数。
  - `profile` 缺省 → 保持现状（批量探测 chat/reflect/ingest/vision + embedding/rerank，向后兼容）。
  - `profile=default` → 只探测默认配置：用 `s.llm_default_*` 直接构造 LlmProfile 发一次探测，跳过 embedding/rerank；响应为 `{"profiles": {"default": <verdict>}}`，verdict 结构与现有 `_probe_llm_profile` 返回一致（成功 `{ok: true, model, provider, duration_ms}`；失败 `{ok: false, error}`）。
  - **注意**：`default` 不在 `LLM_PROFILES`（`config.py:400` = chat/reflect/ingest/vision/audio），`resolve_profile("default")` 与 `get_chat_client("default")` 都会 raise —— 需特判 default，按 `s.llm_default_*` 构造配置走探测。
- 与后端无关的提示：若某个 preset 的 provider 值不被后端接受（如自定义 provider），预设仅作 `openai-compatible` 映射即可。

## 兼容与回滚

- 后端改动收敛在 test 端点单个可选参数（缺省行为不变），`GET/PUT /v1/settings/llm` 契约不动。
- 改动即弃：验证后不提交。
- 验证命令见 implement.md。

## 权衡

- 为什么"前端为主 + 小后端改动"：overlay + GET/PUT API 已完备，痛点集中在呈现与交互；唯一绕不过的缺口是 test 端点不支持只测默认，故加一个可选 `profile` 参数补齐。
- 为什么保留高级编辑器（折叠）：避免目标 AI 被迫重写复杂覆盖逻辑，控制任务规模；同时保住 power user 能力。
- 为什么预设在前端常量：自包含、无需新增后端接口，目标 AI 一次会话可完成。
