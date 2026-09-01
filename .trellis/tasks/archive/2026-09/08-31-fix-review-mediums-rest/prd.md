# 修复其余审查 Medium

父：`08-31-fix-review-mediums`

落实总报告 §3 中尚未落地的 Medium：AM-1/AM-2、INGEST-M1–M5、WEBDAV-M1–M3、SEARCH-2–5、UPLOAD-2/3、ORG-M2、WORKER-M1/M2。

Low 只做机械项（docstring、i18n、空 Host 已修之外的小契约）。不拆 `runtime.py` / `pdf.py`（A-1）。

## Acceptance

每个 ID 有回归测试或等价断言。成功路径不改。
