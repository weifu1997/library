# 执行计划：产出并验证「LLM 配置重构」基准任务规格

> 本任务交付物 = 可转交给其他 AI 实现的编码评测任务规格（不含功能代码实现）。

## 交付清单（ordered）

- [ ] **1. 规格定稿**：`prd.md`（需求/验收）+ `design.md`（预设表 + 交互设计）已可交付。
- [ ] **2. 便携任务文档**：生成自包含 `llm-settings-rework-task.md`（背景 + 需求 + 预设表 + 验收），可直接拷给目标 AI。
- [ ] **3. 规格可落地性验证**（下述命令）。
- [ ] **4. 与父任务整合**：两份基准任务（仪表盘 + LLM 配置）各自独立可交付，父任务 `prd.md` 记录任务地图与总体验收。

## 验证命令

```bash
# 前后端可跑（复用父任务验证）
curl -s http://127.0.0.1:8000/health
# LLM 相关 API 可用（规格依赖）
curl -s http://127.0.0.1:8000/v1/settings/llm | head -c 400
curl -s http://127.0.0.1:8000/v1/settings/llm/test | head -c 300
# 前端 dev server 通
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5173/
```

> 注意：现有 `POST /v1/settings/llm/test` **无 profile 参数**、响应 `profiles` 无 `default` 键 —— 这正是规格要求目标 AI 补的小后端改动。目标 AI 交付后应验证 `curl -s 'http://127.0.0.1:8000/v1/settings/llm/test?profile=default'` 只发一次探测且响应含 `profiles.default`（规格定稿阶段此命令无法预验，属预期）。

## 关键文件 / 风险点

- `desktop/src/pages/SettingsPage.tsx`：快速配置区插入 + 原编辑器折叠，漏改则入口找不到。
- `desktop/src/lib/i18n.ts`：新文案必须走 i18n，否则中文界面缺字。
- `desktop/src/api/client.ts`：`updateLlm` 的 PATCH 语义（空=清除覆盖、api_key 空=保留）要写进规格，否则目标 AI 会踩坑。
- `desktop/src/types/api.ts` + 后端 `routes_settings.py`：契约锁点，api_key 返回为掩码，永不回传明文。
- 后端 `routes_settings.py:437 test_llm_profiles`：需加 `profile` 参数并特判 `default`（`default` 不在 `LLM_PROFILES`，`resolve_profile` 会 raise）；缺省行为保持批量探测、向后兼容。

## 回滚点

- 本任务为规格编写，不产生产品代码；无代码回滚需求。
- 若目标 AI 实现时发现预设的 provider 值不被接受，以 `routes_settings.py` 的 `_profile_field`/`validate_and_normalize` 为准修订。

## 完成前检查（review gate）

- [ ] 规格自包含，目标 AI 无需追问即可开工。
- [ ] 验收可目视判断（页面上选预设→填 key→测试→保存→状态可见）。
- [ ] 改动不入库说明清晰。
- [ ] 提交最终规划摘要，等用户明确批准后再 `task.py start`。
