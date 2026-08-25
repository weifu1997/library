# Design — Remove desktop/Tauri shell, keep browser GUI

## Context

The project ships two GUIs from one React codebase in `desktop/`:

1. **Desktop app** — Tauri (Rust) shell that bundles the backend sidecar, auto-launches it, resolves its ephemeral port, and provides IPC commands (`backend_status`, `backend_base_url`, `backend_port`, `restart_backend`, `quit_app`, `set_ui_language`, `append_frontend_log`, `logs_dir`).
2. **Browser GUI** — the same React app served by Vite (port 5173), with `/v1` and `/health` proxied to `127.0.0.1:8000` in dev; in production it uses `VITE_API_BASE` or the Settings → Connection override.

Goal: delete the Tauri shell and all desktop packaging/CI/docs, keep a pure browser frontend.

## Frontend refactor (biggest piece)

The browser GUI must no longer depend on Tauri IPC. The backend is assumed to be running separately (`library serve` / Docker / remote host).

### API base URL resolution — `frontend/src/api/client.ts`
Current precedence: localStorage override → `VITE_API_BASE` → Tauri invoke (`backend_base_url`/`backend_port`) → `""` (vite proxy).
New precedence: **localStorage override → `VITE_API_BASE` → `""` (vite proxy).**

- Remove: `isTauri()`, `resolveTauriBaseUrl`, `_tauriResolved`, the `if (!_base && isTauri()) await resolveTauriBaseUrl()` branches in `_request` and `uploads.upload`.
- Keep: `initialBase()` (drop the Tauri comment), `resetResolvedBaseUrl` becomes unnecessary — remove it and its BackendGate use; `clearBaseUrlOverride` stays (clears the user override back to `""`/`VITE_API_BASE`), but its Tauri-specific doc comments are removed.
- All fetch calls then use `_base` which is `""` in the default dev case → same-origin `/v1/*` via the Vite proxy.

### `frontend/src/api/chatStream.ts`
- Remove the `resolveTauriBaseUrl` import and the two `if (!getBaseUrl()) await resolveTauriBaseUrl();` guards. A falsy base URL is fine — the fetch is relative through the proxy.

### `frontend/src/main.tsx`
- Remove `resolveTauriBaseUrl` kick-off, `frontendLog`/`installFrontendErrorLogging`, and `isTauri()`. Router is always `BrowserRouter`.

### `frontend/src/App.tsx`
- Remove `isTauri()` and the `set_ui_language` effect (tray-menu locale sync — tray lives in the Rust shell, now gone).

### `frontend/src/components/BackendGate.tsx`
This gate currently polls `/health` and, when Tauri is present, can read backend status, restart the backend, and quit the app. New behavior (browser-only):
- Keep the `/health` poll loop (POLL_INTERVAL_MS / PER_ATTEMPT_TIMEOUT_MS / STALE_THRESHOLD_MS).
- Remove: `fetchBackendStatus()` (Tauri `backend_status`), the fatal-state flow that depended on it, `restart_backend` and `quit_app` invoke calls, `getTauriLogDir`.
- "Retry" button: just re-enter the poll loop (no invoke).
- "Quit" button: drop or replace with `window.close()` only — a browser tab has no backend to quit. Keep it minimal.
- Custom-base banner (`isTauri() && baseUrlOverride`): keep the banner for any base override, but remove the Tauri-only "useBundled" button (there is no bundled backend) — clearing the override can still be offered.
- Waiting screen: reword the log-dir hint to tell the user to start the backend (`library serve` / Docker), since the GUI can no longer start it.
- i18n keys that become unused (e.g. `backend.useBundled`) may be left or trimmed — verify at implement time; unused keys are harmless if left.

### Delete Tauri-only files
- `frontend/src/lib/openExternal.ts` — browsers open `target="_blank"` natively. Remove `interceptExternalLink` imports/calls in `pages/AboutPage.tsx` and `components/MarkdownView.tsx`.
- `frontend/src/lib/frontendLog.ts` — Tauri IPC logging is a no-op in the browser. Remove its imports from `BackendGate.tsx` (and any others after the refactor).

