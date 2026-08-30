# Design: API contract pipeline

## 1. Architecture and boundaries

```
route dict (current JSON)
  → Pydantic response model (schemas/<domain>.py)
  → FastAPI OpenAPI (app.openapi())
  → committed openapi/openapi.json
  → openapi-typescript 7.13.0
  → frontend/src/types/generated/openapi.d.ts
  → aliases in frontend/src/types/api.ts
  → existing client.ts / chatStream.ts (unchanged runtime)
```

Non-goals at this boundary: no React Query, GraphQL, OpenAPI Fetch, client rewrite, DB migration, or SSE business-semantic change.

`src/library/schemas/__init__.py` stays a convention module (docstring). Routes import domain modules directly. No barrel re-export, to avoid import cycles.

## 2. Data flow

1. Snapshot tests capture live JSON key sets for each non-SSE MVP handler (no `response_model` yet).
2. Domain models are written to match those sets.
3. Handlers still build the same dicts, then `Model.model_validate(payload)` and return the model (or keep `response_model=Model` after a key-equality test). Returning a model instance is preferred so FastAPI does not re-filter an untyped dict.
4. OpenAPI export imports `library.main.app` and writes sorted JSON. Lifespan is not started.
5. Typegen reads the committed JSON via the local `openapi-typescript` binary.
6. CI repeats 4–5 on a clean checkout and diffs.

## 3. MVP vs full OpenAPI

- Export **all 58 paths** (FastAPI already does).
- **Precise schemas** only on the 14 MVP operations.
- Non-MVP success bodies may remain `additionalProperties: true`. Test `test_openapi_untyped_paths` holds the allow-wide list. Adding a new precise schema is a later task, not silent scope creep.
- TypeScript is generated from the **full** document so `paths` is complete, but GUI aliases only MVP schemas. Wide non-MVP types are not treated as contracts.

## 4. Response models

### 4.1 Reuse

Reuse, do not duplicate:

- Request models already in routes: `LlmPatchBody`, `LlmModelsRequest`, `ChatBody`, `ChatImage`.
- Nested helpers already implied by frontend types: capabilities, backup, semantic index, webdav status — re-specified in schemas because they are not Pydantic today.

No existing domain files to import from `schemas/`.

### 4.2 New modules

| File | Models |
|---|---|
| `src/library/schemas/settings.py` | `ServerSettingsResponse`, `SemanticIndexStatus`, `WebDavStatus`, `LlmSettingsResponse`, `LlmProfileResolved`, `LlmDefaults`, `LlmBackup`, `LlmCapabilities`, `LlmSettingsPutResponse`, `LlmTestResponse`, `LlmProbeVerdict`, `LlmModelsResponse`, `LlmModelInfo` |
| `src/library/schemas/stats.py` | `StatsOverviewResponse`, `StatsRecentEntry` |
| `src/library/schemas/user_files.py` | `SearchResponse`, `SearchEntry`, `SearchRelatedEntry` |
| `src/library/schemas/upload.py` | `UploadResponse` |
| `src/library/schemas/tasks.py` | `RunningCountResponse`, `ActiveTasksResponse`, `ActiveTaskItem`, `RecentTasksResponse`, `RecentTaskItem`, `TaskThroughputResponse` |
| `src/library/schemas/chat.py` | SSE payload models for OpenAPI only (`ConversationEvent`, `PlanEvent`, `ThinkingEvent`, `ToolCallEvent`, `ToolResultEvent`, `UserArtifactEvent`, `DoneEvent`, …). **Not** used as route `response_model`. |
| `src/library/schemas/errors.py` | Documentation models matching current payloads (`BearerAuthError`, `UploadTooLargeError`, `DisplayNameConflictError`, `CapacityExceededError`, `HTTPValidationError` already in OpenAPI). Not attached as exception handlers. |

### 4.3 Routes that get `response_model`

All non-SSE MVP routes. SSE routes: no JSON `response_model`.

PUT `/llm` uses `LlmSettingsPutResponse` (GET shape + optional extras). GET `/llm` uses `LlmSettingsResponse` without those extras.

### 4.4 Field catalogs (public JSON)

#### GET `/v1/settings/server` — 93 top-level keys

From `src/library/api/routes_settings.py:144-246`:

