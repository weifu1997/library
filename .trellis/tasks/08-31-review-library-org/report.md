# Review report — 知识库组织

Parent: `08-31-feature-code-review`. Report-only. No product code was modified.

This report was written by the main session after a sub-agent claimed “no findings” without persisting a file. Claims below are traced to current source.

---

## 1. Coverage and method

| Surface | Depth |
|---|---|
| `services/folders.py` | line-read create/rename/move/soft_delete, `_validate_folder_name`, `_find_or_create_child` |
| `services/entries.py` | line-read `_build_folder_display_path`, rename/move/soft_delete |
| `services/recommend.py` | line-read `find_related` / `_load_edges` |
| `services/relation_vetting.py` | line-read |
| `api/routes_folders.py` | line-read |
| `api/routes_file_entries.py` | line-read |
| `api/routes_files.py` | line-read reprocess/bulk scope |
| `repositories/folders.py` | line-read `would_create_cycle`, `list_live_descendant_ids`, `find_child_by_name` |
| `repositories/catalogs.py` | line-read `expand_subtree` |
| `repositories/entry_relations.py` `journal.py` `tags.py` | line-read contracts used by this surface |
| `restructure_catalogs.py` (docstring/invariants) | line-read |
| `restructure_catalogs_apply.py` | line-read `_would_cycle`, `_op_move`, `_op_create`, `_op_soft_delete` |
| mining: `mine_relations.py` `mine_tag_overlap.py` `_mining_helpers.py` | line-read dispatcher + pair upsert |
| `enrich_tags.py` `normalize_tags.py` `vet_relations.py` `propose_views.py` `refresh_entry_extra.py` `suggest_lifecycle.py` | structural scan of writes + eligibility |

Pattern scan: `parent_id =`, `would_create_cycle`, `_would_cycle`, `while cur`, `mark_invalidated`, `except Exception`.

Collect-only: `uv run pytest tests/ -k "folder or entry or tag or relation or journal or catalog or view" --collect-only` → **84 selected** (filter is noisy: includes tagged_response / tool_result_preview / webdav). Real owners: `test_folders_ingest_status_e2e`, `test_file_entry_path_e2e`, `test_enrich_tags_e2e`, `test_normalize_tags_e2e`, `test_mine_*`, `test_vet_relations*`, `test_propose_views_e2e`, `test_restructure_catalogs_e2e`, `test_journal_validity_e2e`, `test_lazy_relation_vetting_e2e`, `test_related_prefill_e2e`, `test_refresh_entry_extra_e2e`, `test_lifecycle_e2e`.

---

## 2. Regression / overlap

No Fixed-table item is owned by this child.

| ID | How this child treats it |
|---|---|
| **AH-1** folder WebDAV import cycle | Still fixed in webdav child. GUI `move_folder` still calls `would_create_cycle` (`folders.py:332-335`). Not re-opened. |
| **WEBDAV-H3** catalog `parent_id` on **import** | Owned by webdav. This child checks GUI/API/restructure writes. Catalog **move** in apply is guarded; catalog **import** is not this report. |
| **INGEST-L2** ingest_file folder walk without `seen` | Owned by ingest. `entries._build_folder_display_path` **does** have `seen` (`entries.py:100-110`). |

---

## 3. Findings by severity

### Critical

None.

### High

#### ORG-H1 — Soft-deleted nested folder still occupies `uq_folders_parent_name`; recreate 500s

- **Where:** `src/library/db/models/user_visible.py:37` `UniqueConstraint("parent_id", "name")`; live-only lookup `repositories/folders.py:122-126`; create `services/folders.py:169-185`; route `routes_folders.py:161-177` only catches `FolderNameConflictError` / `ValueError`.
- **Failure scenario:** User deletes folder `/work/Projects` (soft-delete, 7-day purge). GUI immediately creates `/work/Projects` again. `find_child_by_name` sees no **live** sibling, so no 409. `flush()` hits `uq_folders_parent_name` because the tombstone row still has `parent_id=<work>, name=Projects`. The route does not catch `IntegrityError` → **HTTP 500**. Until purge, that name is unusable under that parent.
- **Root vs nested:** SQLite treats UNIQUE `NULL`s as distinct, so the same sequence **at vault root** (`parent_id IS NULL`) can succeed. Nested folders cannot. The live-name index `ix_folders_parent_live_name` is not unique.
- **Suggested fix:** Unique on live rows only (partial unique index `WHERE deleted_at IS NULL`, SQLite 3.8+ / Postgres), **or** include a tombstone discriminator, **or** have create/rename treat a soft-deleted sibling as a conflict with a 409 “name reserved until purge”. Catch IntegrityError in the route either way. Test: soft-delete nested folder, create same name under same parent → 409 or success, never 500.

