# Implement — Remove desktop/Tauri shell, keep browser GUI

Ordered execution plan. Each phase ends with a validation gate. If a gate fails, stop and fix before continuing.

## Phase 0 — Baseline
- [ ] `uv run ruff check src tests` passes (baseline)
- [ ] `uv run pytest tests/ -q` passes (baseline, before any change)
- [ ] Snapshot git state: `git status` clean, branch `v4.0`

## Phase 1 — Frontend de-Tauri (code changes in `desktop/`)
1. `desktop/src/api/client.ts` — remove `isTauri`, `resolveTauriBaseUrl`, `_tauriResolved`, `resetResolvedBaseUrl`, tauri fetch guards; simplify base-URL precedence comment.
2. `desktop/src/api/chatStream.ts` — drop `resolveTauriBaseUrl` import + 2 guards.
3. `desktop/src/lib/openExternal.ts` — delete file; strip `interceptExternalLink` from `pages/AboutPage.tsx`, `components/MarkdownView.tsx`.
4. `desktop/src/lib/frontendLog.ts` — delete file; strip imports from remaining files.
5. `desktop/src/main.tsx` — always `BrowserRouter`; remove tauri kick-off/logging.
6. `desktop/src/App.tsx` — remove `isTauri` + `set_ui_language` effect.
7. `desktop/src/components/BackendGate.tsx` — remove tauri invoke paths (see design); keep `/health` poll; reword backend-not-running guidance.
8. `desktop/vite.config.ts` — `envPrefix: ["VITE_"]`, update comments.
9. `desktop/package.json` — drop `@tauri-apps/*`, rename to `library-frontend`, remove tauri scripts.
10. `desktop/tsconfig.json` — drop `src-tauri` from `exclude`.

**Gate A**: `cd desktop && npm ci && npm run lint && npm run build` → clean (no tauri imports, no TS errors). If `npm ci` fails on lockfile drift, run `npm install` then `npm install` again to refresh `package-lock.json`.

## Phase 2 — Directory rename + delete Tauri shell
1. `git mv desktop frontend` (tracked files; `node_modules`/`dist` regenerate later).
2. `rm -rf frontend/src-tauri` (shell, icons, package/, resources/backend).
3. Regenerate deps: `cd frontend && rm -rf node_modules && npm ci && npm run build` (confirms rename didn't break paths; dist/ rebuilt).
4. Delete desktop-only scripts: `scripts/prepare-backend.mjs`, `scripts/package-windows-portable.mjs`, `scripts/cpython/resolve_packaged_cpython_runtime.py` (and `scripts/cpython/` if empty of other use).
5. Update `pyproject.toml`: exclude `frontend/node_modules`; drop `frontend/src-tauri/target` lines.

**Gate B**: `git status` shows rename as a move; `frontend/` builds; `scripts/` has no desktop packagers; `grep -r "src-tauri" frontend pyproject.toml scripts` → empty.

## Phase 3 — Backend
1. `src/library/main.py`: drop `LIBRARY_DESKTOP` from log + lifespan branch (always `validate_llm_config`); remove 3 Tauri CORS origins; update comments.
2. Comment rewords: `src/library/config.py`, `services/worker_lifecycle.py`, `services/user_files.py`, `db/bootstrap.py`, `cli/repl.py`, `cli/init_cmd.py`, `api/routes_user_files.py`.
3. `.env.example`: remove desktop/Tauri comment lines (keep `RUNTIME_SCHEMA_BOOTSTRAP_ENABLED` semantics).

**Gate C**: `grep -rniE "desktop|tauri|electron" src .env.example` → empty (except allowed exclusions). `uv run ruff check src tests` → clean.

## Phase 4 — CI/CD
1. `.github/workflows/ci.yml`: delete `tauri-check` job; `frontend-build` → `working-directory: frontend`, `cache-dependency-path: frontend/package-lock.json`, rename display; update header comment.
2. `.github/workflows/release.yml`: delete `desktop:` job; `publish-release` → `needs: [docker]`, drop artifact download, rewrite release notes (Docker only), drop file-asset glob + both asset-verification steps; rewrite header comment.
3. Check `.github/workflows/*` for other desktop refs.

**Gate D**: `grep -rniE "desktop|tauri|electron|nsis|appimage|\.dmg\b|\.exe\b" .github` → empty. YAML parses (`python3 -c "import yaml,sys; list(map(lambda f: yaml.safe_load(open(f)), sys.argv[1:]))" .github/workflows/*.yml`).

## Phase 5 — Tests + docs
1. Reword desktop-GUI docstrings in `tests/test_settings_routes_e2e.py`, `tests/test_gui_search_multiword_unit.py`, `tests/test_file_entry_path_e2e.py`.
2. Docs: README.md, README.zh-CN.md, USAGE.md, USAGE.zh-CN.md, DESIGN.md, CHANGELOG.md, docs/GUI_TUTORIAL.md, docs/GUI_TUTORIAL.zh-CN.md, docs/LAUNCH.md, docs/UPGRADE-PLAN.md, samples/architecture.md — remove desktop sections/mentions. CHANGELOG: purge all desktop/tauri/exe entries (user chose full purge). Delete `docs/images/desktop-screenshot-*.jpg` if only used by removed sections; check `samples/architecture.md` diagram text.

**Gate E**: `grep -rniE "desktop|tauri|electron" README.md README.zh-CN.md USAGE.md USAGE.zh-CN.md DESIGN.md CHANGELOG.md docs samples tests` → empty. Re-check `scripts/` and `.env.example` too.

## Phase 6 — Full verification
1. `uv run ruff check src tests`
2. `uv run pytest tests/ -q`
3. `cd frontend && npm run lint && npm run build`
4. [x] Smoke test: start `library serve` (or the dev backend) + `npm run dev`; confirm GUI loads and `/health` passes.
5. Final grep across shipped content: `grep -rniE "desktop|tauri|electron" frontend src scripts docs .github tests pyproject.toml .env.example README.md README.zh-CN.md USAGE.md USAGE.zh-CN.md DESIGN.md CHANGELOG.md` → **no matches**.
6. Allowed remaining "desktop" text (verify only these): `.trellis/tasks/*`, `alembic/versions/*`, `Rar.exe`, `cmd.exe`, upstream `AstrBot-desktop` (`scripts/UPSTREAM.md` attribution), `.codex/config.toml`, **"Claude Desktop"** (third-party MCP client product, not the removed app — keep verbatim), **`electron-to-chromium`** (npm transitive dep for Vite/browserslist Chromium version mapping, not the Electron runtime).

**Gate F**: everything above passes. If pytest has unrelated pre-existing failures, compare against Phase-0 baseline and report.

## Phase 7 — Spec update + commit
1. Update `.trellis/spec/guides/*` if they reference desktop (check `cross-layer-thinking-guide.md` etc. — likely generic; leave unless desktop-specific).
2. Commit with a clear message: `Remove desktop/Tauri app shell, keep browser GUI (rename desktop/ → frontend/)`.
3. Update `CHANGELOG.md` Unreleased section with the removal note (after purge).
4. Archive task via `task.py finish`.

## Rollback points
- After any phase: `git restore --staged . && git restore .` returns the tree to pre-change state (desktop/ recoverable from history).
- The frontend de-Tauri is the only phase with behavioral change (backend no longer auto-launched by GUI) — verify Gate A + Phase 6 smoke before considering the refactor done.