`app_env`, `library_home`, `db_backend`, `postgres_pool_size`, `postgres_max_overflow`, `postgres_pool_timeout_seconds`, `postgres_prepared_statement_cache_size`, `runtime_schema_bootstrap_enabled`, `readiness_timeout_seconds`, `storage_backend`, `worker_enabled`, `worker_running`, `worker_scheduler_enabled`, `worker_batch_size`, `worker_retry_base_seconds`, `worker_retry_max_seconds`, `bulk_reprocess_page_size`, `auto_lifecycle_enabled`, `maintenance_daily_token_budget`, `relation_background_vetting_enabled`, `audit_retention_days`, `task_retention_days`, `task_outcome_retention_days`, `agent_event_retention_days`, `prune_batch_size`, `prune_max_batches`, `relation_mining_entry_page_size`, `relation_mining_activity_limit`, `relation_mining_eligible_tag_limit`, `relation_mining_candidate_limit`, `library_document_limit`, `library_storage_bytes_limit`, `ingest_backlog_limit`, `chat_concurrency_limit`, `default_on_conflict`, `agent_plan_max_tokens`, `agent_execute_max_tokens`, `agent_execute_max_turns`, `agent_max_parallel_tool_calls`, `agent_final_answer_continue_turns`, `agent_final_answer_max_chars`, `agent_turn_timeout_seconds`, `agent_cache_slo_min_hit_ratio`, `agent_cache_slo_min_eligible_requests`, `conversation_compaction_enabled`, `conversation_compaction_reserve_tokens`, `compression_enabled`, `compression_min_chars`, `compression_target_chars`, `compression_context_chars`, `compression_max_ratio`, `llm_ingest_max_tokens`, `llm_ingest_concurrency`, `llm_default_tps`, `llm_chat_tps`, `llm_reflect_tps`, `llm_ingest_tps`, `llm_vision_tps`, `llm_vision_supports_vision`, `embedding_provider`, `embedding_api_key_set`, `embedding_base_url`, `embedding_model`, `embedding_dimensions`, `embedding_tps`, `embedding_batch_size`, `semantic_index_backend`, `semantic_recall_enabled`, `semantic_recall_limit`, `semantic_rebuild_page_size`, `section_backfill_min_score`, `section_embedding_max_sections`, `semantic_recall_configured`, `semantic_index`, `rerank_enabled`, `rerank_api_key_set`, `rerank_base_url`, `rerank_model`, `rerank_tps`, `rerank_batch_size`, `rerank_top_n`, `rerank_max_doc_chars`, `rerank_concurrency`, `rerank_configured`, `evidence_selection`, `vision_profile_configured`, `document_vision_enabled`, `document_vision_max_images`, `document_vision_question_max_images`, `document_vision_min_image_bytes`, `document_vision_min_image_dimension`, `document_vision_min_image_area`, `webdav`.

Nested `semantic_index` (`src/library/semantic/index.py:127-142`): `index_name`, `index_dir`, `exists`, `provider`, `model`, `dimensions`, `entries`, `documents`, `section_entries`, `configured_provider`, `configured_model`, `configured_dimensions`, `rebuild_page_size`, `compatible`, `needs_rebuild`.

Nested `webdav` (`src/library/services/webdav_sync.py:1189-1198`): `configured`, `url`, `username`, `password_set`, `remote_path`, `auto_sync_enabled`, `auto_sync_interval_minutes`, `last`. `last` is a free-form object or `null` (status file). Model as `dict[str, Any] | None` so we do not invent a closed WebDAV last-sync schema in MVP.

Nullable / optional notes: `url`/`username` may be null; `last` may be null; `semantic_index.provider/model/dimensions` may be null. No aliases. Enums as strings matching settings (`embedding_provider`, `semantic_index_backend`, `evidence_selection`, `default_on_conflict`) — constrain only where `Settings` already uses Literal; otherwise `str`.

Secrets: `embedding_api_key_set` / `rerank_api_key_set` / `password_set` only. Never DSN, tokens, raw keys.

#### GET `/v1/settings/llm`

Top-level: `profiles`, `overlay`, `defaults` (`routes_settings.py:307-331`).

`profiles` keys: `chat`, `reflect`, `ingest`, `vision` only (`config.py:442`). Not `default`, not `audio`.

Each profile: `provider`, `api_key` (masked str or null), `api_key_set`, `base_url`, `model`, `tps`, `capabilities`, `backup`.

`capabilities`: `dialect`, `context_window`, `tokenizer`, `supports_vision`, `supports_tools`, `supports_temperature`, `token_limit_param`.

