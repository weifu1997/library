# Review report — 接入面（MCP / CLI / eval / 导出）

Parent: `08-31-feature-code-review`. Report-only. No product code was modified.

---

## 1. Coverage and method

| File | Depth |
|---|---|
| `mcp_server.py` | line-read tool lists, HTTP vs local call, `_destination_path`, stdio main |
| `api/routes_mcp.py` | line-read |
| `cli/client.py` `oneshot.py` `repl.py` `init_cmd.py` | line-read auth/discovery/embedded |
| `cli/eval_cmd.py` | line-read import args |
| `cli/storage_cmd.py` | structural (local↔mirror migrate) |
| `eval/datasets.py` `retrieval.py` `probes.py` | line-read import + `run_turn` persist |
| `services/exports.py` `api/routes_exports.py` | line-read plan, zip, metadata allowlist |
| `services/knowledge_pack.py` | line-read what goes into a pack |
| `server_discovery.py` `server_main.py` | line-read |

Collect-only: `uv run pytest tests/ -k "mcp or cli or eval or export or discover or server_main or server_discovery" --collect-only` → **65 selected**.

---

## 2. Regression

No Fixed-table item is owned by this child. `exports.py` lazy-imports `user_files` (cycle fix) — upload child.

---

## 3. Findings by severity

### Critical

None.

### High

None that an unauthenticated network client can hit **through these adapters alone**. HTTP `/mcp/tools/{name}/call` is read-only agent tools. Write/path issues below are local CLI/stdio (same OS user). Auth of the HTTP app is cross-cutting.

### Medium

#### ACCESS-M1 — Eval import and ReAct report probes write into the live library

- **Where:** `eval/datasets.py:31-76` `import_beir_dataset` creates `/eval/<name>/` via `resolve_or_create_folder`, writes files, runs `handle_ingest_file`. `eval/probes.py:747-785` `_run_react_report_probe` `sessions_repo.create_session` then `run_turn` (persists conversations, journal, tool side effects) and only `close_session` in `finally`.
- **Failure scenario:** Operator runs `library eval import-beir nq ./nq` against their real `LIBRARY_HOME`. Thousands of eval docs land in the production folder tree and ingest queue. `library eval report-compare` / react probe creates real chat sessions and may enqueue reflect/mining. Retrieval-only `eval run` is read-heavy but still uses the live FTS/semantic index. There is no `--dry-run` / separate eval database.
- **Suggested fix:** Default eval data to `LIBRARY_HOME/eval/` **and** a dedicated sqlite file or `LIBRARY_EVAL_HOME`. Refuse import if `library_home` looks like a non-eval production tree unless `--write-library` is set. After ReAct probes, delete or flag the session as `eval`. Document in the CLI help that import is destructive.

#### ACCESS-M2 — MCP `destination_path` and eval dataset `name` are unsandboxed paths

