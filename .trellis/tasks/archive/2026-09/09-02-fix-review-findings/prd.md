# Fix 2026-09-02 review findings (code + docs)

## Goal

Resolve the confirmed/plausible findings from the 2026-09-02 full-code review, on branch `v4.0`.
Three workstreams: (A) backend code findings, (B) frontend code findings, (C) docs drift D1–D19 + still-present old findings (L-2→AP-12, L-3→AP-7, L-4).

## Scope (per user approval: 代码 + 文档 + 旧finding；不含 A-1→LM-1 重构)

### A. Backend code
- **TQ-1 (High, CONFIRMED)**: `enqueue` dedup short-circuit ignores lease expiry → periodic maintenance recovery stalls.
- **AP-1 (Med, CONFIRMED)**: tend progress lacks `dead` bucket; dead tasks counted under `pending`.
- **TQ-2 (Med, CONFIRMED)**: purge_deleted_files deletes storage object after commit without TOCTOU reference re-check.
- **AT-1 (Med, CONFIRMED)**: 5 agent tools index required args directly (`args["x"]`) → KeyError instead of structured error.
- **AT-2 (Med, PLAUSIBLE)**: `query_sql` executes column-reconciled SQL without re-validation; hostile CSV header can splice a second statement.
- **AT-5 (Med, PLAUSIBLE)**: `query_sql` char-cap truncation sets `next_offset=offset+keep` + forced `has_more=True` → non-monotonic paging / phantom "more".

### B. Frontend code
- **FR-1 (Med, CONFIRMED)**: no ErrorBoundary → render exception blanks whole app.
- **FR-2 (Med, CONFIRMED)**: `lib/prefs.ts` localStorage writes unguarded → throws on storage-blocked contexts, UI toggle fails.
- **FR-3 (Med, CONFIRMED)**: cursor-less SSE events never deduped on reconnect (old M-3).
- **FR-5 (Med, CONFIRMED)**: light-mode `--fg-subtle` slate-400 ≈2.6:1 fails WCAG AA 4.5:1.
- **FR-6 (Med, CONFIRMED)**: ChatPage empty-state suggestion cards hardcoded Chinese.
- **FR-7 (Med, CONFIRMED)**: SearchPage empty-state body / no-matches hint / found-N / sample chips hardcoded Chinese.
- **VW-4 (Med, CONFIRMED)**: DOCX render loop bumps `renderKey` per page → `useQuoteJump` re-runs during raster render (storm).

### C. Docs + old findings
- **D1–D19**: correct 19 doc/config drift items so docs match code.
- **L-2→AP-12**: `/health` returns only `{status, version, storage_backend}` (drop git_sha/build_id/environment); keep frontend probe contract.
- **L-3→AP-7**: `_mask` shows first-3/last-2 of API keys → reduce to `****` + last 4.
- **L-4**: `claim_pending_ids` docstring understates CAS/fencing → correct the docstring.

## Constraints
- **No A-1→LM-1 refactor** (two ~670-line functions stay; out of scope by decision).
- Minimal-surface edits: fix the defect, keep surrounding structure; no gratuitous rewrites.
- Match existing code idioms (docstring density, error shapes, i18n key conventions).
- Every behavioral fix must keep the existing test suite green and add/adjust a regression test where the finding named a test point.
- Docs fixes must be **source-of-truth-true**: each correction re-verified against code before writing.
- After fixes: rerun backend baselines (ruff + pytest) and frontend baselines (tsc + eslint). No new lint warnings beyond the pre-existing 16.

## Acceptance
1. TQ-1: expired-lease running row for a dedup key is reclaimable by a new `enqueue`; periodic maintenance re-dispatches instead of stalling; regression test covers the stale-running-dedup path.
2. AP-1: tend progress reports a `dead` count for terminal dead tasks (additive bucket).
3. TQ-2: purge skips storage delete when a live reference to the object re-appears between commit and delete; regression test covers the re-check.
4. AT-1: all 5 tools return a structured missing-field error on absent required args (no KeyError/500).
5. AT-2: hostile CSV header (`x"; SELECT 1 --`) is rejected at column-load time and reconciled SQL is re-validated; no second-statement execution.
6. AT-5: `next_offset` advances by the full fetched page; `has_more` reflects the page-full condition; paging stays monotonic.
7. FR-1: render exception in a lazy page shows a recoverable error UI, not a blank screen.
8. FR-2: toggles still update in-memory state when localStorage throws.
9. FR-3: cursor-less event replayed on reconnect is not re-applied (fingerprint dedup).
10. FR-5: light-mode `--fg-subtle` reaches ≥4.5:1 on white (slate-500).
11. FR-6/FR-7: en locale shows no Chinese; zh unchanged; keys in i18n dict + type.
12. VW-4: renderKey changes at most at render completion (not per page); useQuoteJump no longer re-runs mid-render.
13. D1–D19: each doc statement matches code; re-checked by grep after edit.
14. L-2→AP-12: `/health` JSON = `{status, version, storage_backend}`; openapi.d.ts resynced; frontend probe + Overview/StatusBar still pass.
15. L-3→AP-7: mask output `****<last4>` for keys > 6 chars.
16. L-4: docstring accurately describes CAS (`mark_running`) + fencing.
17. Backend: `ruff check` clean; `pytest` 753 passed (adjusted count if tests added); frontend `tsc -b --noEmit && eslint` 0 errors / ≤16 warnings.
18. All changes committed on `v4.0` with a clear message; review findings listed in the commit body.
