# Review report — WebDAV sync / import / conflicts

Parent: `08-31-feature-code-review`. Report-only. No product code, tests, configs, OpenAPI, or frontend were modified.

Remote snapshot bytes are treated as untrusted input throughout (path, parent chain, conflict, CHECK/FK fields).

---

## 1. Coverage and method

### In-scope files

| File | Depth |
|---|---|
| `src/library/services/webdav_sync.py` (2500 lines) | mix of line-read and structural scan; see ranges below |
| `src/library/api/routes_webdav_sync.py` (271 lines) | **line-read entire file** |
| `src/library/tasks/handlers/webdav_publish.py` (11 lines) | **line-read entire file** (`handle_webdav_publish` → `publish_snapshot`) |

Out of scope (scanned only to decide): generic folder API; storage backend path resolve. `tests/test_mirror_e2e.py` has no WebDAV protocol coverage. `tests/test_mirror_consistency_regressions_e2e.py::test_non_hydrated_webdav_entry_rename_and_move` is a local-mirror placeholder (`_webdav/<id>`) test, not publish/import; no finding filed here.

Supporting reads (not owned): `repositories/folders.py::would_create_cycle`, `services/knowledge_pack.py` blob/relation export, `schemas/webdav.py`, `periodic_tick.py` auto-sync enqueue.

### `webdav_sync.py` ranges

| Lines | Path | Depth |
|---|---|---|
| 1–87 | module docstring, constants | line-read |
| 93–258 | `WebDavClient` (exists/mkcol/put/move/read/stream_to_storage) | line-read |
| 261–362 | `configured` / `test_connection` / `sync_remote_status` | line-read |
| 364–498 | `publish_snapshot` | **structural scan** (named: remote merge, blob upload, latest.json last) |
| 501–580 | `upload_plan` | structural scan |
| **583–811** | **`publish_selected`** | **line-read entire function (229 lines)** |
| 814–890 | `download_plan` | line-read |
| 892–938 | `download_selected` | line-read |
| 941–1021 | `pull_latest_metadata` | line-read |
| 1024–1113 | `hydrate_entry` | line-read |
| 1116–1176 | `download_latest` | line-read |
| 1179–1207 | `read_status` / `_empty_snapshot` | line-read |
| 1210–1256 | `_read_remote_snapshot` (`allow_missing` / `recover`) | line-read |
| 1259–1449 | `_merge_snapshot_rows` / `_scoped_ancestor_rows` / `_merge_by_key` | line-read |
| 1452–1574 | manifest/jsonl helpers, **`_folder_path_from_export`** (seen-set) | line-read |
| **1577–2126** | **`_import_metadata`** | **line-read entire function (550 lines)** |
| 2129–2200 | library_id ensure/adopt/guard, `_require_same_library`, `_redact_error` | line-read |
| 2203–2324 | status IO, `_parse_jsonl`, UUID/name sanitize | line-read |
| 2327–2341 | `_local_row_wins` | line-read |
| **2344–2360** | **`_nearest_live_folder_id`** | **line-read (AH-1)** |
| **2363–2393** | **`_order_by_parent_chain`** | **line-read (AH-1)** |
| 2396–2444 | coerce helpers, remote marker, placeholder key | line-read |
| **2447–2474** | **`_folder_path`** | **line-read (AH-1)** |
| 2477–2500 | `_join_remote` / `_split_path` / `_encode_path` | line-read |

No `_would_cycle` exists in this file. Import reuses `folders_repo.would_create_cycle` (`webdav_sync.py:1633`). Catalogs have a separate `_would_cycle` in `restructure_catalogs_apply.py` that import does **not** call.

### Pattern scan

Grep across in-scope files: `except Exception`, `parent_id`, `would_create_cycle`, `conflict`, `blob_path`, `latest_snapshot`, `_join_remote`, `..`, `recover`, `scoped`.

### Tests inspected

Collect-only (`uv run pytest tests/ -k "webdav or publish_selected" --collect-only`): **22 selected, 1 skipped at collection**, 635 deselected.

