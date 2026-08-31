# Database Guidelines

> Database patterns and conventions for this project.

---

## Overview

<!--
Document your project's database conventions here.

Questions to answer:
- What ORM/query library do you use?
- How are migrations managed?
- What are the naming conventions for tables/columns?
- How do you handle transactions?
-->

(To be filled by the team)

---

## Folder live unique names

`folders` uniqueness is **live-only**: partial unique index
`uq_folders_live_parent_name` on `(parent_id, name) WHERE deleted_at IS NULL`.
Soft-deleted rows must not occupy the name. Recreating a nested folder after
DELETE is 201, not IntegrityError 500. Two live siblings still 409.

SQLite treats two `parent_id IS NULL` as distinct in UNIQUE; root clashes are
still enforced in `create_folder` via `find_child_by_name`. Map remaining
`IntegrityError` on create to 409.

Regression: `tests/test_folder_live_unique_e2e.py`. Alembic
`0017_folders_live_parent_name_unique`.

## Semantic file index publish

The file-index backend is three files: `entries.jsonl`, `vectors.f32`,
`manifest.json`. Readers do not take the write lock.

- Stamp `entries_sha256` / `vectors_sha256` / `vector_bytes` on the manifest
  and replace **manifest last**.
- On load, if counts or checksums disagree, refuse the index (`None`). Never
  `min()`-truncate mismatched rows into search hits.
- Legacy manifests without checksums may load when counts agree.

Regression: `tests/test_semantic_index_unit.py`
(`test_crash_between_index_replaces_does_not_return_wrong_hits`).

## Self-Referencing Tables (`parent_id`)

`folders` and `catalogs` are trees stored as adjacency lists. SQLite enforces
no cycle constraint on a self-FK, so **the application is the only thing
standing between a snapshot and an unwalkable tree**.

### Contract

1. **Every write path that sets `parent_id` must call that table's
   `would_create_cycle()` first** (`repositories.folders` or
   `repositories.catalogs`). Not just the obvious ones. `move_folder` and
   `restructure_catalogs` move always did; the WebDAV metadata import did not,
   and a re-import of a snapshot with mutually-parented folders or catalogs
   closed a real loop in the live database. Catalog `soft_delete` `merge_into`
   also skipped it.

2. **Every read path that walks up a parent chain must carry a `seen` set.**
   Guarding the writes is not enough: a database poisoned before the guard
   existed still has the cycle, and the walk must terminate on that data.

3. Validate the value you are about to **write**, not the one you read. Re-homing
   logic (e.g. `_nearest_live_folder_id`, which climbs to the nearest live
   ancestor) can hand you a parent that is itself below the row being written.

### Why this keeps happening

The failure is asymptomatic until it isn't. A cycle costs nothing to create and
nothing to store; the damage surfaces later, in an unrelated code path, as a
coroutine that never returns and a list that grows until the process dies — no
exception, no log line, the task simply stays `running` forever.

Grep before adding a parent walk: `list_live_descendant_ids`,
`would_create_cycle`, `_nearest_live_folder_id`, `_order_by_parent_chain` and
`_folder_path_from_export` are all already guarded and show the shape.

### Forbidden

```python
# NO — unbounded parent walk
while cur:
    row = await db.get(Folder, cur)
    cur = row.parent_id
```

```python
# NO — `while/else` does not distinguish "reached the root" from "hit a cycle";
# both make the loop condition false.
while cur and cur not in seen:
    ...
else:
    log.warning("cycle")
```

---

## Query Patterns

<!-- How should queries be written? Batch operations? -->

(To be filled by the team)

---

## Migrations

<!-- How to create and run migrations -->

(To be filled by the team)

---

## Naming Conventions

<!-- Table names, column names, index names -->

(To be filled by the team)

---

## Common Mistakes

<!-- Database-related mistakes your team has made -->

(To be filled by the team)
