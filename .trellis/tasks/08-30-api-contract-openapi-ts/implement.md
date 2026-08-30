# Implementation plan

Do **not** run this until the user explicitly approves the latest complete scheme (`审核通过` / `确认方案` or equivalent). Then:

1. Confirm `prd.md` / `design.md` / `implement.md` still match the approved scheme.
2. `python3 ./.trellis/scripts/task.py start 08-30-api-contract-openapi-ts`
3. Load `trellis-before-dev`.
4. Follow the checklist below. Any file or behavior outside the allowed list in `design.md` §13 → stop and re-review.

## Ordered checklist

### A. Freeze current JSON (no behavior change)

- [ ] A1. Add snapshot tests that call (or invoke) each non-SSE MVP handler and record key sets / representative payloads. Do not attach `response_model` yet.
- [ ] A2. Assert search entries have no `summary` (`tests/test_user_files_e2e.py:157` already).
- [ ] A3. Assert upload `folder_id` may be null.
- [ ] A4. Assert GET `/llm` `profiles` keys == `chat,reflect,ingest,vision` and `defaults` is a sibling object.
- [ ] A5. Assert PUT extras `worker_error` / `reprocessed_failed` are absent on the happy path.

Rollback point: tests only; delete the new test file if abandoned.

### B. Schemas

- [ ] B1. Create domain modules listed in `design.md` §4.2. Keep `schemas/__init__.py` as convention text.
- [ ] B2. Strict models: `extra="forbid"`, all catalog fields, `None` serialized.
- [ ] B3. Polymorphic models: dump only `model_fields_set`.
- [ ] B4. Round-trip tests: live dict → model → JSON key set equality.

Rollback point: schema files unused by routes.

### C. Wire non-SSE routes

- [ ] C1. `response_model` on settings/stats/search/upload/tasks routes. Prefer returning model instances.
- [ ] C2. `response_model_exclude_none` left unset/False.
- [ ] C3. OpenAPI `responses` for 400/404/409/413/422/429 where the route actually raises them. Do not add 401 as required security.
- [ ] C4. Re-run snapshot tests; key sets must not shrink.

Rollback point: revert route decorator/return changes; keep schemas.

### D. SSE documentation and types (no protocol change)

- [ ] D1. `openapi_extra` / `responses` `text/event-stream` on both SSE routes. No JSON `response_model`.
- [ ] D2. `x-sse-events` catalog including `session` (not emitted) and `user_artifact`.
- [ ] D3. Backend tests: `after_cursor`, `Last-Event-ID`, terminal `done`/`error`.
- [ ] D4. Frontend: add `user_artifact` and `message` to `ChatEventType`; add `user_artifact` to `KNOWN_EVENTS`; keep unknown → `"message"`.

Rollback point: revert chat route OpenAPI extras and frontend union; runtime stream unchanged if we never touch `_replay_frames` logic.

### E. OpenAPI export

- [ ] E1. `FastAPI(..., version=__version__)` in `main.py`.
- [ ] E2. `src/library/openapi_export.py` + `uv run python -m library.openapi_export`.
- [ ] E3. Commit `openapi/openapi.json`. Secret scan in exporter.
- [ ] E4. Test: 14 MVP operations present; SSE content type; `info.version == __version__`; non-MVP wide-schema list frozen.

### F. TypeScript

- [ ] F1. `npm --prefix frontend install --save-dev openapi-typescript@7.13.0`.
- [ ] F2. Script `gen:api`. Run it; commit `frontend/src/types/generated/openapi.d.ts`.
- [ ] F3. Alias MVP types in `frontend/src/types/api.ts`. Add `generated/usage.ts` fixture.
- [ ] F4. Fix resulting type errors (`SearchEntry`, `folder_id`, `LlmSettings.profiles`, `stages_ms`) without rewriting the client.
- [ ] F5. `npm --prefix frontend run lint` and `build`.

### G. CI

- [ ] G1. Add `contract` job as in `design.md` §9.
- [ ] G2. Locally simulate: generate, then `git diff --exit-code` on the listed paths.
- [ ] G3. Locally simulate drift: delete a generated line, confirm diff would fail.

### H. Docs and quality

- [ ] H1. Short developer note (README or `docs/`) for export + `gen:api`.
- [ ] H2. `uv run ruff check src tests`
- [ ] H3. `uv run pytest tests/ -v`
- [ ] H4. `trellis-check`
- [ ] H5. Do not claim PostgreSQL live tests or old-version interop.

## Validation commands

```bash
uv sync --locked --extra dev
uv run ruff check src tests
uv run pytest tests/ -v
uv run python -m library.openapi_export
npm --prefix frontend ci
npm --prefix frontend run gen:api
npm --prefix frontend run lint
npm --prefix frontend run build
git diff --exit-code -- openapi/openapi.json frontend/src/types/generated/openapi.d.ts src/library/schemas
```

PostgreSQL: do not start a server. Existing dialect unit tests run as part of `pytest tests/`. Record them as static/dialect, not live integration.

## Review gates before `task.py start`

- [ ] User approved the latest complete scheme with an explicit phrase (`审核通过` / `确认方案` / equivalent). Vague “继续” is not enough.
- [ ] Allowed file list in `design.md` §13 is the freeze line.
- [ ] No product files have been edited during planning (only this task directory).

## Rollback points

| After | How |
|---|---|
| A | delete new tests |
| B | delete `schemas/*.py` except `__init__.py` |
| C | revert route files |
| D | revert chat OpenAPI extras + `chatStream.ts` / `api.ts` union |
| E | revert `main.py` version; delete exporter + `openapi/` |
| F | revert `package.json`/lock + generated dir + `api.ts` aliases |
| G | revert `ci.yml` |
| Merged PR | `git revert` the merge; API JSON/SSE should match pre-change |

## Follow-up (not MVP)

- Precise schemas for remaining paths.
- Chat UI for `user_artifact`.
- Frontend `Last-Event-ID`.
- CI on `v4.0`.
- Live PostgreSQL job (only if a service is actually added later).
