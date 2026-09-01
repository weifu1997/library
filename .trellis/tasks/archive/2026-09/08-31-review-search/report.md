# Review report — search (FTS / semantic / rerank)

Report-only. No product code was modified.
Review date: 2026-08-31. Scope: child `08-31-review-search`.

## 1. Coverage and method

Hook injection did not fire; context was loaded from `implement.jsonl`, this child's `prd.md` / `implement.md`, and parent `research/review-protocol.md` + `research/prior-findings.md`.

Pattern scan on every in-scope file: `except Exception`, path join, raw SQL, unauthenticated route surface, lock/cache, MATCH/LIKE construction.

### `semantic/index.py` (1872 lines) — function coverage

| Function | Lines | Method |
|---|---|---|
| `semantic_index_root` / `semantic_index_dir` / `semantic_recall_configured` / `semantic_index_status` / `sqlite_vec_available` | 105–146 | line-read |
| `_index_write_lock` / `_acquire_index_lock` / `_release_index_lock` / `_index_file_lock` | 160–236 | line-read |
| `build_semantic_index` | 238–283 | line-read |
| `_build_semantic_index` | 286–511 | **line-read** (226 lines; oversized) |
| `refresh_semantic_index_for_file` | 514–528 | line-read |
| `_refresh_semantic_index_for_file` | 531–787 | **line-read** (257 lines; oversized) |
| `_semantic_metadata` / `_embed_batch` / `_resume_state` | 790–861 | line-read |
| `search_semantic_index` / `search_semantic_index_many` | 864–934 | line-read |
| `semantic_entry_rows` / `best_semantic_sections` | 937–1033 | line-read |
| `_embed_queries_cached` / `_read_query_cache` / `_query_cache_key` | 1036–1122 | line-read |
| `_semantic_index_exists` / `_read_manifest` / `_manifest_matches_settings` | 1125–1159 | line-read |
| `_replace_file_index` | 1162–1185 | line-read |
| sqlite-vec helpers (`_should_*`, `_connect_sqlite_vec`, `_write_sqlite_vec_index`, `_search_sqlite_vec_index`) | 1188–1458 | line-read |
| `_load_semantic_index` / `_load_semantic_index_cached` / `_semantic_hits_from_scores` | 1460–1528 | line-read |
| `_load_indexable_entries` / `_iter_semantic_input_pages` | 1531–1600 | line-read |
| `_semantic_inputs` / section text / `_entry_text` / scoring / `_normalize` | 1603–1872 | line-read |

No function in this file was structural-scan-only. The two >200-line functions were read in full.

### Other in-scope files

| File | Lines | Method |
|---|---|---|
| `src/library/semantic/embeddings.py` | 253 | line-read |
| `src/library/semantic/rerank.py` | 164 | line-read |
| `src/library/db/fts.py` | 11 | line-read (constants only) |
| `src/library/repositories/entries.py` FTS/search | 1–340, 420–653 | line-read (actual FTS query path; `fts.py` is names only) |
| `src/library/db/bootstrap.py` `_ensure_entry_metadata_fts*` | 385–557 | line-read (migration semantics; files themselves owned by cross-cutting) |
| `src/library/api/routes_semantic_index.py` | 57 | line-read |
| `src/library/agent/text_query.py` | 62 | line-read (tokenizer, not the runtime loop) |
| `src/library/agent/tools/search_metadata.py` | 471 | line-read (FTS consumer) |
| `src/library/agent/tools/recall_knowledge.py` retrieval/rerank | 1–670 | line-read (semantic/FTS merge + rerank; runtime loop out of scope) |
| `src/library/services/user_files.py` `search_entries` | 92–149 | line-read (GUI FTS entry) |
| `src/library/tasks/handlers/rebuild_semantic_index.py` | 45 | line-read |
| `src/library/tasks/handlers/refresh_semantic_file.py` | 48 | line-read |
| `src/library/tasks/handlers/ingest_file.py` `_refresh_semantic_index` | 169–199 | line-read (snapshot consistency) |

### Tests consulted (not executed beyond `--collect-only`)