Selected: 10 conflict-guard e2e (including AH-1), 9 sync e2e, 1 publish-selected scope, 1 mirror placeholder, 1 import-cycle unit for `webdav_sync`.

Did **not** claim “100% tests / no skips”.

---

## 2. AH-1 regression

**Status: still fixed. Do not re-open as a new High finding.**

Fix child `08-31-fix-folder-cycle-guard` is still present.

### Import refuses folder cycles (reuse, not a second copy)

`_import_metadata` writes `Folder.parent_id` only after `folders_repo.would_create_cycle(session, child_id=folder_id, new_parent_id=parent_id)` (`webdav_sync.py:1628–1641`). On True it logs, re-homes to root (`parent_id = None`), and increments `imported["conflicts"]`.

The walk lives in `repositories/folders.py:39–69` (seen-set, terminates on an already-cyclic table). `webdav_sync.py` does not copy it. The only other `_would_cycle` in the tree is catalogs-specific (`restructure_catalogs_apply.py:103`) and is unrelated to this folder fix.

Re-homing uses `_nearest_live_folder_id` (`2344–2360`) with a `seen` set; a cycle or missing node returns `None` (root). Spec contract “validate the value you are about to write, not the one you read” is honored: cycle check runs **after** nearest-live.

### `_folder_path` terminates on a cycle

`_folder_path` (`2447–2474`) uses an explicit `if cur in seen: log.warning; break` inside `while cur:` — not the forbidden `while/else`. Returns the partial path. Same containment on `_folder_path_from_export` (`1566–1573`) and `_scoped_ancestor_rows` (`1419–1431`). `_order_by_parent_chain` (`2385`) stops a snapshot-internal cycle with `on_chain`.

### Tests still exist

- `test_webdav_import_rejects_folder_cycle` (`tests/test_webdav_conflict_guard_e2e.py:819`) — mutually-parented snapshot + local A/B, asserts no DB cycle and `conflicts >= 1`.
- `test_folder_path_survives_existing_cycle` (`:907`) — poisoned A↔B, `_folder_path` under `asyncio.wait_for(..., 10)`.

### Residual walks outside this child (not an AH-1 regression)

`ingest_file._resolve_folder_path` and `agent/tools/read_entries_metadata.py` still walk folder/catalog parents **without** a `seen` set. Those modules are owned by ingest / agent-chat. Folder import no longer creates the cycle those walks would hang on. Catalog import still can — that is **WEBDAV-H3**, a new finding, not AH-1 reopened.

---

## 3. Findings by severity

### Critical

None.

### High

#### WEBDAV-H1 — `publish_selected` drops remote relations that are not among the locally selected ids

- **Where:** `src/library/services/webdav_sync.py:1289–1303` (`_merge_snapshot_rows`, `scoped=True` branch used from `publish_selected:713–718`)
- **Failure scenario:** Machine A has published entries E1, E2 and relation R(E1,E2) to the shared remote. Machine B never selected those ids; it `publish_selected([E3])`. Merge keeps remote **entries** E1/E2 (`_merge_by_key` on `entries.jsonl`) but then filters the merged **relations** with `relation_scope = selected_entry_ids` (only `{E3}`). R is omitted from the new snapshot. `latest.json` is replaced. Subsequent pulls on a fresh machine lose the E1–E2 note. Views/sessions/journals do **not** do this — remote rows are preserved and only local rows are scoped. Relations are the inconsistent collection.
- **Not 二.23:** Comment 1294–1297 and the scoped docstring (1271–1277) are leak language (“must not ride along”, “dropped from the **local** side entirely (remote rows … are still preserved)”). Audit 二.23 / `test_publish_selected_scope_e2e.py` start from an **empty** remote and assert local taxonomy/private agent state is not uploaded. That privacy goal is real: `knowledge_pack` exports every live-entry relation, so a local free-text note between two entries that merely already exist on the remote would leak if the post-merge filter used `entry_ids` (remote ∪ selected). The implementation over-applies that filter to the **merged** list, so already-published remote R(E1,E2) is deleted even though E1/E2 are kept. If 二.23 had meant “drop all unselected relations including remote,” the docstring would say remote relation rows are dropped the way it says journals are preserved, and the merge would also drop E1/E2. Keep as High.
- **Suggested fix:** For `scoped=True`, filter **local** relations to endpoints ⊆ selected ids, then `_merge_by_key` with **all** remote relations, then keep a relation iff both endpoints are in the **merged** `entry_ids` (remote ∪ selected). Add an e2e: pre-seed remote E1–E2+R, publish_selected(E3), assert R still in `relations.jsonl`.

