# Phase 1 evidence (re-verified 2026-08-30)

Historical architecture-audit notes were treated as clues only. Facts below were re-checked against current source, tests, OpenAPI, and git.

## Git / Trellis

- Branch `v4.0...origin/v4.0`, working tree clean (`git status --short --branch`).
- `task.py current --source` was empty before `08-30-api-contract-openapi-ts` was created.
- No prior OpenAPI/contract planning task under `.trellis/tasks/`.
- Tags: `v0.1.0`–`v0.3.6`. HEAD `0eb4bcf` is after `v0.3.6` (`321a67b`).
- No committed `openapi.json`. No frontend `*test*` / `*spec*` files.

## Response models / schemas

- Sole `response_model`: `src/library/main.py:366` (`GET /ready`, `None`).
- `src/library/schemas/__init__.py:1-13` — domain-split convention, empty package.

## Paths (source)

- Prefix: `src/library/main.py:316-331`.
- Settings: `routes_settings.py:136,249,549,632,723`.
- Stats: `routes_stats.py:83`.
- Search: `routes_user_files.py:41` → `GET /v1/search`.
- Upload: `routes_upload.py:178` → `POST /v1/upload` status 201.
- Tasks: `routes_tasks.py:32,69,102,156`.
- Chat SSE: `routes_chat.py:214,468`.

## OpenAPI dump (`app.openapi()`, FastAPI 0.136.3)

- `info`: `{title: Library, version: 0.1.0}`.
- 58 paths. No `security` / `securitySchemes`.
- Components: request bodies only (18 schemas). MVP JSON 200/201 = `additionalProperties: true`.
- SSE documented as `application/json` (chat empty schema; events empty schema).
- `Last-Event-ID` header already in events operation parameters.

## Settings fields

- Server 93 keys: `routes_settings.py:144-246`.
- Frontend missing 8 keys: `frontend/src/types/api.ts:431-517`.
- `semantic_index`: `src/library/semantic/index.py:127-142` (includes `documents`, `section_entries`).
- `webdav`: `src/library/services/webdav_sync.py:1189-1198`.
- Visible profiles: `src/library/config.py:442` = chat/reflect/ingest/vision.
- GET llm: `routes_settings.py:307-331` (`profiles` + `overlay` + `defaults`).
- PUT extras: `worker_error` 781, `reprocessed_failed` 791.
- Masking: `_mask` `routes_settings.py:90-95`.
- Auth test: `tests/test_settings_routes_e2e.py:214-238`.

## Search / upload / tasks

- Search fields: `src/library/services/user_files.py:132-148`; no summary (`tests/test_user_files_e2e.py:157`).
- Frontend `SearchEntry` phantom `summary`/`score`: `frontend/src/types/api.ts:69-76`; UI `SearchPage.tsx:164`.
- Upload result: `routes_upload.py:298-306`; `folder_id: str | None` `services/upload.py:72`.
- 413 middleware: `src/library/upload_limits.py:185-197`.
- 429: `src/library/capacity.py:15-28`.
- Recent `stages_ms`: `routes_tasks.py:145`. Throughput unused by frontend.

## SSE

- Event docstring: `src/library/agent/types.py:49-66` (includes `session`).
- No `event_type="session"` yield in repo.
- `user_artifact`: `src/library/agent/runtime.py:3402-3409`; test `tests/test_generate_chart_e2e.py:222-230`.
- Replay / `after_cursor` / `Last-Event-ID`: `routes_chat.py:425-484`.
- Frontend parser fallback: `frontend/src/api/chatStream.ts:153-183`.
- Resume uses query `after_cursor` only: `chatStream.ts:69`. No `Last-Event-ID` tests.

## Auth

- `src/library/main.py:49` `PUBLIC_PROBE_PATHS`.
- `src/library/main.py:250-267` optional bearer; OPTIONS exempt.
- No `exception_handler` in `main.py`.

## CI / frontend toolchain

- `.github/workflows/ci.yml:10-14` `main` only.
- `uv sync --locked --extra dev`: line 61.
- No PostgreSQL service.
- Node 20, `npm ci`, `lint`=`tsc -b --noEmit`, `build`.
- `frontend/package.json` has no `openapi-typescript`.
- npm `openapi-typescript@7.13.0` MIT (registry 2026-08-30).

## PostgreSQL / old versions

- Tests use SQLite. Postgres mentions are dialect/engine unit tests (`tests/test_entry_metadata_fts_unit.py`, `tests/test_sqlite_performance_tuning_unit.py`).
- `PGHOST` unset in this environment.
- No in-repo old frontend/backend artifacts. **未进行真实互测.**
