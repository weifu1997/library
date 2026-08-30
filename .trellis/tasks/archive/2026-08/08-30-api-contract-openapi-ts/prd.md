# API contract: OpenAPI + TypeScript types + CI check

## Goal

Reduce silent drift between backend JSON, Pydantic response models, FastAPI OpenAPI, generated TypeScript types, and frontend API usage — without changing public API URLs, methods, auth, upload, download, SSE, citation, MCP, or CLI semantics.

User value: Settings, Overview, Search, Upload, task status, and Chat keep working while CI fails the build when those contracts change without an accompanying schema/type update.

## Background

Library is a local-first knowledge base. The HTTP API is FastAPI under `/v1`. The GUI uses a handwritten client (`frontend/src/api/client.ts`) and handwritten types (`frontend/src/types/api.ts`). There is no committed OpenAPI document, no `openapi-typescript` dependency, and almost no `response_model`.

This is a complex contract task. Implementation waits for explicit approval of the latest complete scheme, then `task.py start`.

## User decisions already confirmed

- Create this Trellis task (do not reuse `08-27-architecture-audit-open-source-options`).
- MVP is the 14 source-confirmed paths listed below, including `GET /v1/tasks/throughput`.
- Strategy: export **full** OpenAPI JSON; give **MVP paths precise response schemas**; generate TypeScript into a **separate file**; **do not replace** `frontend/src/types/api.ts` as a whole.

## Confirmed facts (re-verified 2026-08-30)

Evidence index: `research/phase1-evidence.md`. Highlights:

- Working tree clean; branch `v4.0`; current task was empty before this directory was created.
- Only `GET /ready` sets `response_model` (`src/library/main.py:366`), and it is `None`.
- `src/library/schemas/__init__.py` documents domain-split Pydantic modules; the package contains no domain files.
- Live OpenAPI: 58 paths, `info.version` is FastAPI default `0.1.0`, no security scheme, MVP JSON success bodies are `additionalProperties: true`, SSE routes are documented as `application/json`.
- Project version is `0.3.6` (`src/library/__init__.py:3`, `pyproject.toml:3`, `frontend/package.json:4`).
- `openapi-typescript` is not installed. Latest npm release at planning time: `7.13.0`, MIT (`https://openapi-ts.dev`).
- CI runs `uv sync --locked --extra dev` (`.github/workflows/ci.yml:61`), has no PostgreSQL service, and triggers only on `main`.
- Auth 401 exists only when `LIBRARY_API_TOKEN` is set (`src/library/main.py:250-267`). Public probes `/health`, `/live`, `/ready` and `OPTIONS` are exempt.
- `session` is documented on `AgentEvent` (`src/library/agent/types.py:52`) but is not yielded. `user_artifact` is yielded (`src/library/agent/runtime.py:3402`).
- Frontend unknown SSE events become `"message"` (`frontend/src/api/chatStream.ts:168,183`).
- No runnable old frontend/backend artifacts; tags `v0.1.0`–`v0.3.6` exist. No live PostgreSQL in this environment.

## MVP paths

| Method | Path | Success |
|---|---|---|
| GET | `/v1/settings/server` | 200 JSON |
| GET | `/v1/settings/llm` | 200 JSON |
| PUT | `/v1/settings/llm` | 200 JSON |
| POST | `/v1/settings/llm/test` | 200 JSON (including `ok: false`) |
| POST | `/v1/settings/llm/models` | 200 JSON (including `ok: false`) |
| GET | `/v1/stats/overview` | 200 JSON |
| GET | `/v1/search` | 200 JSON |
| POST | `/v1/upload` | 201 JSON |
| GET | `/v1/tasks/running-count` | 200 JSON |
| GET | `/v1/tasks/active` | 200 JSON |
| GET | `/v1/tasks/recent` | 200 JSON |
| GET | `/v1/tasks/throughput` | 200 JSON |
| POST | `/v1/chat/{session_id}` | 200 `text/event-stream` |
| GET | `/v1/conversations/{conversation_id}/events` | 200 `text/event-stream` |

## Requirements

