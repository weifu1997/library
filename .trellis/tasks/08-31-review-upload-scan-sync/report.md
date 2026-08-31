# Review report — upload / scan / sync

Prefix: `UPLOAD-*`. Report-only; no product code was modified.

Parent: `08-31-feature-code-review`. Protocol: `research/review-protocol.md`.

---

## 1. Coverage and method

In-scope files were **fully line-read** (none had a >200-line function that was skipped):

| File | Lines | Depth |
|---|---:|---|
| `src/library/services/upload.py` | 547 | line-read (`upload` ~165 lines) |
| `src/library/api/routes_upload.py` | 314 | line-read |
| `src/library/upload_limits.py` | 201 | line-read |
| `src/library/services/user_files.py` | 539 | line-read |
| `src/library/api/routes_user_files.py` | 375 | line-read |
| `src/library/services/scan.py` | 212 | line-read (`scan_vault` ~95 lines) |
| `src/library/services/sync.py` | 401 | line-read |
| `src/library/services/reprocess.py` | 137 | line-read |
| `src/library/services/attachments.py` | 161 | line-read |
| `src/library/tasks/handlers/bulk_reprocess_files.py` | 120 | line-read |

Adjacent (read to trace contracts, not owned as extra surface): `services/folders.py` (`split_remote_path`, `_find_or_create_child`), `storage/sanitize.py`, `storage/mirror.py` `put`/`_abs`, `tasks/enqueue.py`, `tasks/handlers/ingest_file.py` write-once lock, `api/routes_files.py` reprocess routes, `api/routes_agent.py` attachment GET.

Pattern scan on the in-scope set: `except Exception` / `except:`, path join, `enqueue(` without `dedup_key`, `TODO`/`FIXME` (none), raw SQL (none).

Read-only signals:

```
git status --short          # product paths clean; only untracked .trellis/tasks/* (+ unrelated package-lock.json)
uv run pytest tests/ -k "upload or user_files or scan or sync or reprocess" --collect-only
  → 295 selected / 657 collected
uv run pytest tests/test_import_cycles_unit.py
  → 8 passed
```

`test_user_mgmt_e2e.py` is listed in the child PRD but is folder/entry mutation (library-org). It was not treated as a skip of this surface; it is not an upload/scan/sync owner.

---

## 2. Regression

| Prior item | Status | Evidence |
|---|---|---|
| `user_files` import cycle (`08-31-break-user-files-import-cycle`) | **Still fixed** | `src/library/services/exports.py:33-40` still lazy-imports `user_files`. `user_files.py` imports `library.pipelines.registry` (not the package `__init__` that loads `archive`). `tests/test_import_cycles_unit.py` still parametrizes `library.services.user_files` in a fresh subprocess. `uv run pytest tests/test_import_cycles_unit.py` → **8 passed**. Original failure (`import library.services.user_files` as the first import) no longer holds. |

Do not re-open. No other Fixed-table rows belong to this child.

---

## 3. Findings by severity

### High

#### UPLOAD-1 — `apply_modified` does not clear `ingested_at` and enqueues ingest without `dedup_key`

- **Where:** `src/library/services/sync.py:344-355`; write-once lock `src/library/tasks/handlers/ingest_file.py:74-77` and `:271-277`. Contrast the working primitive `src/library/services/reprocess.py:99-122`.
- **Failure scenario:** Mirror vault. File already ingested (`ingest_status=done`, `ingested_at` set, summary populated). User edits the file in Finder. `/check` classifies it as `modified`. `/ingest --all` / `/sync` calls `apply_modified`, which:
  1. updates `sha256` / `size_bytes`;
  2. sets `ingest_status='pending'`;
  3. **clears `summary` and `description`**;
  4. **leaves `ingested_at` set**;
  5. `enqueue(KIND_INGEST_FILE)` **with no `dedup_key`**.
  The worker then runs `ingest_file`: status is not `done`, so it does not skip; it pays for a full pipeline run on the **new** bytes; `_persist` sees `ingested_at is not None` and **refuses to write** `summary` / `description` / `kind` / `extra`; it still sets `ingest_status='done'`. Scan is now `in_sync`, so `/check` looks clean. The Library label card shows an empty summary. Old tags are not purged (unlike `reprocess_file`). A second `/sync` of the same report, or an overlapping in-flight ingest, can insert a **duplicate** `ingest_file` row for the same `file_id`.