`test_semantic_index_unit.py`, `test_semantic_rebuild_resume_unit.py`, `test_entry_metadata_fts_unit.py`, `test_gui_search_multiword_unit.py`, `test_search_metadata_ranking_unit.py`, `test_search_and_misc_regressions_unit.py` (FTS/semantic sections; **not selected** by the validation `-k` expression), `test_eval_ranking_unit.py` (RRF/quota shape only), `test_recall_knowledge_unit.py` (`test_recall_knowledge_skips_semantic_without_embedding_key`).

Validation:

```
git status --short
uv run pytest tests/ -k "semantic or fts or search_metadata or gui_search" --collect-only
```

Result: 28 tests collected (plus incidental MCP/migration/upload name matches). Product tree clean; only untracked `.trellis/tasks/*` and `package-lock.json`.

## 2. Regression

No prior **fixed** item in `prior-findings.md` is owned by this child.

| ID | Notes |
|---|---|
| A-1 oversized `semantic/index.py` | Still true. Architecture, not a regression of a fix. Re-filed as SEARCH-7. |
| A-2 `except Exception` density | Concrete swallows in this surface are called out where they hide degradation (SEARCH-8). SEARCH-5 is a re-raise after publish, not a swallow. |

Historical search bugs that **do** still have tests and whose original failure no longer holds (not regressions): empty `entry_ids` is not a full scan; first refresh enqueues a full rebuild; zero-length query vectors are not cached; resume state is bound to embedding config; short CJK / short ASCII terms are LIKE-rescued; LIKE wildcards are escaped.

## 3. Findings

### SEARCH-1 — High — non-atomic three-file publish; readers are unlocked

- **Where:** `src/library/semantic/index.py:1183-1185` (`_replace_file_index`); same pattern at `:466-468` (`_build_semantic_index`).
- **Failure scenario:** Refresh (default ingest path) writes `entries.jsonl`, then `vectors.f32`, then `manifest.json` via three separate `Path.replace` calls. Search never takes the write lock (`search_semantic_index_many` at `:880`). If the process is killed after the metadata replace and before the vector replace, on-disk metadata order is the new `[kept…, refreshed…]` layout while vectors are still the old layout. `_load_semantic_index_cached` (`:1494`) only caps by `min(count, len(metadata), len(vectors)//dim)` — it cannot detect a permutation. Semantic hits are then the wrong documents with confident scores. The next file refresh reads that misaligned pair (`:651-680`) and can persist/worsen the corruption; sqlite-vec, if present, is rebuilt from the file index (`:1290`) and becomes wrong too.
- **Suggested fix:** Publish one generation directory (or a single pack file) and `os.replace` the directory/pack atomically. On load, refuse to search unless `len(metadata) == len(vectors)//dim == manifest.entries` **and** a checksum/generation recorded in the manifest matches both files. Readers should either take a shared lock or read a generation that cannot tear.

### SEARCH-2 — Medium — task resume cannot recover from partial JSON or vanished records

- **Where:** `_read_metadata` `src/library/semantic/index.py:1810-1816`; vanished-record check `:418-422`; handler `src/library/tasks/handlers/rebuild_semantic_index.py:28-29`.
- **Failure scenario A:** Worker dies mid-batch. `meta_f.flush()` runs only after the whole batch (`:410-411`), so `entries.jsonl{resume_key}.tmp` can end with a truncated JSON line. `_resume_state` → `_read_metadata` → `json.loads` raises. The handler always sets `resume=True` with `resume_key=task_id`, so the automatic retry hits the same corrupt tmp and fails again (`max_attempts=2`).
- **Failure scenario B:** Resume tmp contains a record that was deleted/demoted while the rebuild was down. `:418-422` raises `ValueError("…restart the rebuild without resume")`, but the task cannot turn resume off. A *new* task id (user clicks Rebuild again after the old task is dead) starts clean; the same task cannot.
- **Suggested fix:** Treat JSON decode errors and `done_ids - seen_record_ids` as “discard resume state and start over” inside `_resume_state` / `_build_semantic_index`. Do not require a human to enqueue a new task.

### SEARCH-3 — Medium — `index_name` sanitizer allows `..` to escape the index root

