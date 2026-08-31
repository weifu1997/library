# 执行 — 设置与配置

遵循父任务 `research/review-protocol.md`。

## Checklist

- [ ] `config.py` 校验与 `config_overlay.py` 合并/持久化
- [ ] `api/routes_settings.py`：GET/PUT、llm test、掩码、错误消毒
- [ ] `llm/factory.py` `model_controls.py` 如何读 profile
- [ ] SettingsPage / LlmProfileEditor / prefs
- [ ] 对应测试盲区
- [ ] 写 `report.md`

## Validation

```bash
git status --short
uv run pytest tests/ -k "settings or config_validation or llm_" --collect-only
```