#### WEBDAV-H2 — `publish_selected` recover path can replace a populated remote with a selected-only snapshot

- **Where:** `_read_remote_snapshot` `recover=True` at `webdav_sync.py:1243–1255`; called from `publish_selected:624–626` (also `publish_snapshot:388–390`, less destructive).
- **Failure scenario:** Remote `latest.json` exists but is not a JSON object, has an empty `latest_snapshot`, the manifest 404s via `read_json`, or any required `*.jsonl` has one invalid line (`_parse_jsonl` raises `WebDavConfigError`). Recover logs a warning and returns `_empty_snapshot()`. The comment says this publishes “a fresh **full** snapshot”. `publish_selected` then merges selected local rows with **empty** remote rows and MOVEs a new `latest.json`. The shared library’s previous entries/relations/tags disappear from latest (blobs remain orphaned). Trigger is narrower than a default happy path, but the user-visible loss is the whole remote catalog except the ids just selected. `allow_missing=True` 404 of `latest.json` is the legitimate first-publish case and is **not** this bug.
- **Suggested fix:** `publish_selected` must pass `recover=False` (or refuse with a clear error). If recover stays for `publish_snapshot`, keep it only there. Do not treat JSONL parse failure as “remote is empty”.

#### WEBDAV-H3 — catalog `parent_id` import has no cycle guard (AH-1 sibling, not a regression)

- **Where:** `_import_metadata` catalog loop `webdav_sync.py:1674–1703`. Contrast folder loop `1633–1641`. Spec: `.trellis/spec/backend/database-guidelines.md` “Every write path that sets `parent_id` must call `would_create_cycle()` first” — catalogs are named in that spec as the other adjacency-list tree.
- **Failure scenario:** Same shape as AH-1, for catalogs: local live catalogs A, B; snapshot `A.parent=B`, `B.parent=A` (two machines independently reparented, or a hostile pack). `_order_by_parent_chain` emits in chain order; each parent exists so the `session.get(Catalog, parent_id) is None` check does not re-home; both writes flush; SQLite allows the self-FK loop. WebDAV’s own `_folder_path` is folder-only so this does not re-hang publish. `agent/tools/read_entries_metadata.py:107–114` walks `Catalog.parent_id` with `while cur_id:` and **no `seen` set** — an entry in that catalog hangs the agent tool (coroutine never returns, list grows). `catalogs_repo.expand_subtree` is bounded; that does not save the agent walk.
- **Suggested fix:** Before writing `Catalog.parent_id`, call a **single** catalog cycle primitive (extract the existing `restructure_catalogs_apply._would_cycle` into `repositories/catalogs.py`, same shape as `folders.would_create_cycle`). On True, re-home to root, increment `conflicts`, log. Add the AH-1 pair of tests for catalogs. Containment on the agent walk belongs to `review-agent-chat` and is not a substitute for the write guard.

### Medium

#### WEBDAV-M1 — untrusted snapshot paths are not confined to `webdav_remote_path`