### Medium

#### ORG-M1 — Catalog `soft_delete` + `merge_into` re-parents children without a cycle check

- **Where:** `restructure_catalogs_apply.py:217-228`. Contrast `_op_move` which calls `_would_cycle` (`144-152`). Module docstring in `restructure_catalogs.py:26-30` says “NEVER produce a parent cycle.”
- **Failure scenario:** Tree `Old → LLM → Nested`. LLM (or a crafted apply payload) emits `soft_delete(Old, merge_into=Nested)`. Apply loads Nested (live), skips self-check, then sets every **child of Old** (`LLM`) `parent_id = Nested`. `Nested.parent_id` is still `LLM` → cycle `LLM ↔ Nested`. `expand_subtree` is BFS-with-seen so it will not hang, but the tree is corrupt; later `_op_move` / agent catalog walks that lack `seen` (already noted on `read_entries_metadata` in the agent-chat child) can hang. The e2e (`test_restructure_catalogs_e2e.py:184`) only merges into a **sibling**, not a descendant.
- **Suggested fix:** Before assigning `child.parent_id = merge_into`, call `_would_cycle(child_id=child.id, new_parent_id=merge_into)` (and reject merge_into if it is in the deleted node’s descendant set). Extract `_would_cycle` to `repositories/catalogs.py` next to `folders.would_create_cycle` (spec contract). Add a test with merge_into = grandchild.

#### ORG-M2 — Entry/folder soft-delete does not invalidate journal rows that cite those entries

- **Where:** `services/entries.py:243-260` and `services/folders.py:352-392` write `deleted_at` + audit only. `journal.mark_invalidated` is only used by reflect/summarize (agent-chat). `Journal.entry_ids` is a JSON list (`ai_recall.py:142`) with no FK.
- **Failure scenario:** User deletes the only PDF a prior insight cited. `search_journal` still returns the active note with that `entry_id`. Agent `read_files` / citations then 404 or skip; the notebook still claims the file is part of the library. `refresh_entry_extra` filters `list_active_with_file_by_ids` so it will not write extra onto a deleted row — that path is fine. Recall of **journal text** is the hole.
- **Suggested fix:** On entry (and folder-cascade) soft-delete, `mark_invalidated` for active journal rows whose `entry_ids` intersect the deleted set, reason `entry_deleted`. Or filter `search_journal` to drop ids that are not live (weaker: notes remain but ids are stripped). Test: delete entry, default journal search no longer returns that id as live evidence.

### Low

#### ORG-L1 — Catalog cycle primitive is a second copy of the folder walk

- **Where:** `restructure_catalogs_apply.py:103-119` vs `repositories/folders.py:39-69`. Spec (`database-guidelines.md:31-32`) says every `parent_id` write goes through `would_create_cycle`; catalogs are named in the same spec as the other adjacency-list tree.
- **Failure scenario:** none today if both copies stay in sync. WEBDAV-H3 exists because import did not call **any** catalog primitive — there is no `catalogs.would_create_cycle` to reuse.
- **Suggested fix:** One function in `repositories/catalogs.py`. Do not bundle with WEBDAV-H3 unless that fix child needs it.

#### ORG-L2 — `mine_relations` swallows a miner failure and still succeeds the daily slot

- **Where:** `tasks/handlers/mine_relations.py:57-60`.
- **Failure scenario:** `citation_graph` raises (LLM/DB). Dispatcher logs and runs the next miner. The task is `done`. Next `/tend` waits a full interval before citation mining runs again. Not user-visible corruption; delayed graph.
- **Suggested fix:** Re-raise after attempting all miners if any failed, or record `task_outcomes` `outcome=error` per miner so tend can retry the failed phase.

---

## 4. Checked, no issue — every `parent_id` write path

| Write path | Cycle guard |
|---|---|
| `create_folder` / `_find_or_create_child` | N/A (new id cannot be in parent’s ancestor chain) |
| `move_folder` `folders.py:332-344` | `folders_repo.would_create_cycle` then write |
| `routes_folders.patch` `update_parent` | calls `move_folder` |
| WebDAV folder import | `would_create_cycle` (AH-1; webdav child) |
| `_op_move` catalogs | `_would_cycle` then write |
| `_op_create` catalogs | N/A (new id) |
| `_op_soft_delete` children re-parent | **ORG-M1** — not guarded |
| WebDAV catalog import | **WEBDAV-H3** — not this child |

### Parent-chain **reads** (this child)