- **Where:** `src/library/semantic/index.py:109-111`; accepted by `POST /v1/semantic-index/rebuild` `src/library/api/routes_semantic_index.py:19-47`. No later `Path.resolve()` / `relative_to()` containment check in this module (lock mkdir `:221-224`, build mkdir `:309-310`, publish `:1169`).
- **Failure scenario:** `index_name=".."` survives the alnum/`-_.` filter (`"."` is allowed). `semantic_index_root() / ".."` is `library_home` (one level up; `"../x"` becomes `".._x"` because `/` is rewritten). Rebuild then writes `entries.jsonl` / `vectors.f32` / `manifest.json` / `.write.lock` into the library home, and `_cleanup_stale_tmps` (`:1209-1226`) unlinks matching `entries.jsonl*.tmp` / `vectors.f32*.tmp` / `manifest.json*.tmp` names there. `index_name="."` stays inside `semantic-index/` (not an escape). Default GUI does not send `index_name` (client posts `{concurrency}` only), but the API default is only applied when the field is omitted; a crafted body still wins. Auth is optional (`LIBRARY_API_TOKEN` unset is the documented default).
- **Suggested fix:** Reject names that are `.`/`..`, contain a path separator after sanitizing, or whose resolved path is not a subpath of `semantic_index_root()`. Pin the API to `DEFAULT_INDEX_NAME` until multiple indexes are a real feature.

### SEARCH-4 — Medium — incompatible semantic index returns empty hits with no `degraded` signal on the recall path

- **Where:** `search_semantic_index_many` `src/library/semantic/index.py:894-896`; consumed by `semantic_entry_rows` and `recall_knowledge` `src/library/agent/tools/recall_knowledge.py:165-179`.
- **Failure scenario:** User changes `EMBEDDING_MODEL` / dimensions in Settings. `needs_rebuild` is true on `/v1/semantic-index/status` and the Settings page, but `recall_knowledge` only adds `degraded` when `semantic_entry_rows` *raises*. An incompatible manifest returns `[]`, so `trace.semantic` is `0` with an empty `degraded` list — indistinguishable from “the corpus has no semantic matches”. (Missing API key is different and already handled: `semantic_recall_configured()` skips the call entirely; covered by `test_recall_knowledge_skips_semantic_without_embedding_key`.) Until something ingests (refresh enqueues rebuild) or the user clicks Rebuild, this lasts.
- **Suggested fix:** Have `search_semantic_index_many` / `semantic_entry_rows` return a reason (`index_incompatible`, `index_missing`) and have `recall_knowledge` append that to `trace.degraded`. Do not pretend a miss is an empty corpus.

### SEARCH-5 — Medium — `SEMANTIC_INDEX_BACKEND=sqlite-vec` without the extra fails the rebuild *after* embeddings are paid, then retries re-embed

- **Where:** `src/library/semantic/index.py:489-494` and `_connect_sqlite_vec` `:1266-1273`.
- **Failure scenario:** File index is already published (`:466-468`). sqlite-vec load then raises `RuntimeError("sqlite-vec is not installed…")`. Because backend is `sqlite-vec` (not `auto`), the exception is re-raised and the task fails. Resume tmp files were `replace`d away, so the retry starts from scratch and re-calls the embedding API for the whole library. `auto` correctly falls back (`:495-501`); the forced backend does not.
- **Suggested fix:** If sqlite-vec is missing, fail *before* embedding (status/rebuild 400), or fall back to the already-published file index and record `degraded` instead of re-raising after publish.

### SEARCH-6 — Low — query cache append is unlocked; JSONL can tear under concurrent searches

- **Where:** `src/library/semantic/index.py:1060-1089`.
- **Failure scenario:** Two uncached queries in different tasks/processes append vectors (1024 floats ≫ PIPE_BUF) to `query_cache.jsonl`. A torn line is skipped by `_read_query_cache` (`:1103-1104`), so this degrades to a cache miss rather than a wrong hit. Unbounded growth is also unaddressed (rebuild does not truncate the cache).
- **Suggested fix:** Same file lock as writers, or a sidecar sqlite; skip cache write on empty vectors (already done); cap/rotate the file.

### SEARCH-7 — Low — A-1 still open: oversized semantic index module / functions

- **Where:** `src/library/semantic/index.py` 1872 lines; `_build_semantic_index` 286–511; `_refresh_semantic_index_for_file` 531–787.
- **Failure scenario:** Not a runtime failure. The file owns locks, resume, two backends, search, cache, section text, and enqueue. That is why SEARCH-1/2/5 live in the same function as publish.
- **Suggested fix:** Split publish/load, sqlite-vec, and search/cache. Do not mix that refactor with a crash-consistency fix.