- **Where:** `_split_path` `2491–2492` keeps `.` / `..` segments; `_join_remote` `2477–2481`; `latest_snapshot` used at `955–956` and `1223–1227`; `hydrate_entry` `1064–1068` joins `marker.remote_root` + `marker.blob_path`; import stores `file_meta["blob_path"]` verbatim at `1873`.
- **Failure scenario:** A peer (or anyone who can write `latest.json` in the library folder) sets `latest_snapshot` to `../../../other-user/manifest.json` or an entry `blob_path` to `../Photos/secret.bin`. `_encode_path` percent-encodes `..` as `%2E%2E`; many WebDAV servers decode then normalize. The client’s credentials often cover the whole account while `webdav_remote_path` is supposed to be the library scope (confused deputy). Hash check on hydrate limits silent ingest of wrong bytes, but pull of a foreign manifest still runs `_import_metadata`. Hostile test (`test_hostile_manifest_ids_and_names_are_neutralized`) only rejects path-shaped **file_id** / slashes in **display_name**, not `blob_path` / `latest_snapshot`.
- **Suggested fix:** Reject any path segment in `{'.', '..'}` after split. Require `latest_snapshot` to match `snapshots/<16-hex>/manifest.json`. Require `blob_path` to match `blobs/sha256/[0-9a-f]{2}/[0-9a-f]{64}`. Ignore `marker.remote_root` from the snapshot; always use `_remote_root(settings)`.

#### WEBDAV-M2 — status file / `GET /status` stores raw exception text (URLs, possible userinfo)

- **Where:** `sync_remote_status:356` `remote_error: str(exc)`; `publish_snapshot:493` and `publish_selected:806` `"error": str(exc)`; `read_status:1190–1198` returns `last` to the client. Routes correctly map unexpected errors to `_GENERIC_WEBDAV_ERROR` (`routes_webdav_sync.py:51–53`) for the HTTP body, but the persisted `last` is what the Settings/status UI reads.
- **Failure scenario:** `webdav_url` is `https://user:pass@host/dav` (or httpx embeds the URL). A 401/timeout writes that string into `sync/webdav_status.json`. Next `GET /v1/sync/webdav/status` (and settings payload `webdav.last`) returns it. `_redact_error` (`2179–2188`) already exists and is used only for per-entry hydrate errors.
- **Suggested fix:** Persist `_redact_error(exc)` (or the generic string) in every `_write_status` error field. Keep the full exception on the server log only (`log.exception` already runs in the route layer).

#### WEBDAV-M3 — one bad untrusted field aborts the entire pull (CHECK/FK / `int()`)

- **Where:** `_import_metadata` `1760` tag `facet` (CHECK `TAG_FACETS`; read at `1744`); `1908` `ingest_status`; `1936` `lifecycle` (CHECK `ENTRY_LIFECYCLES`); `1962–1965` `EntryTag.source`; `1998` `source_kind` default **`"mine_relations"`** which is **not** in `ENTRY_RELATION_SOURCE_KINDS`; `1937` `catalog_id` assigned with no existence remap (FK); `1894` / `download_plan:875` `int(file_meta.get("size_bytes") or 0)` (ValueError). Catalog `name` at `1694` is `_sanitize_import_name` and is **not** a CHECK abort.
- **Failure scenario:** A single relation row missing `source_kind` uses the illegal default and SQLite CHECK fails at `session.commit()` (`pull_latest_metadata:999`) — the whole import rolls back, including already-flushed folders/entries in that transaction. Same for `lifecycle="evil"`, unknown `facet`, dangling `catalog_id`, or `size_bytes: "10MB"`. Healthy packs from `knowledge_pack.py` are fine; a hostile or partially-hand-edited snapshot, or a future schema drift, DoS’s pull. Folders already skip/re-home; entries skip non-UUID ids; these other columns do not.
- **Suggested fix:** Coerce with allow-lists (`_as_int`, `ENTRY_LIFECYCLES`, `TAG_FACETS`, `ENTRY_RELATION_SOURCE_KINDS`). Skip the bad row, increment `conflicts`, log, continue. Default relation `source_kind` to a legal value or skip. Resolve `catalog_id` like folders (`nearest live` / drop FK-less ids).

### Low

#### WEBDAV-L1 — oversized functions (prior A-1, still true)

- **Where:** `_import_metadata` `1577–2126` (~550 lines); `publish_selected` `583–811` (~229 lines). `WebDavClient` is 165 lines.
- **Failure scenario:** none currently; review/maintenance cost. Do not treat as a correctness bug.
- **Suggested fix:** Split import by collection (folders/catalogs/entries/agent-state) only as part of a dedicated refactor child, not bundled with H1–H3.

