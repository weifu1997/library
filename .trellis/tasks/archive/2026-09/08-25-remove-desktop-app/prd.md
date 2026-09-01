# Remove desktop/Tauri app code

## Goal

Remove the Tauri desktop-app (exe) shell and every trace of desktop/Tauri/Electron from the shipped project (source, frontend, scripts, CI/CD, tests, docs, changelog), while keeping the **browser-based Web GUI** (React + Vite frontend) fully functional.

Decisions confirmed with the user:

1. **Keep the browser GUI** — only remove the exe shell. The `desktop/` directory contains both the Tauri shell *and* the web frontend; only the shell is removed.
2. **Rename `desktop/` → `frontend/`** so no desktop-titled directory remains.
3. **CHANGELOG**: thoroughly purge desktop mentions from historical entries too ("彻底清除历史").

## Requirements

### Remove (delete)
- `frontend/src-tauri/` (whole Rust/Tauri shell: Cargo.toml, lib.rs, capabilities, icons, package/*, resources/backend, tauri.conf.json)
- Tauri npm deps in `frontend/package.json`: `@tauri-apps/api`, `@tauri-apps/plugin-opener`, `@tauri-apps/cli`
- Tauri-specific frontend code:
  - `frontend/src/lib/openExternal.ts` (whole file)
  - `frontend/src/lib/frontendLog.ts` (whole file)
  - `resolveTauriBaseUrl` / `isTauri` / `__TAURI*` logic in `api/client.ts`, `api/chatStream.ts`, `components/BackendGate.tsx`, `App.tsx`, `main.tsx`
  - `interceptExternalLink` usage in `pages/AboutPage.tsx`, `components/MarkdownView.tsx`
- Desktop-only build scripts: `scripts/prepare-backend.mjs`, `scripts/package-windows-portable.mjs`, `scripts/cpython/resolve_packaged_cpython_runtime.py` (called only by `prepare-backend.mjs`)
- Desktop/Tauri jobs & steps in `.github/workflows/release.yml` (whole `desktop:` job + artifact handling) and `.github/workflows/ci.yml` (`tauri-check` job, `desktop` path refs)
- Backend `LIBRARY_DESKTOP` handling and Tauri CORS origins in `src/library/main.py`
- Desktop path exclusions for `src-tauri/target` in `pyproject.toml`

### Modify
- `frontend/src/api/client.ts`, `chatStream.ts`, `BackendGate.tsx`, `App.tsx`, `main.tsx` — strip Tauri logic so the GUI is a plain browser app connecting to a separately-run backend
- `frontend/vite.config.ts` — remove `TAURI_` env prefix + Tauri comments
- `frontend/package.json` — rename package to `library-frontend`, drop Tauri deps
- `frontend/tsconfig.json` — drop `src-tauri` from `exclude`
- `.github/workflows/ci.yml` — rename `frontend-build` job to point at `frontend/`; delete `tauri-check`
- `.github/workflows/release.yml` — release pipeline builds/publishes only the Docker image
- Backend comments in `src/library/config.py`, `services/worker_lifecycle.py`, `services/user_files.py`, `db/bootstrap.py`, `cli/repl.py`, `cli/init_cmd.py`, `api/routes_user_files.py` — reword/remove "desktop" mentions
- Test docstrings in `tests/test_settings_routes_e2e.py`, `tests/test_gui_search_multiword_unit.py`, `tests/test_file_entry_path_e2e.py` — "desktop GUI" → web GUI
- `.env.example` — remove desktop/Tauri comments
- Docs: `README.md`, `README.zh-CN.md`, `USAGE.md`, `USAGE.zh-CN.md`, `DESIGN.md`, `CHANGELOG.md`, `docs/GUI_TUTORIAL.md`, `docs/GUI_TUTORIAL.zh-CN.md`, `docs/LAUNCH.md`, `docs/UPGRADE-PLAN.md`, `samples/architecture.md` — remove desktop app sections/mentions

### Explicitly NOT modified (allowed to keep "desktop" text)
- Historical `alembic/` migration files (never rewrite migrations)
- `.trellis/tasks/*` internal planning archives (not shipped content)
- Unrelated third-party/OS matches: `Rar.exe` (WinRAR), `cmd.exe` (Windows shell), upstream `AstrBot-dev/AstrBot-desktop` repo provenance, `.codex/config.toml` (Codex's own desktop app)

## Acceptance Criteria

- [ ] `desktop/` renamed to `frontend/`; no `src-tauri` anywhere in it
- [ ] `frontend/package.json` has no `@tauri-apps/*` deps
- [ ] `npm ci && npm run lint && npm run build` pass in `frontend/` (no Tauri imports)
- [ ] Browser GUI still connects to the backend: dev-mode Vite proxy to 127.0.0.1:8000, and via `VITE_API_BASE` / Settings → Connection override
- [ ] `scripts/` no longer contains `prepare-backend.mjs`, `package-windows-portable.mjs`, or a desktop-only `cpython/` resolver
- [ ] `.github/workflows/release.yml` has no `desktop` job and publishes only the Docker image
- [ ] `.github/workflows/ci.yml` has no `tauri-check` job; `frontend-build` uses `frontend/`
- [ ] `src/library/main.py` has no `LIBRARY_DESKTOP` and no `tauri://` CORS origins
- [ ] `uv run ruff check src tests` passes
- [ ] `uv run pytest tests/ -q` passes (backend tests unaffected by refactor)
- [ ] `grep -rniE "desktop|tauri|electron" frontend src scripts docs .github pyproject.toml .env.example tests README.md USAGE.md DESIGN.md CHANGELOG.md` finds **no matches** in shipped content (allow the explicit exclusions above)
- [ ] No functional regression: CLI (`library serve`) and web GUI still work together

## Notes

- The frontend no longer auto-launches/restarts the backend (that was Tauri's job). The browser GUI now requires the backend to be started separately (`library serve` / Docker) and documents this in the GUI's waiting screen.
- This is a complex task → has `design.md` + `implement.md`.
