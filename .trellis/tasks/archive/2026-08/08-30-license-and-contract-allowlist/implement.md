# Implement

1. License doc edits.
2. `schemas/folders.py`, `schemas/sessions.py`, `schemas/webdav.py` (+ ExtraAllow in `base.py`).
3. Wire `response_model` / error `responses` on the JSON routes.
4. Extend `tests/test_openapi_contract.py` allowlist; keep attachments + folder download untyped.
5. Export OpenAPI, `npm run gen:api`, alias types in `api.ts` + `usage.ts`.
6. `ruff`, contract tests, folder/session/webdav e2e subset, frontend lint.

Rollback: revert the commit; no DB changes.
