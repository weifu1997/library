# Review report — 前端其余页

Parent: `08-31-feature-code-review`. Report-only. No product code was modified.

Chat / Settings pages are out of scope (agent-chat / settings children).

---

## 1. Coverage and method

| File | Depth |
|---|---|
| `pages/LibraryPage.tsx` | line-read selection + metadata effect |
| `pages/SearchPage.tsx` | line-read |
| `pages/OverviewPage.tsx` | line-read |
| `pages/HelpPage.tsx` `AboutPage.tsx` | structural |
| `components/library/FolderTree.tsx` | line-read load / loadDetail |
| `components/library/MetaPanel.tsx` | line-read CoverageNotice |
| `components/library/FileViewer.tsx` | structural (kind dispatch) |
| `components/BackendGate.tsx` | line-read |
| `api/client.ts` | line-read `_request` |
| `types/api.ts` Search/Stats/FileMetadata | line-read |
| `eslint.config.js` `package.json` lint script | line-read |
| `api/routes_stats.py` `schemas/stats.py` | line-read |
| `api/routes_user_files.py` search | line-read |

`npm --prefix frontend run lint` (read-only): **0 errors, 31 warnings** (exactly `--max-warnings 31`).

---

## 2. Regression

| ID | Status |
|---|---|
| **A-3** ESLint + react-hooks | **Still present.** `eslint.config.js` enables `react-hooks` recommended + `@typescript-eslint/no-explicit-any: error`. `package.json` `lint` is `tsc -b --noEmit && eslint . --max-warnings 31`. Not tsc-only anymore. **Not zero warnings:** 31 remain (mostly `react-refresh/only-export-components` in `ViewerShared.tsx`; two `react-hooks/exhaustive-deps`: `ViewerShared.tsx:398`, `SettingsPage.tsx:1269`). Do not re-open A-3 as a missing baseline; residual debt is FE-L2. |
| **Coverage surface** | **Still present.** `MetaPanel.tsx:76` `CoverageNotice`; shows `indexed_partial`, page counts, `ocr_failed_pages`, `partial_reasons` with i18n fallback for unknown keys (`:195-198`). Matches ingest coverage contract. |

---

## 3. Findings by severity

### Critical / High

None.

### Medium

#### FE-M1 — Folder tree `folders.get` / `folders.list` have no in-flight generation guard

- **Where:** `FolderTree.tsx:94-102` `load()`; `FolderRow` `loadDetail` `:359-369`. Contrast `LibraryPage.tsx:155-170` and `SearchPage.tsx:28-45` which use `cancelled`.
- **Failure scenario:** User expands folder A, then quickly expands/collapses or `refreshKey` retriggers. Two `GET /v1/folders/{id}` overlap. The slower response still calls `setChildren` / `setEntries` (`:364-365`) with **no cancelled flag**. The row can show B’s spinner finishing with A’s entries, or a stale listing after a delete+refresh. Root `load()` has the same last-write-wins bug across `refreshKey`.
- **Suggested fix:** Same `cancelled` (or incrementing `reqId`) as Search/Library metadata. AbortSignal on `_request` is nicer but not required for correctness.

#### FE-M2 — Library metadata fetch failures are swallowed

- **Where:** `LibraryPage.tsx:162-164` `.catch(() => { if (!cancelled) setMeta(null); })`.
- **Failure scenario:** `GET /file-entries/{id}/metadata` 500 or network error. Viewer still opens (`FileViewer` with `meta=null`); the right-hand MetaPanel is empty. User cannot tell “this file has no extra fields” from “the request failed.” Search/Overview at least set `error` state.
- **Suggested fix:** `setMetaError` and a retry chip on MetaPanel. Do not treat catch as empty metadata.

### Low

#### FE-L1 — Search empty/results copy is hardcoded Chinese

- **Where:** `SearchPage.tsx:102-103, 128-129, 137` (`输入关键词…`, `找到 {n} 条相关结果`). Placeholder/empty title use `t.search.*`.
- **Failure scenario:** English locale still shows those Chinese sentences. Help/Overview are i18n’d.
- **Suggested fix:** Move the strings into `i18n.ts` `search.*`.

#### FE-L2 — ESLint still allows 31 warnings, including hook deps

- **Where:** `package.json:11` `--max-warnings 31`; `ViewerShared.tsx:398` `applyZoomValue`; `SettingsPage.tsx:1269` `server`.
- **Failure scenario:** A 32nd warning fails CI; the existing exhaustive-deps holes can still ship. A-3’s *baseline* is in place; the budget is the leftover.
- **Suggested fix:** Split refresh-only-export to warn-ignore or move helpers; fix the two hook deps; ratchet `max-warnings` down.

