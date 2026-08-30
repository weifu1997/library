# Design

## License

Source of truth: `LICENSE` (MIT) and `pyproject.toml` (`license = "MIT"`).

Update:

- `README.md` / `README.zh-CN.md` License sections → MIT; drop AGPL network-service paragraph.
- `docs/LAUNCH.md` CLI/product sentences that say AGPL → MIT.
- `scripts/UPSTREAM.md` → Library is MIT; AstrBot-desktop copy was AGPL; those packaging scripts are no longer in tree.

Do not relicense Headroom vendor code; do not claim it is MIT.

## Contract allowlist (JSON only)

Sessions (`routes_agent.py`):

- POST `/v1/sessions` 201 `{session_id, started_at}`
- POST `/v1/sessions/{session_id}/close` `{session_id, ended_at, end_reason, totals}`
- GET `/v1/sessions` `{sessions, limit, offset, next_cursor}`
- GET `/v1/sessions/{session_id}/messages` transcript
- DELETE `/v1/sessions/{session_id}` 204 — `response_model=None`
- GET attachments — raw `Response`, no JSON `response_model`

Folders (`routes_folders.py`):

- GET/POST `/v1/folders`, GET/PATCH/DELETE `/v1/folders/{folder_id}`
- Not GET `.../download` (zip stream)

WebDAV (`routes_webdav_sync.py`, prefix `/v1/sync/webdav`):

- All 12 JSON methods. GET/PUT status reuse `WebDavStatus`.
- Variable payloads (`test`, `remote-status`, plans, pull, download, hydrate, publish-selected): `extra="allow"` so undeclared keys are not dropped.

## Serialization

- Folders/sessions stable snapshots: `extra="forbid"` except PATCH folder (may return `{folder_id}` only) → `extra="allow"`.
- `response_model_exclude_none` stays false.
- Errors: document existing 400/404/409/422/502 only.

## TS

Alias Folder/Session/WebDAV JSON types from `components.schemas` where they fit. Keep handwritten `WebDavStatus.last` shape for GUI (same as settings).