### SEARCH-8 — Low — sqlite-vec search errors in `auto` are swallowed with no log

- **Where:** `src/library/semantic/index.py:915-917` (search); build/refresh at least print to stderr (`:498-501`, `:774-777`).
- **Failure scenario:** Corrupt `vectors.sqlite` with `backend=auto` falls back to the file index. Correct, but operators cannot see it (no `logging` call, nothing in `semantic_index_status`).
- **Suggested fix:** `log.warning` + a `backend_live` / `sqlite_vec_available` field on `semantic_index_status`.

## 4. Checked, no issue

Must-cover items from the extra angles:

| Topic | Conclusion |
|---|---|
| **FTS path** | SQLite FTS5 trigram + quoted phrases (`_quote_fts_phrase`) is not MATCH-injection-prone. Short ASCII/CJK terms are OR'd back via escaped LIKE (`_metadata_short_like_terms`, `_escape_like_term`). Triggers keep `entry_metadata_fts` in sync on insert/update/delete of entries and on file summary/description/extra/ext updates. Soft-deleted rows can remain in FTS but `search_filtered` applies `_live_entry()` / `_live_file()`. GUI `search_entries` tokenizes with `normalize_text_queries` then `search_filtered` (BM25 unless mixed short-LIKE, which ranks by `updated_at` — intentional). Postgres uses `websearch_to_tsquery('simple')` plus ILIKE for CJK; substring-vs-token mismatch vs SQLite trigram is a known dialect difference, not a SQLite bug. |
| **Semantic path** | Empty `entry_ids` does not wipe/scan the library. Missing index → refresh enqueues a full rebuild rather than a one-file index. Zero-entry build removes the index instead of writing `dimensions=0`. Manifest mismatch on refresh enqueues rebuild and does not mix vector spaces. Hits are deduped per `entry_id` (best section wins). In-process writers are serialized by asyncio lock + flock. |
| **sqlite-vec off** | `backend=auto` and package missing: file index is used; search does not raise. `backend=file`: sqlite-vec is never built. Embedding off (`semantic_recall_enabled` false or no key): `recall_knowledge` skips semantic; ingest refresh returns `skipped_reason=semantic_recall_not_configured` and audits `semantic_index_refresh_deferred`. Stats overview exposes `semantic.enabled` / `configured` / `index_ready`. Forced `backend=sqlite-vec` without the extra is SEARCH-5, not a silent miss. |
| **Query cache** | Key includes provider/model/dimensions/`query`/text_type. Settings change ⇒ new key; old JSONL rows are ignored. Empty vectors are not written (`:1072-1076`) and are ignored on read (`:1107-1110`). Staleness vs the *index* is not a bug (query embeddings do not depend on document vectors). Remaining issues are SEARCH-6 (concurrency/growth), not dirty hits after a model change. |
| **Locks** | Same-worker rebuild vs refresh: asyncio lock has no timeout, so ingest refresh waits and then patches files missed by the long-running snapshot transaction. Cross-process flock timeout is 300s (`:182`) — relevant for CLI rebuild vs worker refresh, not the default in-process runner. |
| **Index vs file snapshot** | Refresh deletes by `file_id` / live `entry_id` then re-embeds current DB text (capped at 6000 chars). Ingest calls refresh after persist. Rebuild pages by `FileEntry.id` in one session/transaction (SQLite snapshot); post-rebuild refreshes fill gaps if they acquire the lock. Crash window during publish is SEARCH-1. |
| **Rerank** | Provider failures become `RerankProviderError`; `recall_knowledge` degrades to deterministic order and records `trace.rerank.error`. Default `rerank_batch_size=100` / `rerank_top_n=80` / recall `fetch_limit=100` stays in one batch, so cross-batch `top_n` truncation is not on the default path. |
| **Embeddings** | Vision/LLM keys are not reused (`test_embedding_client_does_not_reuse_vision_key`). Count/dimension mismatches fail the batch. DashScope passes `text_type`; the default `openai-compatible` client does not (OpenAI schema). Quality limitation, not a correctness bug. |
| **Authz on this surface** | Semantic routes sit behind process-wide optional bearer + host allowlist (cross-cutting). No extra per-route auth. Path traversal is SEARCH-3, not an auth bypass. |
| **FTS SQL injection** | User terms are bound as a single quoted phrase list, not concatenated into SQL. LIKE wildcards escaped. |