### Build config
- `frontend/vite.config.ts`: `envPrefix` → `["VITE_"]`, update header comment (no Tauri mode).
- `frontend/package.json`: drop `@tauri-apps/api`, `@tauri-apps/plugin-opener`, `@tauri-apps/cli`; rename package to `library-frontend`; remove `tauri`/`tauri:dev`/`tauri:build` scripts.
- `frontend/tsconfig.json`: remove `src-tauri` from `exclude`.
- Delete `frontend/src-tauri/` entirely; delete `frontend/index.html`? — no, `index.html` is the Vite entry, keep it.
- `frontend/package-lock.json` regenerated via `npm ci`.

### Directory rename
- `git mv desktop frontend` (tracked files only; `node_modules/`, `dist/` are gitignored and regenerated). Update every path reference: CI `working-directory`/`cache-dependency-path`, `pyproject.toml` lint excludes (`frontend/node_modules`, drop `frontend/src-tauri/target`), `.env.example` comments, docs.

## Backend changes

### `src/library/main.py`
- Remove `LIBRARY_DESKTOP` from the startup log line and delete the soft-fail branch: all launches now `validate_llm_config(settings)` (this is the historical web/CLI behavior; the web GUI first-run with no API key is covered by the settings page, same as before desktop existed).
- CORS: remove the three Tauri origins (`tauri://localhost`, `http://tauri.localhost`, `https://tauri.localhost`). Keep `localhost:5173` / `127.0.0.1:5173` (Vite dev) plus the existing non-desktop origins. Update the comment above `add_middleware`.

### Comments only
- `config.py`: reword "desktop/global home `.env`" — the home-`.env` fallback stays (it's generically useful); drop the "packaged desktop CLI wrappers" framing.
- `services/worker_lifecycle.py`, `services/user_files.py`, `db/bootstrap.py`, `cli/repl.py`, `cli/init_cmd.py`, `api/routes_user_files.py`: replace "desktop"/"desktop GUI" with "web GUI"/"GUI" or reword to drop the desktop app framing.

## CI/CD

### `.github/workflows/ci.yml`
- Delete `tauri-check` job (and the Linux Tauri system deps step).
- `frontend-build`: rename display name "desktop tsc + vite build" → "frontend tsc + vite build"; `working-directory: frontend`; `cache-dependency-path: frontend/package-lock.json`.
- Update header comment (jobs list).

### `.github/workflows/release.yml`
- Delete the entire `desktop:` job.
- `publish-release`: `needs: [docker]`; remove "Download desktop artifacts" step; rewrite the release-notes block to describe only the Docker image (no desktop bundles, no unsigned-binary notes); the publish step stops globbing `release-assets/*` — decide: publish the Docker image only (no file assets) → drop `release-assets/*` from `gh release create`; remove both "Verify built assets" and "Verify release assets" steps (desktop-only).
- Rewrite the header comment: what the pipeline produces (Docker image only).
- The `lock-check` job stays.

## Scripts
- Delete `scripts/prepare-backend.mjs`, `scripts/package-windows-portable.mjs`.
- Delete `scripts/cpython/resolve_packaged_cpython_runtime.py` (only called by `prepare-backend.mjs`); if `scripts/cpython/` holds only this file, remove the directory.
- `scripts/UPSTREAM.md`: lines 5/9 reference the *upstream* `AstrBot-desktop` repo (provenance — keep). Lines 34/38-39 describe Library-vs-upstream layout; adjust any text that implies Library ships a Tauri desktop shell.
- `scripts/ci/` — check for desktop refs; trim if present.

## Docs & tests
- Docs: strip the "Desktop App" sections (download links, installers, screenshots) from README/README.zh-CN/USAGE/USAGE.zh-CN; reword GUI-TUTORIAL/LAUNCH/UPGRADE-PLAN/DESIGN/samples/architecture; CHANGELOG — purge all desktop/tauri/exe mentions (user decision).
- Tests: three docstrings reference "desktop GUI" — reword to "web GUI" (the tests themselves target the backend API and are unaffected).

## Rollback shape
- All changes are tree-level; `git checkout -- <files>` / `git restore` reverses the working tree. The deleted `desktop/` is recoverable from git history. No schema/data migration involved.

## Open items verified during implementation
- `frontend/src/lib/i18n.ts` — no Tauri refs (confirmed).
- Whether `scripts/ci` contains desktop references (verify).
- `docs/images/desktop-screenshot-*.jpg` references (remove from docs; images can be deleted if only used by removed sections).