- **R1.** Add domain-split Pydantic response models under `src/library/schemas/` covering every public JSON field of the non-SSE MVP paths. Reuse existing request models in route files; do not invent a second settings/llm shape that merges `profiles` and `defaults`.
- **R2.** Attach `response_model` (or equivalent returning a model instance) to every non-SSE MVP route. Before wiring, freeze the live key set in tests so FastAPI cannot silently drop fields.
- **R3.** Keep current `None` serialization for fields that already appear as JSON `null`. Do not globally enable `response_model_exclude_none`. PUT extras (`worker_error`, `reprocessed_failed`) and polymorphic probe objects must omit absent keys rather than emit new nulls.
- **R4.** Document existing error status codes in OpenAPI `responses` without changing runtime payloads or adding status codes the source does not raise. Verify 401 only when token auth is configured; otherwise mark N/A.
- **R5.** Do not attach a JSON `response_model` to `EventSourceResponse` routes. Document both SSE routes as `text/event-stream`. Catalog transport events from runtime + persistence, including `user_artifact` and documented-but-not-emitted `session`. Keep unknown-event fallback `"message"` on the frontend parser.
- **R6.** Export a deterministic full OpenAPI JSON (all 58 paths). MVP paths must have named, non-generic success schemas. Non-MVP paths may remain wide; a test must list them so they cannot masquerade as typed.
- **R7.** Set OpenAPI `info.version` to `library.__version__` (proposed; see design). Generated documents, examples, and fixtures must not contain API keys, bearer tokens, passwords, or DSNs.
- **R8.** Add `openapi-typescript@7.13.0` as a frontend **devDependency**, lock it in `frontend/package-lock.json`, and generate types with the local binary (no unpinned `npx`). Output a separate committed file. Do not wholesale-replace `frontend/src/types/api.ts`.
- **R9.** Frontend must actually use generated types: re-export or alias MVP types from the generated file, plus a compile-only fixture that imports `paths` so the generated file is not orphaned. Keep the existing fetch/XHR client, upload XHR, and SSE parser.
- **R10.** CI contract check on a clean checkout: generate OpenAPI, generate TypeScript, `git diff --exit-code` on the committed generated files and schema modules. Fail if install/generate fails or if the working tree is dirty after a supposed success. Use locked uv and npm. Do not invent a PostgreSQL service.
- **R11.** Tests must cover: MVP field sets; OpenAPI path/method presence; error status documentation vs runtime; SSE event names, terminal events, `after_cursor`, and `Last-Event-ID`; secret redaction; profiles vs defaults remaining distinct.
- **R12.** No database schema change, no Alembic migration, no runtime data-layer library (React Query / GraphQL / OpenAPI Fetch), no replacement of parser / vector store / LLM adapter / agent runtime / semantic index.

## Out of scope

- Precise response models for the remaining ~44 non-MVP paths.
- Unifying or rewriting exception handlers / error JSON.
- Changing API URLs, methods, auth logic, upload/download protocol, SSE event names, citation, MCP, or CLI tool semantics.
- Rendering `user_artifact` in Chat UI (typing it is in scope; new UI is not).
- Sending `Last-Event-ID` from the frontend (backend support + tests are in scope; client keeps `after_cursor`).
- Replacing `frontend/src/api/client.ts`.
- Expanding CI `on:` branches to `v4.0` unless separately approved.
- Live PostgreSQL integration tests or old-release interop tests (environment/artifacts unavailable).
- Moving existing request models out of route files.

## Acceptance criteria

- [ ] AC1. All 14 MVP path+method pairs exist in the committed OpenAPI document with the correct HTTP method.
- [ ] AC2. Non-SSE MVP success schemas are named models, not `additionalProperties: true` objects. A test lists non-MVP untyped paths.
- [ ] AC3. Live JSON key sets for non-SSE MVP routes equal the response-model key sets; adding `response_model` does not drop fields. `folder_id` on upload remains nullable. PUT extras and probe variants do not gain new always-null keys.
- [ ] AC4. `profiles` and `defaults` remain different structures. Visible profiles are `chat|reflect|ingest|vision`. `default` appears on test-default and in `defaults`, not as a GET `profiles` key.
- [ ] AC5. SSE routes are `text/event-stream` in OpenAPI, have no JSON `response_model`, and the event catalog includes `conversation`, `planning`, `plan`, `thinking`, `tool_call`, `tool_result`, `user_artifact`, `answer`, `error`, `done`, plus `session` marked currently-not-emitted. Frontend unknown events still become `"message"`.
- [ ] AC6. Tests cover SSE normal end (`done`), error end, resume via `after_cursor`, and `Last-Event-ID`. Frontend reconnect still uses `after_cursor`.
- [ ] AC7. Existing error codes for MVP routes are documented; runtime payloads unchanged. 401 tests run only with token configured.
- [ ] AC8. `openapi-typescript@7.13.0` is in `frontend/devDependencies` and lockfile. Generated `.d.ts` is committed, repeatable, and imported by `api.ts` aliases and/or a compile-only fixture.
- [ ] AC9. `npm --prefix frontend run lint` and `build` pass. Handwritten `api.ts` still exists as the GUI type facade.
- [ ] AC10. CI contract job regenerates OpenAPI + TS on a clean checkout and fails on drift (`git diff --exit-code`). `uv sync --locked --extra dev` remains the backend install path.
- [ ] AC11. Secrets do not appear in responses, OpenAPI, generated types, logs, or fixtures.
- [ ] AC12. SQLite tests in `tests/` pass. PostgreSQL is static/dialect-only; the report must not claim live PG tests passed. Old-version analysis is static; the report must say 未进行真实互测.
- [ ] AC13. No Alembic migration, no DB schema change, no new runtime frontend data-layer dependency.

## Proposed decisions included in the scheme

Approving this scheme accepts these recommendations:

1. `FastAPI(..., version=library.__version__)` so live `/openapi.json` and the committed file share `0.3.6` (documentation-only).
2. Commit `openapi/openapi.json` and `frontend/src/types/generated/openapi.d.ts`.
3. Add a dedicated `contract` job to `.github/workflows/ci.yml` without changing `on:` branches.
4. `response_model_exclude_none` stays `False`.
5. Pin `openapi-typescript` to exact `7.13.0`.
6. Type `user_artifact` in the UI event union; do not add Chat UI for it in MVP.
7. Keep frontend resume on `after_cursor`; test `Last-Event-ID` on the backend.

## Open questions

None blocking. Remaining items are the proposed decisions above, accepted or rejected when the user approves or returns the scheme.
