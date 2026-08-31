# 执行 — SET-M1/M2

- [x] `read_overlay` 区分 missing vs unreadable；PUT merge 拒绝 unreadable
- [x] `validate_and_normalize` 拒绝含 `***` 的 api_key/password
- [x] 测试（settings e2e 或 overlay unit）
- [x] `uv run pytest tests/ -k "settings or overlay or config_validation" -q`

证据：`config_overlay.py` `read_overlay`；`routes_settings.py` PUT merge；models 已 strip `***`。
