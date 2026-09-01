# WebDAV Sync Contracts

> Untrusted-input hardening for `src/library/services/webdav_sync.py`.
> A WebDAV peer (or anyone able to write `latest.json` / snapshot files on the
> remote) is hostile. Every path and every enum field in a snapshot is untrusted
> and must be validated before it reaches a filesystem path, a URL join, or a
> SQLAlchemy insert.

## 1. Scope / Trigger

Trigger: hardening work on the WebDAV sync surface. Read this file before
touching any snapshot parse, remote path join, status persistence, or import
row write.

## 2. Signatures

```python
# knowledge_pack.py — the only legal snapshot id producer
def new_snapshot_id(_now: datetime | None = None) -> str: ...  # secrets.token_hex(8)

# webdav_sync.py
def _validated_latest_snapshot(value: Any, *, required: bool = True) -> str: ...
def _validated_blob_path(value: Any) -> str: ...
def _split_path(path: str) -> list[str]: ...   # raises WebDavConfigError on "." / ".."
def _as_int(value: Any, default: int = 0) -> int: ...
def _redact_text(text: str) -> str: ...
def _redact_error(exc: Exception) -> str: ...
def _write_status(settings: Settings, value: dict[str, Any]) -> None: ...
```

## 3. Contracts

### Snapshot layout (WEBDAV-M1)

- `latest.json.latest_snapshot` must match `snapshots/<16-hex>/manifest.json`
  (`_LATEST_SNAPSHOT_RE`). The 16 hex chars are the `new_snapshot_id()` output.
  Test fixtures MUST use `new_snapshot_id()` (or a literal `[0-9a-f]{16}`) —
  a timestamp like `2026-07-01T00-00-00Z` is rejected.
- Entry `blob_path` must match `blobs/sha256/<2-hex>/<64-hex>`
  (`_BLOB_PATH_RE`). Uppercase hex is rejected.
- `_split_path` rejects any `.` / `..` segment. A remote path is never joined
  onto the root before passing this check.
- Hydration ignores `marker.remote_root` — the configured `_remote_root(settings)`
  is always used, so a hostile snapshot cannot redirect hydrate off the library
  scope (confused-deputy guard).

### Status persistence (WEBDAV-M2)

- Every persisted error field (`error`, `remote_error`, and anything else
  written by `_write_status`) is passed through `_redact_text` before the JSON
  file is written. URLs become `<url>`, `user:pass@host` becomes `<redacted>`.
- The full exception stays on the server log only.

### Import row coercion (WEBDAV-M3)

- `size_bytes` / `doc_count` / counts: `_as_int(value, default)` — never a bare
  `int(...)` that raises on `"10MB"`.
- Enum columns are allow-listed against `library.db.models.enums` and the row is
  **skipped** (not aborted) on an illegal value, `imported["conflicts"] += 1`:
  - tag `facet` → `TAG_FACETS`
  - entry `ingest_status` → `INGEST_STATUSES`
  - entry `kind` → `FILE_KINDS`
  - entry `lifecycle` → `ENTRY_LIFECYCLES`
  - entry_tag `source` → `ENTRY_TAG_SOURCES` (default `"ingest"`)
  - relation `source_kind` → `ENTRY_RELATION_SOURCE_KINDS` (missing → skip;
    `"mine_relations"` is NOT legal)
- `catalog_id` is resolved like folders: dangling / soft-deleted ids become
  `None` instead of an FK failure.

## 4. Validation & Error Matrix

| Condition | Behavior |
|---|---|
| `latest_snapshot` = `snapshots/<16-hex>/manifest.json` | accepted |
| `latest_snapshot` contains `..` or non-hex id | `WebDavConfigError` (pull aborts) |
| `latest_snapshot` empty + `required=True` | `WebDavConfigError` |
| `latest_snapshot` empty + `required=False` (status probe) | treated as "no snapshot" |
| `blob_path` not `blobs/sha256/<2-hex>/<64-hex>` | `WebDavConfigError` |
| illegal enum value on an import row | row skipped, `conflicts += 1` |
| `size_bytes="10MB"` | coerced to `default` (0) |
| raw exception contains URL / userinfo | redacted in persisted status, full text only in logs |

## 5. Good / Base / Bad Cases

- **Good**: healthy pack from `knowledge_pack.py` pulls; `hydrate_entry` streams
  from `_remote_root(settings)` + validated `blob_path`.
- **Base**: `sync_remote_status` with an empty `latest_snapshot` returns
  "no snapshot yet" rather than failing the whole probe.
- **Bad**: hostile `latest_snapshot = "../../../other-user/manifest.json"`
  aborts pull before any join; hostile `blob_path` aborts hydrate; a single
  relation row with `source_kind="mine_relations"` skips that row instead of
  rolling back the whole import.

## 6. Tests Required

- `tests/test_webdav_mediums_unit.py` — validator accept/reject matrices, pull /
  hydrate hostile paths, status redaction, illegal-CHECK-field skip, and a
  `test_new_snapshot_id_is_git_like_hex` (in `test_webdav_sync_e2e.py`).
- Any new snapshot fixture must produce a 16-hex `snapshot_id` (use
  `new_snapshot_id()`), or the pull tests fail on validation.

## 7. Wrong vs Correct

```python
# WRONG — int() raises, `..` joins, source_kind default aborts commit
size = int(file_meta.get("size_bytes") or 0)
remote = _join_remote(root, latest["latest_snapshot"])   # .. not checked
row.source_kind = str(item.get("source_kind") or "mine_relations")  # illegal

# CORRECT — coerce, confine, allow-list, skip
size = _as_int(file_meta.get("size_bytes"), 0)
latest_snapshot = _validated_latest_snapshot(latest.get("latest_snapshot"))
source_kind = str(item.get("source_kind") or "")
if source_kind not in ENTRY_RELATION_SOURCE_KINDS:
    imported["conflicts"] += 1
    continue
```

## Cross-layer notes

- `GET /v1/sync/webdav/status` and settings `webdav.last` read the persisted
  status file — that is why redaction must happen at write time.
- The strict snapshot regex is a hard contract: any future producer of snapshot
  dirs (e.g. exports) must emit `new_snapshot_id()`-shaped ids.