## 5. Test gaps

- No test that kills/crashes between the three `replace` calls and then searches or refreshes (SEARCH-1).
- No test that `_resume_state` / handler recovers from a truncated JSONL line or from `done_ids` that are no longer indexable (SEARCH-2). Current resume tests only cover config mismatch and `resume_key=task_id`.
- No test that `index_name=".."` / `"."` is rejected (SEARCH-3).
- No test that `recall_knowledge` sets `degraded` when the index exists but is incompatible (SEARCH-4). Existing test only covers missing embedding key (skip, not empty-hit).
- No test that `backend=sqlite-vec` without `sqlite_vec` fails closed *before* embedding, or falls back without a second full embed (SEARCH-5).
- No concurrent `_embed_queries_cached` test (SEARCH-6).
- `test_search_and_misc_regressions_unit.py` is not selected by the PRD validation `-k "semantic or fts or search_metadata or gui_search"` even though it holds several semantic/FTS regressions.
- `search_metadata` in-memory rerank fetches `min(total, max(limit+offset, min(500,total)))` then slices; no test that `offset>=500` ranking/pagination is wrong.
- `best_semantic_sections` always uses the file index even when sqlite-vec is the search backend; no test that section-backfill still works if only `vectors.sqlite` exists.
- Postgres FTS is compile-shape only; no live PG test that `"aft"` does *not* match `raft` (trigram vs token dialect gap).
- No test that `semantic_index_status` reports live backend / sqlite-vec availability.

## 6. Suggested fix children — do not create

| Title | Owning files | Why |
|---|---|---|
| Atomic semantic-index publish + generation check | `src/library/semantic/index.py` (`_replace_file_index`, `_build_semantic_index`, `_load_semantic_index_cached`) | SEARCH-1. Highest user-visible risk: wrong hits that persist. |
| Rebuild resume: treat corrupt/stale tmp as a fresh start | `src/library/semantic/index.py` `_resume_state` / `_read_metadata`; `rebuild_semantic_index.py` | SEARCH-2. |
| Reject `index_name` path traversal | `semantic_index_dir`; `routes_semantic_index.py` | SEARCH-3. |
| Surface semantic skip reasons on search/recall | `search_semantic_index_many`, `recall_knowledge`, `semantic_index_status` | SEARCH-4 + SEARCH-8 observability. |
| Fail sqlite-vec-required builds before embed, or degrade to file | `_build_semantic_index`, `_connect_sqlite_vec`, status API | SEARCH-5. |

Do not bundle SEARCH-7 (module split) with SEARCH-1.

## 7. Five-angle table

| Angle | Conclusion |
|---|---|
| **Correctness** | FTS matching/ranking and the happy-path semantic build/refresh/search are sound and well-tested. Real holes: torn publish (SEARCH-1), resume that cannot self-heal (SEARCH-2), incompatible index presented as “no hits” to the agent (SEARCH-4), sqlite-vec-required rebuild that re-embeds on retry (SEARCH-5). |
| **Security** | FTS MATCH/LIKE are parameterized and quoted/escaped. Embedding/rerank keys are separate from chat/vision. Remaining: `index_name=".."` escapes the index root (SEARCH-3). Route auth is process-wide, not this child's bug. |
| **Architecture / maintainability** | A-1 still open (SEARCH-7). Two backends, resume, cache, and search in one module. File-backend search loads all vectors into an `lru_cache`. `search_with_file` is deprecated leftover in `entries.py`. |
| **Spec / contract** | Rebuild API returns 202 + `task_id` (dedup returns the existing task, not `None`). Status/Settings expose `needs_rebuild` / `compatible`; stats expose `configured` / `index_ready`. Missing contract: live backend, sqlite-vec availability, search skip reason. Frontend rebuild does not send `index_name` (safe default). |
| **Tests** | Strong on FTS CJK/short-term/LIKE-escape, first-refresh-enqueue, empty `entry_ids`, config-mismatch rebuild, query-cache empty vectors, section vectors. Gaps listed in §5, especially crash-consistency and resume failure. |
