# Journal - weifu1997 (Part 1)

> AI development session journal
> Started: 2026-08-23

---


## 2026-08-25 — remove-desktop-app task progress

- Phase 0 (baseline): ruff + pytest pass, git clean on v4.0.
- Phase 1 (frontend de-Tauri): client.ts / chatStream.ts / main.tsx / App.tsx / BackendGate.tsx / vite.config.ts / package.json / tsconfig.json / i18n.ts rewritten; openExternal.ts + frontendLog.ts deleted; Gate A (lint+build) pass.
- Phase 2 (rename+shell delete): `desktop/` → `frontend/`, `frontend/src-tauri/` deleted, desktop packager scripts deleted, pyproject.toml/.gitignore/UPSTREAM.md updated; Gate B pass.
- Phase 3 (backend): main.py de-LIBRARY_DESKTOP + CORS, 8 comment rewords, .env.example cleaned; Gate C (grep + ruff) pass.
- Phase 4 (CI/CD): ci.yml (drop tauri-check, frontend-build→frontend), release.yml (drop desktop job, Docker-only publish); Gate D pass.
- Phase 5 (tests+docs): 3 test docstrings reworded; README en/zh rewritten (Desktop App → Web GUI, screenshots deleted); skills/ cleaned; .gitignore cleaned. DESIGN.md + samples/architecture.md cleaned (subagent). In progress: CHANGELOG full purge, GUI_TUTORIAL en/zh rewrite, USAGE/LAUNCH/UPGRADE-PLAN (subagents running). Pending Gate E grep + Phase 6 full verification + Phase 7 commit.

- Phase 5 complete: CHANGELOG full purge (agent: 21 desktop-only bullets deleted, 8 mixed rewritten), GUI_TUTORIAL en/zh rewritten to browser workflow (agent), USAGE/LAUNCH/UPGRADE-PLAN cleaned (agent, kept 4 Claude Desktop refs), DESIGN + samples/architecture rewritten to Docker-only release (agent), skills/ cleaned, .gitignore cleaned.
- Phase 6 complete: ruff clean, pytest 560 passed/1 skipped, frontend lint+build pass, smoke test (backend /health OK, GUI loads on Vite, proxy OK). Final grep clean except legit: Claude Desktop (MCP client), AstrBot-desktop upstream, electron-to-chromium (npm transitive dep), CHANGELOG removal note.
- Cleanup: killed stale Vite dev server (pid 1055/1056, pointed at deleted desktop/, was recreating desktop/.vite — user approved kill), removed recreated desktop/ dir.
- Phase 7 complete: spec guides clean, CHANGELOG Unreleased removal note added, committed as 3123650 ("Remove desktop/Tauri app shell, keep browser GUI"), task.py finish archived task.


## Session 1: 全量代码审查：审计、两个 High 安全修复与八项后续治理

**Date**: 2026-08-31
**Task**: 全量代码审查：审计、两个 High 安全修复与八项后续治理
**Branch**: `v4.0`

### Summary

对 129k 行代码库做全量审查（后端 69k / 前端 22k / 测试 38k），产出分级报告后逐条修复。自动化基线本就干净（ruff/tsc 全过、零 any、无 eval/shell 注入面），问题是在此之上挖出的。

两个 High 均已复现并修复：WebDAV 二次导入可造出目录环、随后 _folder_path 无限循环挂死 worker（回归测试以 TimeoutError 复现了真实死循环）；PDF OCR 逐页失败与空白页共用 '' 语义，导致限流丢页的文档被标记为入库成功（静默数据丢失）。

安全面补两处：CORS 中间件此前注册在最内层，401/413 响应不带 CORS 头，浏览器只能看到 'fetch failed'；新增 Host 白名单封堵 DNS rebinding（默认无 token 部署下，用户浏览恶意页面即可被读走全部文档并改写 LLM base_url 窃取 API key）。

另修：不可逆迁移的 downgrade 由静默 pass 改为显式 raise（区分出 2 个纯数据修复迁移保留 no-op）、SSE 重连不再把已恢复的瞬时失败报为错误、前端接入 ESLint + react-hooks 规则（错误清零、警告棘轮锁 31）、打断 services.user_files 循环导入、coverage 数据首次有 HTTP 出口与界面展示。

三处推翻先前结论：M-1 实为 7 个而非 6 个 downgrade 且需分两类；M-3 经核实不成立，未加去重机制；自写的迁移策略测试曾用 ast.Expr 过滤误判 7 个真实 downgrade 为 no-op。

测试 575 -> 657（+82），关键修复均验证过先红后绿。遗留缺口：前端无测试框架，chatStream 行为修复无自动化回归；ESLint 15 条 exhaustive-deps 警告未清零（改 viewer 组件 effect 依赖有无限重渲染风险，另开任务）。

### Git Commits

| Hash | Message |
|------|---------|
| `267ae89` | (see git log) |
| `db2c86d` | (see git log) |
| `116ff0b` | (see git log) |
| `046d112` | (see git log) |
| `c27c56e` | (see git log) |
| `e1e1ccc` | (see git log) |
| `8fa1f58` | (see git log) |
| `a31158e` | (see git log) |
| `7b500a3` | (see git log) |

### Status

[OK] **Completed**