`backup`: null or `{provider, model, base_url, api_key, api_key_set}`. Vision uses raw backup (`raw=True`); others resolved (`raw=False`).

`defaults`: `{provider, model, base_url, api_key, api_key_set, tps, backup, capabilities}` — **not** the same type as a visible profile (no requirement that keys match `LlmProfileName`).

`overlay`: `dict[str, Any]` with `*_api_key` / `*_password` values masked. Additional properties allowed; do not freeze overlay keys.

#### PUT `/v1/settings/llm`

Same as GET, plus omitted-unless-set:

- `worker_error: str` (`routes_settings.py:781`)
- `reprocessed_failed: int` (`791`)

Errors: 422 `{detail: str}` from `OverlayValidationError`; FastAPI 422 for body parse.

#### POST `/v1/settings/llm/test`

Always 200.

- `?profile=default`: `{profiles: {default: verdict}, duration_ms}` — no embedding/rerank.
- else: `{profiles: {chat,reflect,ingest,vision}, embedding, rerank, duration_ms}`.

Verdict variants (do not merge into one always-null object):

- success: `{ok: true, model, provider, duration_ms, mode?}` (`mode` is `image`/`text` for LLM profiles)
- rate-limited success: same + `note: "rate limited (reachable)"`
- failure: `{ok: false, error, duration_ms}`
- unconfigured: `{ok: null, configured: false}`

Embedding success adds `dimensions`. Unconfigured embedding/rerank: `{ok: null, configured: false}`.

#### POST `/v1/settings/llm/models`

Always 200 except 422.

- success: `{ok: true, models: [{id, display_name}], provider, base_url, duration_ms}`
- failure: `{ok: false, error, duration_ms}`
- backup missing: `{ok: false, error: "backup model not configured", duration_ms: 0.0}`
- 422 unknown profile / unsupported provider: `{detail: str}`

`display_name` is str for Anthropic, `null` for OpenAI-compatible.

#### GET `/v1/stats/overview`

`routes_stats.py:97-114`:

```
totals: {entries, folders, tags}
tasks: {running, pending}
recent: [{entry_id, display_name, folder_path, created_at, ingest_status}]
storage_backend: str
semantic: {enabled, configured, index_ready}
```

`folder_path` / `created_at` / `ingest_status` nullable. No errors besides generic 401-if-token and 5xx.

#### GET `/v1/search`

`{q, count, entries}`. Entry (`services/user_files.py:132-148`): `entry_id`, `display_name`, `folder_id`, `folder_path`, `lifecycle`, `mime_type`, `size_bytes`, `ingest_status`, `created_at`, `updated_at`, `related_entries`.

Related: `entry_id`, `display_name`, `score` only. **No `summary`.** 422 if `q` missing/too short.

#### POST `/v1/upload` 201

`file_id: str`, `entry_id: str`, `folder_id: str | None`, `display_name: str`, `deduped: bool`, `auto_renamed: bool`, `skipped: bool`.

`storage_key` is internal and must not appear.

Errors: 400 invalid dest / ambiguous path; 404 folder; 409 conflict; 413 too large; 429 capacity; 422 validation.

#### Tasks

- `running-count`: `{running: int, pending: int}`
- `active`: `{running: [item], pending: [item]}` item = `{id, kind, label, file_id, entry_id, attempts, age_s}` (`file_id`/`entry_id` nullable)
- `recent`: `{items, next_cursor}` item includes `stages_ms: dict` (`routes_tasks.py:145`) plus the fields already on `RecentTask`
- `throughput`: `{window_minutes, since, queue, completed, by_kind}` as in `routes_tasks.py:252-270`

### 4.5 Serialization rules

| Rule | Value | Why |
|---|---|---|
| `response_model_exclude_none` | `False` | Current payloads include JSON `null` (`api_key`, `backup`, `folder_id`, `next_cursor`, …) |
| Strict snapshots (server, stats, search, upload, running-count, active, recent, throughput, GET llm) | `extra="forbid"` after snapshot tests | Dropping undeclared keys is a bug |
| Polymorphic objects (test verdicts, models result, PUT extras) | validate known fields; dump **only `model_fields_set`** | Preserve omitted keys; do not emit new nulls |
| Aliases | none on MVP JSON | Handlers use snake_case keys |
| Enums | Python `Literal` only where the runtime already constrains (e.g. `on_conflict`, chat `mode`) | Do not invent closed enums for free-form strings |