| Read path | `seen` |
|---|---|
| `folders.would_create_cycle` | yes |
| `folders.list_live_descendant_ids` / `expand_subtree` | yes |
| `catalogs.expand_subtree` | yes |
| `entries._build_folder_display_path` | yes (`entries.py:100-110`) |
| Agent `read_entries_metadata` catalog walk | no — agent-chat child |

### Other checked items

- **Folder GUI move** refuses cycles with `ValueError` → HTTP 400 (`routes_folders.py:237-238`).
- **Entry move** only changes `folder_id` (not a self-FK tree). Target must be live (`entries.py:176-179`).
- **Soft-delete folder** BFS descendants with `seen`, marks folders + entries, sets `purge_after` on entries. Physical delete is worker/cross-cutting.
- **Recommend** default walk is `vetted_only`; unvetted is opt-in. Live-A join plus B filter. Empty seed → `[]`.
- **Relation upsert** miners emit sorted `(a, b)` pairs (`mine_tag_overlap.py:155-164`); helper documents caller must sort. Unique `(entry_a_id, entry_b_id)`.
- **Vetting** skips deleted/no-summary; rejected edges stay quiet until growth/TTL.
- **enrich_tags** drops ids not in the supplied vocab; does not create tags.
- **normalize_tags** no chained `alias_of` (picks canonical with `alias_of IS NULL`).
- **refresh_entry_extra** only writes live active entries (`list_active_with_file_by_ids`).
- **Journal invalidation** as a *contradiction* mechanism (reflect) is intact; file-delete coupling is ORG-M2, not a reflect bug.
- **Bulk reprocess** catalog scope uses `expand_subtree` (cycle-safe BFS).

---

## 5. Test gaps

| Gap | Why |
|---|---|
| Soft-delete nested folder then create same name | Would have caught ORG-H1 (500 vs 409). |
| `soft_delete` merge_into = descendant | Would have caught ORG-M1. Current e2e merges into a sibling. |
| Journal search after entry soft-delete | ORG-M2. |
| `IntegrityError` on folder create is untested | Route error mapping. |
| Duplicate live root folder names | SQLite NULL UNIQUE; application `find_child_by_name` currently prevents live dupes — worth a unit test so a future query change does not rely on the DB. |

No assertion-free tests spotted in the opened e2e modules (they are `test_script_main` bundles with real asserts).

---

## 6. Suggested follow-up fix children

Do **not** create these in this round.

| Title | Files | Why |
|---|---|---|
| Live-only unique folder names (ORG-H1) | `db/models/user_visible.py`, Alembic, `services/folders.py`, folder e2e | Recreate-after-delete must not 500. |
| Cycle-check catalog merge_into (ORG-M1) | `restructure_catalogs_apply.py`; extract `catalogs.would_create_cycle` | Same class as AH-1, different tree. Can share the primitive with WEBDAV-H3. |
| Invalidate journal on entry/folder delete (ORG-M2) | `services/entries.py`, `services/folders.py`, journal repo | Stale notebook citations. |

Do not mix ORG-H1 (schema unique) with ORG-M1 (catalog apply).

---

## 7. Five-angle conclusions

| Angle | Conclusion |
|---|---|
| **Correctness** | Folder **move** is cycle-safe. Catalog **move** is cycle-safe. Catalog **merge_into** is not (ORG-M1). Nested folder **name reuse after soft-delete** 500s (ORG-H1). Entry move/rename conflict policies are consistent with upload. |
| **Security** | No path/SQL injection on this surface. Folder names reject `/` `\`. Auth is process-wide (cross-cutting). Hostile catalog apply payloads can cycle the catalog tree (ORG-M1) if they can enqueue restructure — default worker runs that kind. |
| **Architecture** | Folder cycle helper lives in the repository as required. Catalog helper is a private copy in the apply handler (ORG-L1), which is why import skipped it. `routes_files.py` still owns bulk-reprocess SQL scope (known layering debt from the architecture audit; not a new functional bug). |
| **Spec / contract** | `database-guidelines.md` parent_id contract is met for **folder GUI/API** and **catalog move**. It is not met for catalog merge_into or WebDAV catalog import. Journal invalidation contract is contradiction-based, not lifecycle-based (ORG-M2). |
| **Tests** | Restructure, vet, mine, enrich, normalize, lifecycle, journal validity have e2e scripts. Missing: recreate-after-delete, merge_into descendant, journal after delete. |

---

## Verification

```
git status --short -- src tests frontend openapi
# clean

uv run pytest tests/ -k "folder or entry or tag or relation or journal or catalog or view" --collect-only
# 84 selected / 573 deselected
```