- **Why High:** Realistic default path (Finder edit + `/sync`). User-visible empty metadata after a reported-successful apply. Duplicate enqueue is the extra angle this child was asked to settle.
- **Suggested fix:** After updating hash/size, call `reprocess_file` (clears `ingested_at`, purges tags/relations, uses `dedup_key=f"ingest_file:{file_id}"`), or at minimum set `ingested_at=None` and pass that dedup key. Residual race if a *running* ingest still holds a snapshot of the old bytes — document or cancel/fence that delivery (worker child owns fencing). Add a test that runs the ingest handler after `apply_modified` and asserts the new summary is persisted.

### Medium

#### UPLOAD-2 — Upload auto-create stores unsanitized folder names; mirror disk uses `sanitize_folder`

- **Where:** `src/library/services/upload.py:230-237` passes raw `folder_segments` into `resolve_or_create_folder` and into `folder_display_path`. `src/library/services/folders.py:126-152` (`_find_or_create_child`) does **not** call `_validate_folder_name` (`folders.py:31-38`, used only by explicit create/rename). Disk path is computed in `storage/mirror.py:83-86` via `sanitize_folder` / `sanitize_name` (`storage/sanitize.py:42-48`, `:76-89`).
- **Failure scenario:** `POST /v1/upload?remote_path=/My:Notes/doc.txt` with `STORAGE_BACKEND=mirror`. DB folder name stays `My:Notes`. Vault directory becomes `My_Notes` (`:` → `_`). `files.storage_key` is the sanitized path; `folders.name` is not. Every later `scan_vault` builds `expected_rel` from DB names (`scan.py:69-76`) → `My:Notes/doc.txt`, misses the disk file, then pass 2a matches `storage_key` and reports a **false `moved`**. `/sync` `apply_moved` then creates a second folder `My_Notes` and relocates the entry, leaving an empty `My:Notes`. The same split happens for `..` / `.` (sanitize `rstrip(" .")` turns them into `unnamed`) and other Windows-illegal characters.
- **Suggested fix:** Sanitize each auto-created folder segment with the same `sanitize_name` (or `_validate_folder_name` plus the portable rules) **before** insert, and pass the sanitized path as `folder_display_path`. Reject or collapse `..` / `.` at `split_remote_path`. Test: upload `remote_path=/foo:bar/a.txt` in mirror mode, then `scan_vault` → `in_sync` with a single folder whose name matches the vault directory.

#### UPLOAD-3 — Folder zip download materializes every member and the whole archive in memory

- **Where:** `src/library/api/routes_user_files.py:350-363` (`folder_download` → `_zip_stream`).
- **Failure scenario:** `GET /v1/folders/{id}/download` on a folder of large PDFs. Each file is fully `extend`ed into a `bytearray`, `ZipFile.writestr` copies it again, and the complete zip sits in a `BytesIO` before the first response chunk is yielded. A few-GB folder OOMs the API process. Zip-slip of member names is already neutralized (`user_files.py:396-410`, tested in `test_mirror_consistency_regressions_e2e.py`).
- **Suggested fix:** Stream members with `ZipFile.open` / a spooling temp file, or cap total uncompressed bytes and return 413. Test with a fake storage that records peak buffer size.

### Low

#### UPLOAD-4 — `conversation_id` is joined into the attachments path without sanitizing