### 4.6 Silent field-drop prevention

1. Fixture: expected key set per route (from snapshot tests).
2. Test: `set(live_json) == expected`.
3. Test: `set(Model.model_validate(live_json).model_dump(mode="json")) == set(live_json)` for strict models; for polymorphic, `set(dumped) == set(live_json)`.
4. Fail the build if a handler dict has keys not on the model (`extra="forbid"`).

### 4.7 Secret hygiene

- Settings already mask keys (`_mask`) and expose `*_set` booleans. Models must use `str | None` for masked `api_key`, never a plaintext example.
- OpenAPI `examples` / `openapi_extra` must not include `sk-`, `Bearer`, passwords, DSNs.
- Export post-check: scan the JSON text for obvious secret field names with non-masked values (`api_key` whose value does not contain `***` and is not null). Overlay values in schema are types only, not live overlay contents — export uses the schema, not a live settings dump.
- Tests assert `/v1/settings/llm` and `/server` bodies never contain the configured raw test key.

## 5. Error documentation

Runtime payloads stay as they are. OpenAPI `responses` added only for codes the source actually raises on that path.

| Path | Codes | Payload | 401 |
|---|---|---|---|
| All `/v1/*` | 401 | `{detail: "missing or invalid bearer token"}` | Only if `library_api_token` set. Document as optional security. Do not add a global dependency that would 401 tokenless servers. |
| PUT `/llm`, POST `/llm/models` | 422 | `{detail: str}` or FastAPI `HTTPValidationError` | N/A unless token |
| POST `/llm/test` | 422 query parse | FastAPI 422 | same |
| GET `/search` | 422 | FastAPI 422 | same |
| POST `/upload` | 400, 404, 409, 413, 422, 429 | see routes_upload / capacity / upload_limits | same |
| POST `/chat/{id}` | 400, 404, 413, 422, 429 | images / session / capacity | same |
| GET `.../events` | 404, 422 | conversation missing / query | same |
| GET `/stats/overview`, task GETs, GET `/settings/server`, GET `/llm` | (none besides 401-if-token, 422-if-bad-query on tasks) | | |

**Not in MVP:** 416 on `GET /v1/file-entries/{id}/download` (`routes_user_files.py:296-301`). Do not document 416 on search/upload/tasks.

Do not add a custom exception handler. FastAPI default 422 remains.

OpenAPI security: declare optional HTTP bearer `LibraryToken` so docs match middleware, but do not mark all operations `security` required — tokenless loopback is the default (`main.py:112-142`).

## 6. SSE

### 6.1 Rules

- No JSON `response_model` on `post_chat` or `resume_chat_events`.
- Unique event source: `AgentEvent` yielded by `run_turn`, persisted by `agent_events_repo.append`, replayed by `_replay_frames` (`routes_chat.py:425-465`). HTTP SSE `event` = `row.event`, `data` = `row.data`, `id` = cursor.
- OpenAPI 200 content: `text/event-stream` with schema describing SSE frames. Use `openapi_extra` / `x-sse-events` listing event names → payload `$ref`. Do not post-process generated TS into a fake JSON 200.
- Transport catalog (must list `session` and `user_artifact`):

| Event | Currently emitted? | Data |
|---|---|---|
| `session` | **No** (doc only, `agent/types.py:52`) | session_id string if it ever appears |
| `conversation` | Yes | conversation_id string |
| `planning` | Yes | empty / no JSON |
| `plan` | Yes | JSON `{text, budget?}` |
| `thinking` | Yes | JSON round/limit/budget fields (`runtime.py:2290-2314`) |
| `tool_call` | Yes | JSON including `display`, `entry_names`, … (`runtime.py:3020-3031`) |
| `tool_result` | Yes | JSON `ok`, `preview`/`error`, … |
| `user_artifact` | Yes | JSON `{tool_call_id, tool_index, turn, tool, payload}` (`runtime.py:3402-3409`) |
| `answer` | Yes | rewritten answer string |
| `error` | Yes | error string (also used for timeout/cancel) |
| `done` | Yes | JSON usage + `truncated`, `session_name`, `mode`, `budget` (`runtime.py:1052-1098`) |

