# Implement — Dependency audit + frontend bundle slim

Ordered execution plan. Each phase ends with a validation gate. If a gate fails, stop and fix before continuing.

## Phase 0 — Baseline
- [x] Record baseline frontend bundle sizes: `npm run build` in `frontend/`, note `index-*.js` + `heic2any-*.js` gzip sizes. → `index-ehmX4-Cv.js` gzip **523.78 kB** (raw 1,645.90 kB); `heic2any-*.js` already a separate lazy chunk (gzip 341.24 kB). Build 2026-08-25.
- [x] `.venv/bin/python -m pytest tests/ -q` passes (baseline). → 560 passed, 1 skipped.
- [x] `git status` clean; branch `v4.0`. → clean except untracked task dir.

## Phase 1 — B: dependency removal
1. `pyproject.toml`: remove `moto[s3]>=5.0` from the `dev` extra. ✅
2. Regen `uv.lock`: install uv if absent (`python3 -m pip install --user uv`), then `uv lock --locked` (or into the venv). ✅ `uv 0.12.5` was already present in `.venv` (not on PATH); `.venv/bin/uv lock` → 348 → **107 packages**, removed moto/cryptography/werkzeug etc., kept boto3/aioboto3 (main dep aioboto3).
3. `frontend/package.json`: move `@types/react-syntax-highlighter` from `dependencies` to `devDependencies`. ✅
4. Regen `package-lock.json`: `cd frontend && npm install`. ✅

**Gate A**: `grep -rniI "moto" tests src pyproject.toml` → empty. ✅ `.venv/bin/python -m pytest tests/ -q` passes. ✅ 560 passed, 1 skipped. `cd frontend && npm ci` succeeds; ✅ `@types/react-syntax-highlighter` only under `devDependencies`. ✅

## Phase 2 — C1: route-level lazy loading
1. Read `frontend/src/App.tsx` routes block (~lines 1-45). ✅
2. Convert the 6 non-chat pages to `React.lazy` imports; keep `ChatPage` + `/` redirect static. ✅ Pages are **named exports**, so used `lazy(() => import("@/pages/X").then(m => ({ default: m.X })))`.
3. Wrap `<Routes>` in `<Suspense fallback={...}>` (reuse an existing loading/backdrop component if one exists in the codebase). ✅ Reused `ViewerLoading` from `ViewerShared.tsx` (zustand `useI18n`, no provider needed — verified `useI18n` impl).

**Gate B**: `cd frontend && npm run lint && npm run build` passes; build output now has separate page chunks (`SettingsPage`, `LibraryPage`, …) and a smaller `index-*.js`. ✅ lint clean; 6 page chunks emitted (SettingsPage 13.01KB/gzip, LibraryPage 27.13, HelpPage 3.21, AboutPage 3.09, OverviewPage 2.88, SearchPage 1.93); entry `index-DPFYnisB.js` **1,441.99 kB (gzip 479.56)** ↓ from 1,645.90/523.78. (A second `index-B9qSyfep.js` 351.49 kB is a shared vendor chunk extracted for the lazy pages — contains none of the markdown stack.)

## Phase 3 — C2: lazy syntax highlighter
1. Read `frontend/src/components/MarkdownView.tsx` fully — especially `CodeRenderer` (~L191-250) and its copy-button/theme props. ✅
2. Create `frontend/src/components/CodeBlock.tsx`: lazy component that `await import("react-syntax-highlighter")` + Prism styles on first fenced-block render; preserve copy button, line numbers, theme toggle. ✅ New file; header (copy button) renders instantly, raw text `<pre>` fallback until the chunk arrives, then highlighting fills in. Uses `Promise.all` over both dynamic imports; `import type { SyntaxHighlighterProps }` keeps types accurate with zero runtime cost.
3. `MarkdownView.tsx`: drop the static highlighter imports (L20-21); route fenced blocks through `CodeBlock`. ✅ Removed static imports + old local `CodeBlock`; `CodeRenderer` delegates fenced → `CodeBlock`. Also dropped now-unused `useTheme`/`useTemporaryValue`/`useI18n` imports (noUnusedLocals is on).

**Gate C**: `npm run lint && npm run build` passes; `react-syntax-highlighter` no longer in `index-*.js` (appears as its own lazy chunk). ✅ lint clean. Entry `index-BNjc7Kde.js` (gzip **257.88 kB**) contains no `react-syntax-highlighter`; the package is now its own lazy chunk (`index-BIYZwKU7.js` 976 kB / 308 gzip) + Prism styles chunk (`prism-D8xh5Yco.js` 651 kB / 225 gzip), plus the fenced-block logic split into `index-DEZ_zdKX.js`. No chunk carries the static style import → no duplication.

## Phase 4 — Full verification
1. `npm run build` → record new `index-*.js` gzip; compare vs Phase 0 (expect a meaningful drop). ✅ Entry `index-BNjc7Kde.js` gzip **257.88 kB** (raw 819.90 kB) vs baseline 523.78 kB → **−50.8% initial JS gzip**. `index.html` has no modulepreloads → true initial load = entry JS 257.88 + CSS 18.48 kB gzip. Highlighter stack (react-syntax-highlighter chunk 308 gzip + Prism styles 225 gzip) + fenced-logic chunk (17.89 gzip) + 6 page chunks all load on demand.
2. `.venv/bin/python -m pytest tests/ -q` passes. ✅ 560 passed, 1 skipped.
3. GUI smoke (real browser: Playwright 1.62.1 driving cached chromium-1234 against `vite dev` + live backend):
   - ✅ `/chat` loads immediately; all 6 lazy routes render (no blank/error, no page errors, no console errors). App.tsx serves 6 `lazy()` + ViewerLoading fallback; CodeBlock dynamic imports preserved under Vite's transform.
   - ✅ **Code-block path** end-to-end: pointed chat profile at a throwaway mock OpenAI server (base_url/model only; API key untouched; full overlay file backed up first) → sent a message in quick mode → streamed answer with a fenced python block rendered **HIGHLIGHTED** (17 `span[class*="token"]` elements → lazy highlighter chunk loaded), language label `python`, **copy button `copy → copied`** (clipboard write confirmed). Zero page errors. Config restored **byte-identical** (verified `diff` against backup + GET resolves original base_url/model).
   - Rich viewers: **no viewer code touched** (already `await import` lazy since before this task); `/library` route renders. No regression surface — noted, not re-exercised with real docx/xlsx/epub/HEIC files.

**Gate D**: all above pass; `git diff --stat` shows only pyproject/package.json/App.tsx/MarkdownView(+CodeBlock)/lockfiles touched. ✅ (`pyproject.toml` −1, `uv.lock` −208, `package.json`/`package-lock.json` types-move, `App.tsx` +58/−, `MarkdownView.tsx` −49, +`CodeBlock.tsx`.)

## Phase 5 — Commit + archive
1. Commit: `Slim deps and frontend bundle: drop unused moto, lazy-load routes and code highlighter`.
2. `task.py finish` to archive.

## Rollback points
- B: `git checkout pyproject.toml uv.lock` restores; moto only affects dev env.
- C: revert `App.tsx` + `MarkdownView.tsx` (and delete `CodeBlock.tsx`) — pure load-timing change, no data impact.
- Always stop and report on any gate failure instead of proceeding.