#### WEBDAV-L2 — `WebDavPullResponse` omits `conflicts` (and agent-state counts)

- **Where:** `src/library/schemas/webdav.py:51–66`. Runtime pull returns `conflicts` (ExtraAllow). Tests assert `pulled["conflicts"]`.
- **Failure scenario:** generated TS/OpenAPI clients drop or never type the field; UI cannot show “N local edits kept”. Not a runtime loss of the count.
- **Suggested fix:** Add `conflicts: int | None` (and sessions/conversations/journals if those stay in the payload) to the strict/extra model used by OpenAPI.

#### WEBDAV-L3 — hash-mismatch blob delete swallows all errors

- **Where:** `WebDavClient.stream_to_storage` `251–254` `except Exception: pass`.
- **Failure scenario:** storage delete fails; a wrong-hash blob remains at `storage_key` until the next successful hydrate overwrites it. Download still raises `WebDavConfigError`, so the caller is not told success.
- **Suggested fix:** Log the delete failure; keep the raise.

#### WEBDAV-L4 — missing/soft-deleted folder parent re-home does not increment `conflicts`

- **Where:** `_nearest_live_folder_id` at `1627` then write; conflict++ only on cycle (`1642`) or local-wins (`1655`). Catalog missing parent sets `None` at `1679–1680` with no count. Catalog `session.get` does **not** skip `deleted_at`, so a live catalog can sit under a soft-deleted parent (unreachable; folders avoid this).
- **Failure scenario:** operator looking at `conflicts == 0` after a pull that silently re-rooted folders. Data is still acyclic.
- **Suggested fix:** Count re-homes; for catalogs, skip deleted parents (or nearest-live) like folders.

---

## 4. Checked, no issue

Must-include conclusions first.

### Conflict counting

The counter is a **row-level skip/re-home tally**, not a list of conflict objects.

Increments (`imported["conflicts"]`):

| Site | When |
|---|---|
| `1642` | folder parent would cycle → re-home to root, **row still imported** |
| `1655` | local folder wins (`_local_row_wins`) → skip remote fields |
| `1688` | local catalog wins → skip |
| `1716` | local view wins → skip |
| `1839` | newer local **delete** → do not resurrect, skip file+entry |
| `1921` | newer local entry **metadata** → keep entry fields; file sha/marker still updated; tags still merged |

Does **not** increment: tag identity merge, relation overwrite, session/conversation/journal overwrite, missing-parent folder re-home, skipped non-UUID entry/file ids, catalog missing parent.

`_local_row_wins` (`2327–2341`): strictly newer local `updated_at` vs remote `updated_at`, or local `deleted_at` newer than remote updated/snapshot created. Equal timestamps → remote wins. Missing remote timestamp → not a metadata win (delete can still win).

Double-count is possible (cycle++ then local-wins++ on the same folder) because cycle handling does not `continue`. Harmless; the write is skipped on local-wins so no cycle is created.

Pull returns the counter; `test_pull_preserves_newer_local_edits_and_merges_tags` asserts `== 1`; cycle test asserts `>= 1`. **Conclusion: the documented minimal guard behaves as designed for folders/catalogs/views/entries. Gaps are WEBDAV-L2/L4 and the uncounted collections, not a miscount of the cases it claims to cover.**

### Publish scope

`publish_selected` → `_merge_snapshot_rows(..., scoped=True)`:

| Collection | Local side | Remote side |
|---|---|---|
| entries | selected ids only | all remote entries kept |
| blobs uploaded | local pack blobs whose sha256 is on a selected entry | `exists` skip |
| folders / catalogs | ancestor chain of selected entries only (`_scoped_ancestor_rows`, cycle-safe) | all remote kept, local ancestors overwrite same id |
| tags / tag_aliases | tags attached to selected entries (+ aliases to those tags) | all remote kept |
| views / sessions / conversations / journals | **empty local list** (private agent state not leaked) | **all remote kept** |
| relations | see **WEBDAV-H1** — filter applied to the **merged** list with scope = selected ids only | dropped if endpoints ∉ selected |