- **Where:** `src/library/services/attachments.py:62-63` (`_conversation_dir`); `read_attachment` at `:150-157` only `relative_to(conv_dir)`, not `attachments_root`. Served by `GET /v1/conversations/{conversation_id}/attachments/{name}` in `api/routes_agent.py:260-276` (route lives in agent-chat; the join is this child's service).
- **Failure scenario:** `name` is locked to `^\d+\.(png|jpe?g|gif|webp)$` (tested). `conversation_id` is a FastAPI `{param}` (`[^/]+`), so it **cannot contain slashes** — `GET .../conversations/../..//etc/attachments/1.png` and `%2F`-encoded slashes **404** (no `:path` converter). The remaining HTTP vector is a single-segment `..`: `GET /v1/conversations/%2e%2e/attachments/1.png` binds `conversation_id=".."`, `Path(attachments_root) / ".."` resolves to `library_home`, and `relative_to(conv_dir)` succeeds, so `library_home/1.png` is served if that file exists. Default installs may run without a bearer token. Cannot reach `/etc` or walk more than one directory above `attachments/`. Filename-constrained, so not arbitrary-file read.
- **Why Low (was Medium):** The Medium write-up assumed slash-bearing `conversation_id` values reach the join. They do not. Residual is a one-level escape to `library_home/<digits>.<img>`, which is a real unsanitized join but not a realistic sensitive-file leak.
- **Suggested fix:** Require `conversation_id` to match the generated UUID shape (or at least reject `..` / `.`). After resolve, `relative_to(attachments_root(...).resolve())`. Extend `test_chat_attachments_e2e.py::test_bad_names_rejected` with `conversation_id=%2e%2e`.

#### UPLOAD-5 — One unreadable vault file aborts the entire scan

- **Where:** `src/library/services/scan.py:153-166` (`_walk_and_hash`).
- **Failure scenario:** A single permission-denied or disappearing file under the vault raises out of `path.open`, so `/check` returns no report instead of hashing the rest and listing that path as a failure. `/sync` cannot run.
- **Suggested fix:** Per-file try/except, collect errors on `ScanReport`, continue. Test with a chmod-0 file (or a mock `open`).

#### UPLOAD-6 — `reprocess_file` documents “None if deduped”; enqueue returns the existing task, so `reused` is almost never true

- **Where:** `src/library/services/reprocess.py:81-83`; consumer `src/library/api/routes_files.py:52-58` (`reused: task_id is None`). `enqueue` (`tasks/enqueue.py:30-36`) returns the live pending/running row, not `None`.
- **Failure scenario:** User hits Reprocess while an `ingest_file` for that file is already pending. Tags/relations/`ingested_at` are cleared (good), the existing task id is returned, and the JSON says `"reused": false`. Clients that poll “new task” vs “reused” get the wrong signal. `None` only happens on the narrow insert-conflict-then-row-gone race.
- **Suggested fix:** Return `(task_id, reused)` from `reprocess_file` (compare id to a pre-lookup, as `bulk_reprocess_files.py:71-83` already does), or document that a non-null `task_id` may be a reused delivery. Align the route.

---

## 4. Checked, no issue

Must-include extra angles:

- **Upload failure compensation — no issue.** After `storage.put`, `upload()` wraps the DB work in `except BaseException` and `storage.delete`s the tentative key (`upload.py:344-354`); a failed delete is swallowed so the original error is preserved. Dedup hits delete the temp object *before* `_create_dedup_entry` and leave `UploadResult.storage_key` unset, so commit compensation cannot delete the shared live object (`upload.py:77-79`, `:308-319`, `:539-546`). Skip/error policies return before `put`. Capacity rejection is after `put` and therefore compensated; tested in `test_new_upload_capacity_rejects_and_removes_written_object`. Route-level `_commit_upload` (`routes_upload.py:147-177`) rolls back, then deletes only if a verification session shows the key unreferenced; `CancelledError` preserves the object (tested). `_SizeCappedStorage` deletes the partial object when the byte cap trips (`routes_upload.py:87-91`). Middleware 413 (`upload_limits.py`) rejects before spooling. Orphans from a failed *compensation* delete are acknowledged in comments as later-reconciliation; that is intentional, not a hole in the commit path.

- **Scan miss / duplicate enqueue — mixed, explicit.**
  - **Missed files in the diff:** `scan_vault` does not silently drop live, non-dot vault files. Pass 1 claims exact path+hash (in_sync) or path+different hash (modified) before any mover search; pass 2a lets an entry keep its own `storage_key`; pass 2b will not steal a path already in `seen_disk_paths` / prefers non-`owned_paths` (`scan.py:78-144`). Duplicate sha256s in mirror mode (dedup off) are handled; a deleted copy of a still-present duplicate is `missing`, not a move onto the survivor (`test_mirror_consistency_regressions_e2e.py` case 7). **Documented skip:** any path component starting with `.` (`scan.py:156-160`), including `.part-*` temps — intentional. Hidden user files (`.env`) need an explicit `/upload`.
  - **Duplicate ingest enqueue:** `adopt_disk_file` (`sync.py:145-148`) omits `dedup_key`, but each adopt mints a new `file_id` and `files.storage_key` is UNIQUE, so a second adopt of the same disk path fails rather than double-enqueue. **`apply_modified` is the duplicate-enqueue hole** — see UPLOAD-1. Upload and `reprocess_file` both use `ingest_file:{file_id}`.

Other checked items:

- **API input → storage key (path traversal of backends is cross-cutting).** `split_remote_path` drops empty segments (`folders.py:88`). Mirror `put` **ignores** the UUID tentative key and builds `sanitize_folder(folder_path) + sanitize_name(display_name)` (`mirror.py:79-86`); `..` rstrip-dots to `unnamed`, `/` `\` become `_`. Local/S3 keys are `storage_prefix(file_id)` (`upload.py:103-105`) and `_path`/`_abs` refuse escapes (storage child). This surface does not pass a raw `../` string through as a mirror storage key. Residual is UPLOAD-2 (DB folder names not sanitized), not a disk escape.
- **Sha256 dedup (non-mirror):** live rows only (`files.get_by_sha256`); soft-deleted files do not capture a replacement upload (tested). Mirror skips content dedup by design (`upload.py:289-294`) via `isinstance(storage, MirrorStorage)`; `_SizeCappedStorage.__class__` masquerade keeps that check working (`routes_upload.py:79-82`).
- **Name-conflict policies** rename / error / skip match the upload e2e contract; skip/error short-circuit before reading bytes.
- **Zip-slip on folder download** — `_safe_zip_component` strips separators and `..` (`user_files.py:396-410`); covered.
- **Attachment `name` traversal** — `_NAME_RE` + resolve `relative_to(conv_dir)`; `test_bad_names_rejected` covers `../../etc/passwd` as *name*. conversation_id is UPLOAD-4.
- **Range requests** on `/file-entries/{id}/content` parse a single `bytes=` range, 416 with `Content-Range: bytes */N`, suffix/open ranges (`routes_user_files.py:259-309`); e2e in `test_user_files_e2e.py`.
- **Soft-deleted entries** excluded from search / metadata / download (404).
- **Bulk reprocess paging** uses stable `File.id` cursor, `distinct()`, includes the folder itself via `list_live_descendant_ids`, checkpoints on the dispatcher payload (`bulk_reprocess_files.py:53-106`). Scope validation lives in `routes_files.py` (adjacent).
- **`apply_all` category overlap:** scan partitions new/moved/modified/missing; `asyncio.gather` of the four appliers does not double-apply the same entry. Concurrent `resolve_or_create_folder` on a shared new path can IntegrityError one item; that is collected as `SyncFailure`, not silent success.
- **No `TODO`/`FIXME`** in the in-scope files.

---

## 5. Test gaps

| Gap | Why it matters |
|---|---|
| No test runs `ingest_file` after `apply_modified` | Would have caught UPLOAD-1. `test_scan_sync_e2e.py` sets `WORKER_ENABLED=false` and only asserts scan counts + entry identity. |
| No test that `apply_modified` / `adopt_disk_file` pass `dedup_key` | Duplicate-enqueue extra angle is untested. |
| No mirror upload with `:` / `..` in `remote_path` then `scan_vault` | Would have caught UPLOAD-2. |
| Attachment tests do not pass `conversation_id=%2e%2e` | UPLOAD-4 (slash-bearing ids 404; this is the remaining vector). |
| Folder-download tests cover zip-slip, not memory/size | UPLOAD-3. |
| `test_user_files_e2e.py` header still says metadata must not include `extra` / `tags`; the handler returns both (`user_files.py:224-228`) and the assertions only forbid `catalog_id` / `description` / `kind` / `entry_tags` | Stale contract comment, not a product bug. |
| Scan/sync/upload/user_files/reprocess e2e modules are script-style (`main` / `_main`) collected via `conftest.py::pytest_pycollect_makeitem` | They *do* run under pytest (confirmed in `--collect-only`). Not a gap; do not “fix” by rewriting in this round. |

---

## 6. Suggested fix children

Do **not** create these in this round.

| Title | Owning files | Why |
|---|---|---|
| Fix mirror in-place edit re-ingest (`apply_modified` write-once + dedup) | `services/sync.py`; test next to `test_scan_sync_e2e.py` / `test_sync_failure_e2e.py` | UPLOAD-1. One verifiable cluster: after Finder edit + apply, new summary is stored and only one `ingest_file` row exists. |
| Sanitize upload auto-created folder names to match mirror disk | `services/folders.py`, `services/upload.py`; mirror scan e2e | UPLOAD-2. |
| Stream or cap folder zip download | `api/routes_user_files.py` | UPLOAD-3. |
| Reject traversing `conversation_id` in attachments | `services/attachments.py` (+ agent route test) | UPLOAD-4. |
| (optional, can fold) Align `reprocess_file` reused contract | `services/reprocess.py`, `api/routes_files.py` | UPLOAD-6. |
| (optional) Per-file scan hash errors | `services/scan.py` | UPLOAD-5. |

Do not bundle UPLOAD-1 with a scan rewrite or with folder-zip streaming.

---

## 7. Five-angle table

| Angle | Conclusion |
|---|---|
| **Correctness** | Upload transaction/dedup/compensation is sound (see §4). Scan classification of new/moved/missing/modified is sound and does not miss live non-dot files. **`apply_modified` fails to re-index in-place edits** (UPLOAD-1) and can duplicate ingest tasks. Upload auto-create can desync DB folder names from the vault (UPLOAD-2). Reprocess primitive itself clears `ingested_at` and uses the canonical dedup key. |
| **Security** | Mirror/local storage keys from this surface are sanitized or UUID-sharded; physical backend traversal stays with cross-cutting. Folder zip members cannot zip-slip. Attachment **filenames** cannot traverse. FastAPI `{conversation_id}` cannot contain slashes (404); a single-segment `%2e%2e` still joins to `library_home/<n>.<img>` (UPLOAD-4, Low). Auth on these routes is process-wide (cross-cutting). |
| **Architecture / maintainability** | Cycle break (lazy `exports` import) still holds. `user_files` defers `recommend` / `webdav_sync`. Folder zip is unbounded in memory (UPLOAD-3). `_SizeCappedStorage.__class__` hack is documented and necessary for mirror isinstance. `apply_modified` should reuse `reprocess_file` instead of a partial ingest reset. |
| **Spec / contract** | Upload response matches `schemas/upload.py`. Search response matches `schemas/user_files.py` (no summary leak). Metadata *does* return `summary` / `tags` / `extra` by DESIGN.md §14.3 carve-out; e2e header comment is stale. `reprocess_file` docstring vs `enqueue` vs `reused` flag disagree (UPLOAD-6). Backend spec files under `.trellis/spec/backend/` are still stubs; no extra spec violation beyond that. |
| **Tests** | Compensation, capacity, middleware 413, dedup-vs-deleted, dedup follow-up kinds, import cycles, scan four-way classify, sync failure collection, bulk reprocess paging, attachment name traversal, zip-slip are covered. Missing: ingest-after-`apply_modified`, folder-name sanitization vs scan, conversation_id traversal, zip memory bound (see §5). |
