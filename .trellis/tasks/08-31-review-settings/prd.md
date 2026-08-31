# 审查：设置与配置

父任务：`08-31-feature-code-review`

## Goal

审查 LLM profile、config overlay、设置 API 与前端 Settings 的五个角度。只出报告。

## Scope

- `src/library/services/config_overlay.py`
- `src/library/api/routes_settings.py`
- `src/library/config.py`（与 overlay 的合并/校验）
- `src/library/llm/factory.py` `model_controls.py`（profile 如何被选中）
- `frontend/src/pages/SettingsPage.tsx` `frontend/src/components/LlmProfileEditor.tsx` `frontend/src/lib/prefs.ts`
- 测试：`test_settings*` `test_config*` `test_llm_*` `test_env_example*` `test_model_limits*` `test_provider*`

## Extra angles

- overlay 与环境变量优先级；GUI 保存后哪些项即时生效
- API key 回显/掩码（复验 L-3）
- 前端 `LlmProfileName` 含 `default` 与后端 `defaults` 对象是否漂移

## Re-verify still-open

- L-3 `_mask` 泄漏 key 首 3 尾 2

## Out of Scope

- worker 启停开关的生命周期实现（归 worker；Settings 页上的开关 UI 仍要看）
- CORS/Host 中间件（归 cross-cutting；Settings 若暴露相关配置则记录契约）

## Acceptance Criteria

- [ ] 五个角度均有结论
- [ ] overlay 合并与 LLM test 端点有明确结论
- [ ] L-3 复验；前后端 profile 形状漂移有结论
- [ ] finding 含 `file:line` + 失败场景
- [ ] 无产品代码改动