- UI union (`ChatEventType`): current names **plus** `user_artifact` and `message`. `session` is on the transport catalog and generated OpenAPI extension, not required in the UI union until it is emitted.
- Parser: unknown names still become `"message"` (`chatStream.ts:183`). Add `user_artifact` to `KNOWN_EVENTS` so it is not mislabeled. ChatPage may keep `default: return turn` (no new UI).
- Terminal: `done` or `error`. Replay stops when conversation `ended_at` is set and latest event is `done`/`error` (or idle fallback).
- Resume: query `after_cursor` (frontend + CLI). Header `Last-Event-ID` (`routes_chat.py:472-480`) — backend tests required; frontend unchanged.
- Do not change event names, data format, end conditions, or reconnect protocol.

### 6.2 SSE tests

- Event names from a scripted turn include `user_artifact` when generate_chart runs (existing e2e) and never require `session`.
- Order: `tool_call` → `user_artifact` → `tool_result` (existing generate_chart assertion).
- Normal end: last public event `done`.
- Error end: `error` then stream close.
- Resume: `GET .../events?after_cursor=N` does not replay `id <= N` (existing quick-mode helper).
- `Last-Event-ID` numeric header takes `max(after_cursor, header)` (`routes_chat.py:478-480`). New test.
- Frontend unit is not present; keep parser behavior via a small TypeScript compile fixture and existing e2e. Do not claim a new browser test if we only add backend tests.

## 7. OpenAPI export

- Entry: `uv run python -m library.openapi_export` implementing `src/library/openapi_export.py`.
- Environment: no server, no lifespan, no `.env` values copied into the spec. Uses schema types only.
- Output: `openapi/openapi.json` (new directory). Deterministic: `json.dump(..., sort_keys=True, indent=2, ensure_ascii=False)` + trailing newline.
- Commit the file.
- `info.title` stays `Library`. `info.version` = `library.__version__` via `FastAPI(version=__version__)` in `main.py` (docs-only; `/docs` and export stay aligned). Test: `app.openapi()["info"]["version"] == __version__`.
- Generate full `paths` + `components`. Typegen uses the whole file; contract strictness is MVP-only.
- Secret scan on the written file in the export module (fail if raw key-like examples appear).

## 8. TypeScript generation

- Package: `openapi-typescript` **exactly** `7.13.0`, MIT, `frontend/devDependencies`.
- Install: `npm --prefix frontend install --save-dev openapi-typescript@7.13.0` (updates lockfile v3).
- Script: `"gen:api": "openapi-typescript ../openapi/openapi.json -o src/types/generated/openapi.d.ts"`.
- Command: `npm --prefix frontend run gen:api` using the local `frontend/node_modules/.bin/openapi-typescript`. **Forbidden:** unpinned `npx openapi-typescript`.
- Output committed. Repeat generation must be byte-stable given the same OpenAPI file (CI diff).
- `api.ts` remains the GUI facade. MVP interfaces become `export type ServerSettings = components["schemas"]["ServerSettingsResponse"]` (and equivalents). Non-MVP types stay handwritten.
- `frontend/src/types/generated/usage.ts` compile-only fixture imports `paths["/v1/search"]` etc. `client.ts` already imports `ServerSettings` from `api.ts`, so aliases are live uses. Fixture imported from `api.ts` with `import type {} from "./generated/usage"` if needed to defeat tree-shaking of type-only files under `tsc -b`.
- Do not leave `openapi.d.ts` unimported.

Frontend type fixes that fall out of aliasing (allowed, not a wholesale replace):

- `ServerSettings` gains the 8 missing keys.
- `SearchEntry` matches backend (drop fake `summary`/`score`; add real fields). `SearchPage` summary branch becomes dead and should be removed or kept harmless.
- `UploadResult.folder_id` becomes `string | null`.
- `RecentTask` gains `stages_ms`.
- `LlmSettings.profiles` no longer includes `default`. `LlmProfileName` stays as a UI union for the editor (`default` + visible names) but is **not** the GET profiles key type. `testLlmDefault().profiles.default` stays on the **test** response type.

## 9. CI contract check

New job `contract` on `.github/workflows/ci.yml` (same `on:` as today: `main` push/PR).

Steps:

1. `actions/checkout@v4`
2. `astral-sh/setup-uv@v3` + `uv python install 3.12` + `uv sync --locked --extra dev` (same as `backend-tests`)
3. `uv run python -m library.openapi_export`
4. `actions/setup-node@v4` with `node-version: 20` and `cache-dependency-path: frontend/package-lock.json`
5. `npm --prefix frontend ci`
6. `npm --prefix frontend run gen:api`
7. `git diff --exit-code -- openapi/openapi.json frontend/src/types/generated/openapi.d.ts src/library/schemas`