Full `publish_snapshot` uses `scoped=False`: complete local taxonomy merged; relations kept among merged entry ids; remote-only rows from other machines are not dropped (the “never pulled” merge at `400–416`).

`test_publish_selected_scopes_metadata_to_selected_entry` covers the **empty-remote** case (ancestor folders, attached tag, no private views/journals, unrelated folder not leaked). It does **not** cover merge-with-existing-remote relations (H1) or recover (H2).

**Conclusion: selective publish’s taxonomy/privacy scope is correct except relations (H1) and the recover empty-snapshot path (H2).** 二.23 is the local-leak rule (empty-remote test, remote rows preserved for views/sessions/journals); it does not document deleting already-published remote relations among kept remote entries. Full publish including sessions/journals is intentional backup behavior; auto-sync (`periodic_tick` → `KIND_WEBDAV_PUBLISH` → `publish_snapshot`) therefore uploads agent state. That is a product choice, not a selective-publish regression.

### Other checked items

- **Library ownership:** `_require_same_library` on publish; `_guard_pull_library` before DB writes; `_adopt_library_id` only after successful pull. Tested by `test_publish_refuses_foreign_library_then_merges_after_pull`.
- **latest.json last:** both publish paths upload blobs + snapshot metadata, then MOVE `latest.json`. Interrupted publish without a successful latest MOVE leaves the previous latest intact.
- **Blob sha256:** `stream_to_storage` hashes and deletes on mismatch; `test_webdav_stream_to_storage_checks_sha256`.
- **Hydration marker:** changed remote sha forces `hydrated=False`; `hydrated=False` is not flipped back by `storage.exists`; newer local delete is not resurrected. Tests `#3/#10/#13/#18`.
- **Folder name reconciliation:** `(parent_id, name)` including soft-deleted rows; parents-before-children via `_order_by_parent_chain`. Tests `#4/#22`.
- **Display name / file_id hostile:** non-canonical UUID file/entry ids skipped; `/` `\` and dot-only names sanitized. Folder/catalog/tag ids are **not** UUID-gated (L-level gap, not retested as High).
- **Placeholder storage key:** MirrorStorage uses `_webdav/{canonical-uuid}`; local uses `storage_prefix`. `display_name` is not interpolated into the key.
- **SSRF to arbitrary hosts:** client `base_url` is the user-configured `webdav_url` (http/https only). Not snapshot-controlled. Host allowlist is `review-cross-cutting`.
- **Route auth:** `/v1/sync/webdav/*` uses `OPTIONAL_AUTH_RESPONSES` / `WEBDAV_ERROR_RESPONSES`; process-wide token middleware is cross-cutting. Config whitelist `_CONFIG_FIELDS` drops unknown overlay keys with 422.
- **Handler:** `webdav_publish.py` ignores payload and always full-publishes; matches enqueue from `/publish` and auto-sync.
- **`follow_redirects=True`, `trust_env=False`:** no proxy-env surprise; redirects stay httpx-default (http/https).
- **JSONL unicode:** `_parse_jsonl` uses `json.loads` per line; U+2028 inside strings preserved (`test_parse_jsonl_preserves_unicode_line_separator_inside_strings`). Non-dict lines silently skipped (acceptable).
- **Concurrent publishers:** last MOVE of `latest.json` wins; no If-Match. Inherent last-write-wins; not filed (would be a design child, not a silent logic bug).

---

## 5. Test gaps

| Gap | Why it matters |
|---|---|
| No test that `publish_selected` **preserves remote relations** among unselected remote entries | WEBDAV-H1 would be green today |
| No test that `publish_selected` **refuses** (or full-publishes) when remote JSONL/manifest is corrupt | WEBDAV-H2 |
| No catalog-cycle import test (folder pair exists) | WEBDAV-H3 |
| Hostile fixture does not set `blob_path` / `latest_snapshot` with `..` | WEBDAV-M1 |
| No test that status `error` / `remote_error` is redacted | WEBDAV-M2 |
| No test that illegal `lifecycle` / `source_kind` / `facet` skips a row instead of failing the pull | WEBDAV-M3 |
| `publish_selected` scope test starts from **empty** remote only | does not exercise remote∪local merge |
| No test for catalog live-child under soft-deleted parent | WEBDAV-L4 |
| `test_mirror_e2e.py` is not WebDAV protocol | correctly out of scope |

Collect-only: 22 selected / 1 skipped at collection (`-k "webdav or publish_selected"`). The skip is not a WebDAV test being xfail’d; do not treat the suite as “all 22 ran”.

---

## 6. Suggested fix children

Do **not** create these in this round.

1. **Fix selective-publish merge (H1 + H2)**  
   Files: `src/library/services/webdav_sync.py` (`_merge_snapshot_rows`, `publish_selected`, `_read_remote_snapshot` call sites), `tests/test_publish_selected_scope_e2e.py`.  
   Why: one verifiable cluster — selected publish must not delete remote relations and must not recover into a selected-only latest.

2. **Catalog parent_id cycle guard on WebDAV import (H3)**  
   Files: `webdav_sync.py` catalog loop; extract `would_create_cycle` to `repositories/catalogs.py`; `tests/test_webdav_conflict_guard_e2e.py`.  
   Why: same acceptance shape as `08-31-fix-folder-cycle-guard`, for catalogs. Do not copy-paste the folder helper.

3. **Constrain untrusted snapshot paths (M1)**  
   Files: `_split_path` / hydrate / `_read_remote_snapshot` / import marker; extend hostile e2e.  
   Why: independent of merge/cycle; testable with `..` fixtures.

4. **Redact WebDAV status errors (M2)**  
   Files: `sync_remote_status`, `publish_snapshot`, `publish_selected` status writes. Small, separate from (1).

Optional later (do not bundle with 1–3): M3 allow-list/skip-row import hardening; L1 function split; L2 OpenAPI `conflicts` field (coordinate with `review-frontend-pages`).

---

## 7. Five-angle conclusions

| Angle | Conclusion |
|---|---|
| **Correctness** | Folder cycle + `_folder_path` (AH-1) still fixed. New High bugs: selective publish drops remote relations (H1); selective recover can gut `latest.json` (H2); catalog import can still close a parent loop (H3). Conflict counting matches the documented minimal guard. Full publish still merges remote-only rows. |
| **Security** | Snapshot is untrusted and only partly sanitized (UUID file/entry ids, display_name slashes). Path `..` on `blob_path`/`latest_snapshot` is not rejected (M1). Status JSON can echo raw httpx URLs (M2). No snapshot-controlled SSRF to a new host. Route layer does not leak exception text to HTTP 502 bodies. Authz is process-wide (cross-cutting). |
| **Architecture** | Publisher-not-filesystem-syncer still holds (content-addressed blobs, latest.json last). `publish_selected` is in-request; full publish is a worker task (`KIND_WEBDAV_PUBLISH`, timeout 180s) — inconsistency, not a defect by itself. `_import_metadata` / `publish_selected` remain oversized (A-1). Catalog cycle logic is duplicated in `restructure_catalogs_apply` and unused by import. |
| **Spec / contract** | Folder `parent_id` writes now match `database-guidelines.md`; catalog writes do not (H3). `WebDavPullResponse` omits `conflicts` (L2) even though the service returns it (`ExtraAllowModel`). Overlay config whitelist and generic 502 match the route comments. |
| **Tests** | AH-1, conflict guard, hostile file_id/name, library_id, empty-remote selected scope, sha256 mismatch are covered. Missing: remote-relation preservation, recover-on-corrupt, catalog cycle, `..` paths, status redaction, CHECK-constraint rows. 22 tests collected by the assigned `-k` filter. |

---

## Verification

```text
git status --short
# product paths clean; untracked .trellis/tasks/* and package-lock.json only
# (report.md appears under .trellis/tasks/08-31-review-webdav/ after this write)

uv run pytest tests/ -k "webdav or publish_selected" --collect-only
# 22 selected / 1 skipped at collection / 635 deselected
```

No `--fix`. No product files edited.
