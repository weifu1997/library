# Design — Dependency audit + frontend bundle slim

## Boundary

**B** touches dependency manifests + lockfiles only — no source code. **C** touches frontend load timing only — no behavior change, no backend change.

## B — moto removal

`moto[s3]` (dev extra) has **zero references** repo-wide (`grep -rniI "moto" --include="*.py"` → empty). It exists only to mock S3 in tests; no test imports it, so it is dead weight in the dev environment (pulls boto3/botocore + friends). Safe to delete from `pyproject.toml` dev extra. The main dependency list stays intact — the 4 non-imported deps (aiosqlite/asyncpg/greenlet/python-multipart) are runtime dialect/driver requirements confirmed by config URLs and FastAPI form/upload handling.

Lockfile regen:
- `uv.lock`: requires `uv`. Local machine has no `uv` binary on PATH (only the committed `.venv`, created by uv). Approach: `python3 -m pip install --user uv` (or into `.venv`), then `uv lock --locked` to refresh uv.lock after the pyproject edit. CI's `lock-check` job (`uv lock --locked`) is the final authority — must pass before push.
- `package-lock.json`: `npm install` after moving `@types/react-syntax-highlighter` to devDependencies.

## C — frontend code-splitting

### Current state (verified)
- Rich readers already dynamic: `OfficeViewer` (`await import("@silurus/ooxml/docx|pptx|xlsx")`), `EpubViewer` (`await import("epubjs")`), `ImageViewer` (`await import("heic2any"/"utif")`). Build shows `heic2any-*.js` as a separate chunk already.
- Main chunk heavies: (1) `MarkdownView` statically imports `react-markdown`, `react-syntax-highlighter` + Prism styles (`vscDarkPlus`/`prism`), `katex` (+ css), `remark-gfm`, `remark-cjk-friendly`, `remark-math`, `remark-github-blockquote-alert`, `rehype-katex`; (2) `App.tsx` statically imports all 7 page components.

### C1 — Route-level lazy loading
`App.tsx` (routes at lines 32-43) converts the 6 non-chat pages to:
```tsx
const LibraryPage = lazy(() => import("@/pages/LibraryPage"));
const SearchPage = lazy(() => import("@/pages/SearchPage"));
// ... OverviewPage, SettingsPage, HelpPage, AboutPage
```
Wrap `<Routes>` in `<Suspense fallback={<Loading… />}>`. `ChatPage` and the `/` → `/chat` redirect stay static (initial route). react-router-dom 7 + React 18 support this natively.

### C2 — Lazy syntax highlighter
`MarkdownView.tsx` imports `Prism as SyntaxHighlighter` + two Prism style objects at module top (lines 20-21). The `CodeRenderer` component (line 191+) renders `<SyntaxHighlighter>` only for fenced blocks (line 232); inline code is a plain `<code>`.

Extract the fenced-code branch into a new lazy component, e.g. `frontend/src/components/CodeBlock.tsx`:
- `CodeBlock` does `const { default: SyntaxHighlighter } = await import("react-syntax-highlighter")` + `const style = await import("./styles...")` on first mount (or use `React.lazy` + a wrapper that receives children/className), preserving the copy button, line numbers, and theme toggle behavior already in `CodeRenderer`.
- `MarkdownView` drops the static highlighter import; the top-level markdown stack (react-markdown/katex/remark) stays in main chunk but the largest single lib (Prism highlighter + styles) moves to its own lazy chunk.

### Ordering & risks
- Do C1 before C2 (C1 is mechanical and independently verifiable; C2 needs care to preserve code-block UX).
- Risk: Suspense fallback UX on first navigation; first code-block render incurs a chunk fetch. Mitigate with a simple spinner fallback and keep `preload`/hover heuristics out of scope.
- No SSR (pure SPA), so `React.lazy` has no hydration concerns.

## Verification hooks
- Record pre/post `index-*.js` gzip sizes from `npm run build` output (or `ls -S dist/assets`).
- GUI smoke: initial `/chat` loads; navigate each lazy route; render a markdown response with a fenced code block and confirm highlighting + copy.
- Backend untouched by C; B is covered by `pytest` + lockfile sync.
