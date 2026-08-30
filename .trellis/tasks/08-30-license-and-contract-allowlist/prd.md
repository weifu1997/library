# License docs + sessions/folders/webdav contract

## Goal

1. Align public license documentation with `LICENSE` and `pyproject.toml` (MIT).
2. Extend the OpenAPI/TS contract allowlist to sessions, folders, and WebDAV JSON APIs using the existing response-model pipeline.

## Requirements

- **R1.** README, Chinese README, launch copy, and UPSTREAM notes must not claim Library is AGPL. Canonical license is MIT (`LICENSE`, `pyproject.toml`).
- **R2.** Historical third-party AGPL provenance (removed AstrBot packaging scripts; Headroom vendor) may still be mentioned as *upstream* licenses, not Library's license.
- **R3.** Add named response models for JSON session, folder, and WebDAV routes. Binary attachment and folder-zip download stay untyped streams. DELETE session is 204 with no body.
- **R4.** Do not change URLs, methods, auth, upload/download/SSE/citation/MCP/CLI semantics, or DB schema.
- **R5.** Keep `frontend/src/types/api.ts` as a facade; alias new generated schemas. Do not wholesale-replace it.
- **R6.** Update contract tests and regenerate committed OpenAPI + TypeScript.

## Out of scope

- Changing the LICENSE file or PyPI classifier away from MIT.
- file-entries, exports, tend, MCP, semantic-index precise models.
- Chat UI for `user_artifact`.
- Expanding CI `on:` branches.

## Acceptance

- [ ] Docs say MIT and point at `LICENSE`.
- [ ] Session/folder/WebDAV JSON operations have named OpenAPI schemas.
- [ ] Attachments remain non-JSON; session DELETE is 204.
- [ ] `pytest tests/test_openapi_contract.py` and related e2e pass.
- [ ] `gen:api` + `git diff --exit-code` on OpenAPI/generated TS/schemas is clean.
