# Implement — fix review findings

Ordered so each area is verified before moving on. Baselines run first and last.

## 0. Baseline (before any edit)
- [ ] `uv run ruff check src tests` — record current state (should be clean).
- [ ] `uv run pytest -q` — record count (753 passed / 1 skipped at review time).
- [ ] `cd frontend && npx tsc -b --noEmit && npx eslint --max-warnings 31 .` — record (0 errors / 16 warnings at review time).

## A. Backend (ruff + targeted pytest after each)
1. **TQ-1** — `src/library/repositories/tasks.py` (add `now` to `find_pending_or_running_by_dedup`; add `reclaim_expired_running_for_dedup`) + `src/library/tasks/enqueue.py` (pass `now`; conflict-branch reclaim+retry). Verify `mark_done`/`mark_running` fencing guards exist so reclaim release is safe.
2. **TQ-1 test** — new test in `tests/` (stale running row with expired lease + same dedup_key → `enqueue` returns fresh row; row becomes dead). Match existing enqueue test file conventions.
3. **AP-1** — `src/library/api/routes_tend.py` add `"dead": 0`. Check frontend tend consumer for exact-shape assertions.
4. **TQ-2** — `src/library/tasks/handlers/purge_deleted_files.py` re-check after commit (`exists_by_storage_key`) + skip + audit; `src/library/repositories/files.py` add `exists_by_storage_key`.
5. **TQ-2 test** — mock storage, restore a files row with same storage_key, assert delete not called.
6. **AT-1** — 5 tools `.get()` + missing-arg error (match existing error idiom).
7. **AT-2** — `query_sql.py`: `_validate_column_name` at load/discovery + re-validate reconciled SQL.
8. **AT-2 test** — hostile header `x"; SELECT 1 --` rejected at load or validation; never executes a second statement.
9. **AT-5** — `query_sql.py` char-cap: `next_offset = offset + len(flat_rows)`; `has_more = len(flat_rows) >= row_limit`; update `truncation_reason`.
10. **AT-5 test** — wide payload: next page returns only new rows; `has_more` false on a non-full page.
11. **L-2→AP-12** — `src/library/main.py` `/health` → `{status, version, storage_backend}`; resync `frontend/src/types/generated/openapi.d.ts` (`/health`). Check `docs`/`README` /health claims (part of D15).
12. **L-3→AP-7** — `routes_settings.py` `_mask` → `****<last4>`.
13. **L-4** — `repositories/tasks.py` `claim_pending_ids` docstring (CAS + fencing).
14. Gate: `uv run ruff check src tests` + `uv run pytest -q` (targeted test files first, then full).

## B. Frontend (tsc + eslint after each)
15. **FR-1** — new `ErrorBoundary.tsx`; wrap Routes in `App.tsx`.
16. **FR-2 (+FE-1)** — `lib/prefs.ts` read/write guards; `lib/theme.ts` same pattern.
17. **FR-3** — `api/chatStream.ts` `publish()` cursor-less fingerprint dedup.
18. **FR-5** — `styles/globals.css:24` light `--fg-subtle` → slate-500 `100 116 139`.
19. **FR-6** — i18n `chat.suggestions` (en+zh) + `ChatPage.tsx` consume; update `I18nStrings` type.
20. **FR-7 (+FR-10)** — i18n `search.emptyBody` / `noMatchesHint` / `foundResults` / `sampleQueries` / `clear` (en+zh) + `SearchPage.tsx` consume.
21. **VW-4** — `OfficeViewer.tsx` remove per-page `setRenderKey` bumps; keep completion bump.
22. Gate: `npx tsc -b --noEmit` + `npx eslint --max-warnings 31 .` (≤16 warnings).

## C. Docs (grep-verify each after edit)
23. D1–D19 per design.md C1 (19 files/edits). Each: re-grep the code claim, then write. D15's /health text depends on step 11 — do D15 after AP-12 lands.
24. Gate: `grep` each corrected claim against code once more.

## D. Finish
25. Full backend + frontend baseline re-run (ruff / pytest / tsc / eslint). Compare to step 0 — no new warnings; pytest count ≥ baseline.
26. `git status` review — only intended files changed. Commit on `v4.0` with message covering the fix groups; list IDs in body (TQ-1, AP-1, TQ-2, AT-1/2/5, FR-1/2/3/5/6/7, VW-4, D1–D19, AP-12, AP-7, L-4).
27. Update task.json notes / close out; archive if requested.

## Review gates
- After step 1-2 (TQ-1) and step 6-9 (AT-*) — the two behavioral hot spots — re-read the diff before proceeding.
- Frontend after step 21 (VW-4) — re-read the render-loop diff.