- **Where:** `mcp_server.py:368-373` `_destination_path` = `Path(value).expanduser()`, `mkdir(parents=True)`, no `relative_to` jail. Used by download_file / download_folder / export_conversation. `eval/datasets.py:53` `eval_root() / name` with `name` from CLI (`eval_cmd.py:43`) — `../` escapes `LIBRARY_HOME/eval`.
- **Failure scenario:** Stdio MCP (Claude Desktop etc.) is told `destination_path=~/.ssh/authorized_keys` or `/tmp/x`; the Library process writes there as the OS user. `library eval import-beir '../../tmp/pwn' ./corpus` writes the dataset dir outside `eval/`. HTTP MCP does **not** expose these workflow tools (`call_mcp_tool_local` rejects non-read-only names, `:643-644`).
- **Suggested fix:** MCP: resolve and require destination under `$HOME` or an explicit `--allow-write-root`. Eval: reject `name` containing `/`, `\`, `..`. Test both.

#### ACCESS-M3 — Conversation zip export materializes every cited blob in memory

- **Where:** `routes_exports.py:103-116` — `bytearray` per file, then full `ZipFile` in a `BytesIO` before the first chunk is yielded.
- **Failure scenario:** Export a turn that cited several large PDFs. API process peaks at sum(file sizes) + zip size. Same class as UPLOAD-3 (folder download). Citation set is smaller than a whole folder, but unbounded.
- **Suggested fix:** Stream zip members (spool to temp file) or cap total uncompressed bytes. Reuse the folder-download fix if that child lands first.

### Low

#### ACCESS-L1 — HTTP `/mcp/tools` is a second, narrower surface than stdio MCP

- **Where:** `routes_mcp.py` → `call_mcp_tool_local` (read-only). Stdio `list_mcp_tools` adds workflow tools. Easy to assume the HTTP list is complete.
- **Suggested fix:** Document on GET `/mcp/tools` that workflow tools are stdio-only, or expose them over HTTP behind the same auth.

#### ACCESS-L2 — Knowledge pack includes sessions / conversations / journals

- **Where:** `knowledge_pack.py:251-261`. Used by WebDAV full publish (webdav child). Not an HTTP export route. No API keys in the pack (settings overlay is not packed).
- **Suggested fix:** None here; WEBDAV publish-scope already notes agent-state on full publish.

---

## 4. Checked, no issue

### MCP / CLI do not skip API auth or path checks on the HTTP path

- `LibraryClient` sends `Authorization: Bearer` from `--api-token` / `LIBRARY_API_TOKEN` (`cli/client.py:52-56`). Embedded REPL uses ASGI + the same app middleware (`repl.py:14-16`).
- Stdio MCP HTTP mode uses the same header (`mcp_server.py:313-320, 687`). Embedded MCP fallback mounts `library.main.app` with the same middleware (`:323-336`).
- HTTP `POST /mcp/tools/{name}/call` cannot call `upload_file` / `query_sql` / `finish_research` — only `READ_ONLY_TOOL_NAMES`. Writes go through `/v1/upload` etc. with existing validation.
- CLI slash commands are HTTP wrappers (`cli/commands.py` via client), not raw repository writes (except `eval` and `storage migrate`, which are explicit admin commands).

### Eval retrieval-only path

- `run_eval_dataset` (`retrieval.py:38-50`) bootstraps schema and reads FTS/semantic; it does not import new docs. Damage is ACCESS-M1 on **import** and **react report** probes, not on `eval run`.

### Export secrets / scope

- Conversation export is citation-footnote scoped, not the whole library. Soft-deleted/missing entries go to `manifest.missing` (`exports.py` module doc).
- Metadata JSON allowlist `_EXPORT_METADATA_KEYS` (`:43-60`) has summary/preview/related, not `extra` / `tags` / `catalog_id` / `description` / API keys.
- Zip member names run through `_safe_zip_name` (strips `/` `\` NUL).

### Discovery

- `runtime/server.json` has `base_url`, host, port, pid, home — no token (`server_discovery.py:36-42`). `0.0.0.0` is rewritten to `127.0.0.1` for clients (`:20-21`).

### Init

- `library init` writes a starter `.env` only if missing; does not print or copy API keys (`init_cmd.py`).

---

## 5. Test gaps

| Gap | Why |
|---|---|
| `eval import-beir` with `name=../x` | ACCESS-M2. |
| MCP `_destination_path` with `..` | ACCESS-M2; existing MCP tests may not cover write tools. |
| Eval react probe leaves a `sessions` row | ACCESS-M1 cleanup. |
| Export zip peak memory | ACCESS-M3. |
| HTTP `/mcp/tools/call` of `upload_file` → 400 | Documents the read-only split. |

---

## 6. Suggested follow-up fix children

Do **not** create these in this round.

| Title | Files | Why |
|---|---|---|
| Isolate eval writes (or require --write-library) | `eval/datasets.py`, `eval/probes.py`, `cli/eval_cmd.py` | ACCESS-M1 |
| Jail MCP destination_path + sanitize eval names | `mcp_server.py`, `eval/datasets.py` | ACCESS-M2 |
| Stream conversation export zip | `routes_exports.py` | ACCESS-M3 (can share design with UPLOAD-3) |

---

## 7. Five-angle conclusions

| Angle | Conclusion |
|---|---|
| **Correctness** | CLI/MCP HTTP paths use the real API. Eval import/probes intentionally hit the live DB (ACCESS-M1). Export of unfinished conversations 409s. |
| **Security** | HTTP MCP cannot run write tools or SQL. Stdio MCP and eval CLI can write arbitrary local paths (ACCESS-M2) as the OS user. Export metadata does not leak keys. Route auth is cross-cutting. |
| **Architecture** | Stdio MCP = workflow HTTP client + optional embedded app. HTTP `/mcp` = in-process read-only tools. Eval bypasses the task runner and calls `handle_ingest_file` / `run_turn` directly. |
| **Spec / contract** | Export allowlist matches DESIGN.md §14.3. Knowledge pack agent-state is a WebDAV concern. |
| **Tests** | MCP/CLI/eval/export/discovery e2e exist. Path jail and eval isolation are untested. |

---

## Verification

```
git status --short -- src tests frontend openapi
# clean

uv run pytest tests/ -k "mcp or cli or eval or export or discover or server_main or server_discovery" --collect-only
# 65 selected / 592 deselected
```
