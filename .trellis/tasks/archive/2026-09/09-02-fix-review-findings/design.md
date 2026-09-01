# Design — fix review findings

Verified against current code on `v4.0` (2026-09-02). Each fix states the mechanism and the exact behavioral change.

## A. Backend

### A1. TQ-1 (High) — enqueue dedup vs lease expiry
**Mechanism** (verified):
- `tasks_repo.find_pending_or_running_by_dedup` (`repositories/tasks.py:24-37`) matches `dedup_key` + `status IN ('pending','running')` — no lease check.
- `tasks_repo.has_inflight_for_kind` (`repositories/tasks.py:315-342`) deliberately treats an expired-lease `running` row as *not inflight* (`lease_expires_at IS NULL OR >= now`).
- `periodic_tick.py:128` uses `has_inflight_for_kind` (says "go") then `enqueue(...)` at `:153`; `enqueue.py:31` dedup short-circuit returns the stale `running` row → no new task, no recovery, audit says "task_enqueued" falsely. Recovery stalls until a separate lease reclaimer runs.
- `enqueue.py:60-78` also has an INSERT…ON CONFLICT DO NOTHING path over a partial unique index `dedup_key WHERE status IN ('pending','running')`. A stale `running` row still satisfies the index predicate → a fresh insert conflicts even after the short-circuit is fixed.

**Fix**:
1. `find_pending_or_running_by_dedup(db, dedup_key, *, now=None)` — add `now`; running rows count only when `lease_expires_at IS NULL OR lease_expires_at >= now` (exact `has_inflight_for_kind` semantics). Pending rows always count.
2. Add `reclaim_expired_running_for_dedup(db, dedup_key, *, now) -> bool` — `UPDATE … SET status='dead', finished_at=now, last_error='lease expired; reclaimed by enqueue', locked_by=NULL, lease_expires_at=NULL WHERE dedup_key=? AND status='running' AND lease_expires_at IS NOT NULL AND lease_expires_at < now`. The `locked_by/lease_expires_at` clear is the fencing release; the dead worker's `mark_done` guard (`WHERE locked_by==worker AND lease_expires_at==old`) will then no-op, which is correct.
3. `enqueue.py` conflict branch (`rowcount == 0`): try `reclaim_expired_running_for_dedup`; if it reclaimed a row, re-run the INSERT; then return `find_pending_or_running_by_dedup(...)` (which, post-fix, returns None if the surviving row is stale — caller treats as new enqueue… but the row WAS inserted, so re-query returns the new row). Order carefully so the return is the actual active row.

**Test point**: `tests/test_tasks_enqueue_unit.py`-style new case — insert a `running` row with `lease_expires_at` in the past + same dedup_key → `enqueue` returns a fresh row (old one becomes dead), and a second enqueue within lease returns the running row.

### A2. AP-1 — tend dead bucket
`api/routes_tend.py:153-174`. Add `"dead": 0` to `state_counts` (additive — response contract grows one key). `bucket = status if status in state_counts else "pending"` then maps terminal `dead` → `dead` instead of `pending`. Confirm no frontend consumer asserts an exact 6-key shape (additive is safe; check `frontend` tend usage during impl).

### A3. TQ-2 — purge TOCTOU
**Mechanism**: `tasks/handlers/purge_deleted_files.py:155-160` — after `session.commit()` the file row is gone; the direct `_delete_storage_object(storage, file_id, key)` runs without re-checking that no live reference to `storage_key` exists. A concurrent restore (re-create file row pointing at same object) would have its object deleted.

**Fix**: after commit, before each delete, open a short `session_scope()` and run `SELECT 1 FROM files WHERE storage_key=? LIMIT 1`. If a row exists → skip delete (object still referenced), audit `storage_delete_skipped` with reason `object_referenced`. Add `files_repo.exists_by_storage_key(db, storage_key) -> bool`. Note: this also covers the same-object-reused-by-restore case. (The enqueued `KIND_DELETE_STORAGE_OBJECT` task path is a separate consumer; out of scope — it runs from a replayed queue row.)

**Test point**: unit test — commit a purge, simulate restore by re-inserting a `files` row with the same `storage_key`, assert `_delete_storage_object` is not invoked (mock storage.delete not called).

### A4. AT-1 — required-arg validation
Sites (verified): `analyze_container.py:133` (`args["container_entry_id"]`), `materialize_view.py:60` (`args["id"]`), `read_catalog.py:59` (`args["id"]`), `resolve_tag.py:49` (`args["name"]`), `generate_chart.py:130-133` (`mark`, `encoding`, `data`, `caption`).