If generate mutates the tree, the job fails. If uv/npm install fails, the job fails. No `|| true`.

Do not split OpenAPI across jobs in MVP; one job owns both generators so they cannot drift from different artifacts.

Optional later: upload OpenAPI as an artifact. Not required if the file is committed and regenerated in the same job.

## 10. Database and compatibility

- No schema change, no Alembic.
- SQLite remains the test database.
- PostgreSQL: keep existing dialect/unit tests; do not start or install Postgres; do not claim live PG tests passed.
- Old versions: tags exist (`v0.3.6` and earlier). No packaged old GUI/API in-tree. Compatibility analysis is Git/OpenAPI/field-set static only. **未进行真实互测.**
- Adding fields to TypeScript types is backward compatible for extra JSON keys the GUI ignored. Removing handwritten phantom fields (`SearchEntry.summary`) is a type-only correction; runtime JSON never had them (`tests/test_user_files_e2e.py:157`).
- PUT/test key-omission serializers exist specifically so we do not break clients that treat missing vs null differently.

## 11. Runtime dependencies and license

- No new Python runtime dependency.
- New frontend **dev** dependency only: `openapi-typescript@7.13.0`, MIT.
- Existing `sse-starlette` unchanged.
- Supply chain: pin exact version + lockfile; CI uses `npm ci` and `uv sync --locked`.

## 12. Rollout and rollback

- Rollout: land schemas + export + generated files + CI together on one PR. GUI runtime client unchanged, so tokenless local serve keeps working.
- Rollback: revert the PR. Public JSON and SSE behavior should be identical to pre-change; only docs/types/CI disappear.
- If `response_model` is found to drop fields in implementation, **stop** and return to scheme review rather than widening models ad hoc beyond MVP.

## 13. Allowed vs forbidden files

**Allowed (implementation, after scheme approval + `task.py start`):**

- `src/library/schemas/**`
- `src/library/openapi_export.py` (and `src/library/py.typed` untouched)
- `src/library/main.py` (FastAPI `version=`, no auth/middleware behavior change)
- `src/library/api/routes_{settings,stats,user_files,upload,tasks,chat}.py` (`response_model`, OpenAPI `responses`, SSE `openapi_extra` only)
- `tests/test_openapi_*.py`, `tests/test_contract_*.py`, extensions to existing e2e/unit tests listed in implement.md
- `openapi/openapi.json`
- `frontend/package.json`, `frontend/package-lock.json`
- `frontend/src/types/generated/**`
- `frontend/src/types/api.ts` (aliases / MVP type corrections, not wholesale replace)
- `frontend/src/api/client.ts` (type imports only if required; no client rewrite)
- `frontend/src/api/chatStream.ts` (`KNOWN_EVENTS` + `ChatEventType` alignment)
- `frontend/src/pages/SearchPage.tsx` only if phantom `summary` type-break requires a one-line guard
- `.github/workflows/ci.yml` (add `contract` job)
- `docs/` or README snippet describing `gen:api` / export (short)
- this Trellis task's planning files

**Forbidden without re-review:**

- Alembic / `src/library/db/models/**`
- parser, vector store, LLM adapter, agent runtime logic, semantic index algorithms
- replacing `client.ts` runtime, adding React Query / GraphQL / OpenAPI Fetch
- other route files (folders, webdav, sessions CRUD, exports, tend, mcp, …)
- `.env` values
- unrelated Trellis tasks
- CI `on:` branch expansion
- deleting `frontend/src/types/api.ts`

## 14. Risks

- FastAPI `response_model` dropping extras: mitigated by snapshot-first and returning model instances.
- Polymorphic 200s gaining nulls: mitigated by `model_fields_set` dump.
- `LlmSettings.profiles` typing `default` today: aliasing to generated types will type-break if code reads `data.profiles.default` on GET. Current GUI uses `data.defaults` and test endpoint `res.profiles.default` (`LlmProfileEditor.tsx:136`). Verify at implementation; if a break appears, fix types not the wire.
- Generated TS verbosity: accepted; file is generated.
- CI only on `main`: `v4.0` will not run contract until merge. Local commands still required before merge.
