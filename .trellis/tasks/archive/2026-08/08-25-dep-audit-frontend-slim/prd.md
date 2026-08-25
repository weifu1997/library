# 依赖审计 + 前端体积瘦身（B 未用依赖清理 + C 富阅读器按需加载）

## Goal

**B** — 审计并移除真正未使用的依赖。**C** — 缩小前端首屏 bundle。

User decision: B+C 合并为一个任务（已确认）。

## B — 依赖审计结论（已完成只读审计）

### 后端 `pyproject.toml`（29 main deps + extras）
- **29 个 main deps 全部在用**，无移除对象。其中 4 个无直接 `import` 但为**运行时驱动**，必须保留：
  - `aiosqlite` / `asyncpg` — SQLAlchemy 方言（`sqlite+aiosqlite://`、`postgresql+asyncpg://`）
  - `greenlet` — SQLAlchemy asyncio 的运行时依赖
  - `python-multipart` — FastAPI `UploadFile`/`Form` 解析所需
- **`moto[s3]`（dev extra）→ 全仓 0 引用，移除** ✅（唯一真正的未用依赖）
- `semantic` extra 的 `sqlite-vec` → `semantic/index.py` 条件 `find_spec` 使用，保留
- dev extra 其余（pytest、pytest-asyncio、fpdf2、ruff）→ 均有使用，保留

### 前端 `frontend/package.json`（20 deps + 9 devDeps）
- **20 个 deps 全部在用**，无移除对象
- **`@types/react-syntax-highlighter` 放在 `dependencies`，应属 `devDependencies`**（类型包，不进运行时）→ 移到 devDeps（卫生调整）

## C — 前端 bundle 审计结论（已完成只读审计）

**关键事实：富阅读器已经按需加载了。** `OfficeViewer`/`EpubViewer`/`ImageViewer` 均用 `await import("@silurus/ooxml/...")`、`await import("epubjs")`、`await import("heic2any"/"utif")`；构建产物里 `heic2any` 已是独立 chunk。**这部分无需改动。**

剩余重量在主 chunk（`index-*.js` 1.6MB / gzip 523KB）：
1. **`MarkdownView.tsx` 静态导入的 markdown 栈**：`react-markdown` + `react-syntax-highlighter`（含 Prism 样式）+ `katex` + `remark-gfm/cjk-friendly/math/github-blockquote-alert` + `rehype-katex` — 这是主 chunk 最大可瘦身项。
2. **所有页面静态导入**：`App.tsx` 无懒加载，`SettingsPage`(63K)/`ChatPage`(35K)/`LibraryPage`/`SearchPage`/`OverviewPage`/`HelpPage`/`AboutPage` 全在主 bundle。

### C 方案（两档）
- **C1 路由级懒加载**：`React.lazy` 懒加载 `LibraryPage`/`SearchPage`/`OverviewPage`/`SettingsPage`/`HelpPage`/`AboutPage`，`ChatPage` 保持静态（首屏路由是 `/chat`）。低风险、机械改动。
- **C2 语法高亮器懒加载**：`MarkdownView` 的 `CodeRenderer`（约 L232 的 `<SyntaxHighlighter>`）抽成懒加载的 `CodeBlock` 组件，首个代码块渲染时才 `import("react-syntax-highlighter")` + Prism 样式。移除主 chunk 中最大单体库之一。

## Requirements

### B
- [ ] 从 `pyproject.toml` dev extra 移除 `moto[s3]>=5.0`
- [ ] 前端：`@types/react-syntax-highlighter` 从 `dependencies` 移到 `devDependencies`
- [ ] 重新生成 `uv.lock`（需要 uv）与 `package-lock.json`（`npm install`），保持锁文件与声明同步

### C
- [ ] `App.tsx`：6 个非 chat 页面改 `React.lazy`，外层 `<Suspense fallback>`；`ChatPage` 与根重定向保持静态
- [ ] `MarkdownView.tsx`：`<SyntaxHighlighter>` 抽成 `CodeBlock` 懒加载组件（保留现有点击复制、行号、主题切换行为）
- [ ] 富阅读器的既有 `await import` 保持不动

## Acceptance Criteria

- [ ] `grep -rniI "moto" tests src pyproject.toml` → 无匹配；`uv.lock` 已同步
- [ ] `npm ci` 可安装；`@types/react-syntax-highlighter` 仅存在于 `devDependencies`
- [ ] 后端：`.venv/bin/python -m pytest tests/ -q` 通过（与基线一致）
- [ ] 前端：`npm run lint` 通过；`npm run build` 成功
- [ ] **主 chunk 首屏体积显著下降**（记录构建前后 `index-*.js` gzip 体积对比）
- [ ] GUI 冒烟：首屏 `/chat` 立即加载；导航到 `/settings`、`/library`、`/overview`、`/search`、`/help`、`/about` 均正常渲染
- [ ] Markdown 代码块仍正常语法高亮 + 复制按钮可用（懒加载 CodeBlock 路径）
- [ ] 富阅读器功能不回归（docx/xlsx/pptx/epub/图片查看）

## Notes

- B 的审计方法是「按 package→import 名映射做 src/ 全量 grep + 运行时驱动人工确认」，已规避误判；`moto` 为全仓 `grep -rniI` 0 命中，可信。
- C 不改变任何功能行为，只是加载时机变化；首次打开非 chat 页面/首个代码块会有短暂 Suspense，属预期。
- 本地无 `uv` 可执行文件（记忆库已记录）——重新生成 `uv.lock` 需要临时安装 uv 或 `python3 -m pip install uv`，见 implement。
- 这是复杂任务 → 有 `design.md` + `implement.md`。