**Fix**: use `.get()` + explicit `{"error": "missing required argument '<name>'"}` return (match existing tool error idiom — e.g. query_sql's shape). For `generate_chart`, validate each of the four keys before destructuring.

### A5. AT-2 — reconciled SQL re-validation + hostile headers
**Mechanism**: `_run_duckdb` (`query_sql.py:353-355`) executes `rewritten` from `_reconcile_columns` without re-running `_validate_sql`. A CSV header like `x"; SELECT 1 --` referenced by the model becomes a quoted identifier whose embedded `;`/`--` can splice a second statement (bounded: in-memory DuckDB + `enable_external_access=false`, but violates the only-SELECT contract).

**Fix** (two layers):
1. At column-discovery/load time (`_load_table` info_schema path / `_reconcile_columns`), validate column names with `_validate_column_name`: reject names containing `"`, `;`, or control/newline chars → surface a clear per-entry load error (`"column name '<name>' in <table> is not queryable"`). Hostile headers never become queryable identifiers.
2. After `rewritten, fixes = _reconcile_columns(...)`: if `rewritten != sql`, run `_validate_sql(rewritten)`; if it returns an error, return `{"ok": False, "error": ...}` instead of executing.

**Test point**: CSV with header `x"; SELECT 1 --` → either load rejection or validation failure, never a second statement.

### A6. AT-5 — char-cap paging
**Mechanism**: `query_sql.py:423-434` — char cap sets `rows=flat_rows[:keep]`, `row_count=keep`, `truncated=True`, `has_more=True`, `next_offset=offset+keep`. Because `flat_rows` was already the full DB page (`LIMIT row_limit`), `offset+keep` causes the next page to re-deliver `[keep, len(flat_rows))` (duplicate context), and `has_more=True` is forced even when the DB page wasn't full (phantom "more").

**Fix**:
- `next_offset = offset + len(flat_rows)` (advance by the full fetched page → monotonic, no re-delivery, no permanent gap).
- `has_more = len(flat_rows) >= row_limit` (honest page-full test, same idiom as the normal path).
- Keep `truncation_reason`; update its copy to state the page advanced by the full fetch.

**Test point**: wide table >40k chars: page 1 `next_offset` equals the page's full row count; page 2 returns only genuinely-new rows.

## B. Frontend

### B1. FR-1 — ErrorBoundary
New `frontend/src/components/ErrorBoundary.tsx` (class component: `componentDidCatch`, `getDerivedStateFromError`). Fallback = existing design tokens (`bg-bg-card`, `text-fg-base`, `text-danger`) + error message + "reload" button (`window.location.reload()`). Wrap the `<Suspense>`/`<Routes>` block in `App.tsx` (and the whole tree below `BackendGate` is fine — keep scope to Routes). Verify a lazy-page throw lands in the boundary.

### B2. FR-2 — prefs localStorage guard
`lib/prefs.ts:52,56,60` — wrap each `setItem` in `try/catch` and always `set(...)` the in-memory state. Also wrap the `read*` `getItem` calls in `try/catch` (property access can throw in sandboxed iframes even though `typeof localStorage === "object"`). Same defect class exists in `lib/theme.ts:33-36,39` (FE-1, Low) — fix it in the same pass (adjacent, flagged).

### B3. FR-3 — cursor-less SSE dedup
`api/chatStream.ts:124` `publish()`: keep a `seenCursorless = new Set<string>()` (module- or consume-scope). For an event with no `eventCursor`, skip when `${type}:${data}` is already in the set, else add it. Safe because cursor-less frames are terminal-only (the pre-conversation error frame in `routes_chat.py:291` is the only id-less frame; `done`/`error` with cursors are already deduped by cursor). Comment explains the invariant.

### B4. FR-5 — light-mode contrast
`styles/globals.css:24` `--fg-subtle: 148 163 184` (slate-400) → `100 116 139` (slate-500, ≈4.7:1 on `--bg-base` white). Dark block unchanged. Check the `.dark` block already uses slate-500 (`:71`), so light/dark now match luminance intent. Re-scan `text-fg-subtle` usages that are 11-12px labels (the reported AA failures).

### B5. FR-6 — ChatPage suggestions i18n
`pages/ChatPage.tsx:622-626` — move the 3 suggestion cards' `{title, desc, prompt}` into i18n as `chat.suggestions: [{title, desc, prompt}, …]` (en + zh). Component reads `t.chat.suggestions` (icon stays component-side). Add keys to `I18nStrings` type.

### B6. FR-7 — SearchPage i18n
`pages/SearchPage.tsx:102,129,137` (+ sample chips `:54`) — add keys: `search.emptyBody`, `search.noMatchesHint`, `search.foundResults` (interpolated with count), `search.sampleQueries` (array). Component substitutes `{n}`. en + zh. (FR-10 clear-button `aria-label` is adjacent Low — include `t.search.clear`.)

### B7. VW-4 — DOCX render storm
`components/library/viewers/OfficeViewer.tsx:569-585` — remove the per-page `setRenderKey(n+1)` bumps inside the loop (the `quoteRef.current || completedThrough===1 || completedThrough===pageCount` block). Keep `setRenderedPageCount` (progress). The final `setRenderKey` before `setRendering(false)` stays → `useQuoteJump` content (`docx:${url}:${renderKey}`, `:428-436`) changes once at completion, not per page. Verify `quoteRef` early-jump still fires at completion (renderKey>0). If progress setState per page proves noisy, batch via a ref flushed on rAF — but only if needed.

## C. Docs + old findings

### C1. D1–D19 — each correction (re-verify against code before writing)
- D1: `DESIGN.md:344`, `USAGE.md:542` — OCR default cap 300 (`config.py:394`, `.env.example:339-341`). State the default cap instead of "uncapped".
- D2: `DESIGN.md:430-444`, `USAGE.md:347-351` — MCP has 7 workflow tools (`mcp_server.py:37-46`); "read-only retrieval only" claim is wrong.
- D3: `README.zh-CN.md:236` — 16 tables (not "14 张表, 4 层"); diagram omits agent_events/tag_aliases/views.
- D4: `README.zh-CN.md:249`, `README.md:173-179`, `DESIGN.md:305-314` — 10 pipelines (not 8); add email/pptx/markitdown.
- D5: `USAGE.zh-CN.md:214,222,231-238` — `marg` CLI removed → `library` binary; rewrite the command block to `library` equivalents or a removal note.
- D6: `USAGE.zh-CN.md:185-187` — no `/on-conflict` command; default conflict policy is `rename`.
- D7: `USAGE.zh-CN.md:465` — no `/restore` command.
- D8: `USAGE.zh-CN.md:459` — `cmd_search` has no `--include-archived`.
- D9: `USAGE.zh-CN.md:385` — `storage migrate` only local↔mirror (`cli/storage_cmd.py:30`); no `--to s3`.
- D10: `USAGE.zh-CN.md:412`, `README.zh-CN.md:522` — `.library/.env` is not read; config reads CWD then `LIBRARY_HOME/.env` (`config.py:710-724`).
- D11: `docs/LAUNCH.md:165` — desktop bundles removed; no `src-tauri/`.
- D12: `docs/GUI_TUTORIAL.zh-CN.md:145` — token budgets plan 2048 / execute 4096 (`config.py:309-310`).
- D13: `CHANGELOG.md:581` — `COMPRESSION_*` (renamed from `READ_COMPRESSION_*`).
- D14: `docs/UPGRADE-PLAN.md:12,299-300` — Non-goals is §13, Invariants §11.
- D15: `README.zh-CN.md:370` — `/health` returns version + storage_backend (correct after AP-12 fix).
- D16: `skills/research-with-library/SKILL.md:26` — profile prefix is `LLM_<PROFILE>_*` inheriting `LLM_DEFAULT_*`, not `LIBRARY_LLM_CHAT_*`.
- D17: `samples/quickstart.md:30` — no `--name` flag on upload; trailing-slash/extension disambiguation.
- D18: `USAGE.md:86-87` — `AGENT_EXECUTE_MAX_TOKENS` default 4096.
- D19: `samples/architecture.md:305` — eval also has `ablation-run`, `load-run` (`cli/eval_cmd.py`).

### C2. L-2→AP-12 — /health surface
`src/library/main.py:454-464`: `/health` returns `{status, version, storage_backend}` (drop `git_sha`, `build_id`, `environment`). Frontend contract `isBackendHealth` needs `status` + `storage_backend` (kept) and optional `version` (kept) — verified `client.ts:103-110`. Consumers: `StatusBar` (storage_backend), `OverviewPage` (storage_backend), `SettingsPage` (storage_backend). Regenerate `openapi.d.ts` (`/health` response schema) — check for a codegen script; if none, hand-sync the `health_health_get` response. Update D15 to match.

### C3. L-3→AP-7 — mask
`api/routes_settings.py:99-104`: `_mask` → for `len(secret) > 6` return `f"****{secret[-4:]}"` (drop first-3); `len <= 6` stays `"***"`. Standard last-4 masking. Verify all 7 call sites still type-check.

### C4. L-4 — docstring
`repositories/tasks.py:40-50`: `claim_pending_ids` docstring → state that rows are selected pending-first, and that transition-to-running uses `mark_running`'s CAS (`WHERE status='pending' RETURNING`) with worker fencing (owner token + lease) — matches `mark_running:65-91`.

## Rollback shape
Each fix is a small independent edit; if a regression appears, revert that edit only. The two multi-touch areas are (a) TQ-1 (repo + enqueue — one logical change) and (b) AT-2 (load-time validation + re-validation — one logical change). Docs edits are isolated per file.