#### FE-L3 — `_request` network failures stay raw `TypeError`

- **Where:** `client.ts:162-164` catch logs and rethrows. HTTP errors become `ApiError` (`:166-182`).
- **Failure scenario:** Backend down / CORS (if H-1 regressed) → UI shows `Failed to fetch` (Search/Overview `e.message`). Not a new CORS bug. BackendGate already special-cases health.
- **Suggested fix:** Wrap fetch failures in `ApiError(0, null, "network")` so pages can i18n one code.

---

## 4. Checked, no issue

### Race (Search / Library metadata / Overview)

- Search debounce 200ms + `cancelled` on effect cleanup (`SearchPage.tsx:28-45`). In-flight fetch is not aborted, but results are not applied after cancel.
- Library metadata uses the same cancelled pattern.
- Overview `load()` has no cancel; a single mount + manual refresh is the only caller — stale overlap is unlikely unless the user hammers refresh (last response wins, same endpoint).

### Coverage UI

- Partial ingest is amber, not red (`MetaPanel.tsx:175-188`). Unknown `partial_reasons` still render.

### OpenAPI / types

- `GET /v1/search` → `SearchResponse` (`routes_user_files.py:45-54`); frontend `SearchResult` / `SearchEntry` are `components["schemas"][...]` (`api.ts:45-47`).
- `GET /v1/stats/overview` → `StatsOverviewResponse` StrictModel (`schemas/stats.py:32-38`); frontend `StatsOverview` omits nothing material (`api.ts:351-352`). Overview fields `totals` / `tasks` / `recent` / `semantic.{enabled,configured,index_ready}` match.
- **Explicit remaining drift:** `GET /v1/discover/{id}` is still `dict[str, Any]` with no `response_model` (`routes_user_files.py:57-64`). The GUI Search page does not call it (related entries come from metadata). `FileMetadata` is handwritten plus `[key: string]: unknown` (`api.ts:71`) — extra backend keys are allowed, missing keys are not type-enforced. Settings GET `/server` extra keys were folded into generated `ServerSettingsResponse` (settings child).

### client.ts HTTP errors

- Non-OK responses parse JSON `detail` into `ApiError`. 204 handled. FormData does not force `Content-Type: application/json`.

### BackendGate

- Polls `/health` with timeout; cancelled on unmount; recovery `clearBaseUrlOverride` when a bad Settings base is stored.

---

## 5. Test gaps

| Gap | Why |
|---|---|
| No frontend test runner | Search cancel, FolderTree overlap, metadata catch — zero assertions (same note as agent-chat SSE). |
| `test_gui_search_multiword_unit.py` is backend FTS | Does not cover SearchPage. |
| `test_ingest_coverage_surface_unit.py` is backend projection | MetaPanel rendering untested. |
| `test_openapi_contract.py` / `test_stats_overview.py` | Cover backend shapes; GUI wiring untested. |
| ESLint warning budget | No test that `max-warnings` only shrinks. |

---

## 6. Suggested follow-up fix children

Do **not** create these in this round.

| Title | Files | Why |
|---|---|---|
| Guard FolderTree in-flight listings | `FolderTree.tsx` | FE-M1 |
| Surface metadata fetch errors | `LibraryPage.tsx`, `MetaPanel.tsx` | FE-M2 |
| i18n leftover SearchPage strings | `SearchPage.tsx`, `i18n.ts` | FE-L1 |
| Ratchet ESLint warnings / fix hook deps | `ViewerShared.tsx`, `SettingsPage.tsx`, `package.json` | FE-L2 |

Do not mix with Chat SSE (already fixed) or Settings LLM editor.

---

## 7. Five-angle conclusions

| Angle | Conclusion |
|---|---|
| **Correctness** | Search/Library metadata ignore stale effects. Folder tree listing does not (FE-M1). Metadata errors look like empty files (FE-M2). Overview numbers match `StatsOverviewResponse`. |
| **Security** | Token in localStorage (same as Chat). Search query is a query string, not innerHTML. Viewer kinds dispatch on extension/mime from metadata, not user HTML. Auth is cross-cutting. |
| **Architecture** | Pages stay local-state; `client.ts` is the only HTTP wrapper. Viewers are split files. `FileMetadata` still a loose handwritten type. |
| **Spec / contract** | Search + Overview are OpenAPI StrictModels and match the GUI. Discover remains untyped. Coverage UI matches ingest `indexed_partial`. |
| **Tests** | Backend stats/openapi/coverage tests exist. No component tests. ESLint is the only frontend gate (31-warning budget). |

---

## Verification

```
git status --short -- src tests frontend openapi
# clean

npm --prefix frontend run lint
# 0 errors, 31 warnings (max-warnings 31)
```
