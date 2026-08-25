# Implement — Remove Docker assets

Ordered execution plan. Each phase ends with a validation gate. If a gate fails, stop and fix before continuing.

## Phase 0 — Baseline
- [ ] `uv run ruff check src tests` passes
- [ ] `uv run pytest tests/ -q` passes
- [ ] `git status` clean; branch `v4.0`

## Phase 1 — Delete files
1. `git rm Dockerfile docker-compose.yml .dockerignore .github/workflows/release.yml`

**Gate A**: `git status` shows only those 4 deletions; `ls .github/workflows/` → only `ci.yml`.

## Phase 2 — CI
1. `.github/workflows/ci.yml`: delete the `docker-build` job block and the header-comment line `#   4. docker-build ...`; renumber/trim the job list comment.
2. Check `.github/` for any other docker refs (e.g. `dependabot.yml` watching docker images) — clean if present.

**Gate B**: `grep -rniE "docker|ghcr" .github` → empty. YAML parses: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`.

## Phase 3 — Docs
1. `README.md` / `README.zh-CN.md` — replace the Docker quickstart (`echo LLM_DEFAULT_API_KEY=... > .env && docker compose up -d`) with a bare-Python path (`uv sync` + `library serve`); drop ghcr / docker-compose mentions elsewhere.
2. `USAGE.zh-CN.md`, `DESIGN.md`, `CHANGELOG.md` — remove docker mentions (CHANGELOG: purge historical entries too, per prd decision 4); add the removal note to the Unreleased section.
3. `docs/GUI_TUTORIAL.md` (~line 308 "or run it with Docker:"), `docs/GUI_TUTORIAL.zh-CN.md`, `docs/LAUNCH.md`, `docs/UPGRADE-PLAN.md`, `samples/architecture.md` — remove docker references.

**Gate C**: `grep -rniE "docker|ghcr|docker-compose" README.md README.zh-CN.md USAGE.zh-CN.md DESIGN.md CHANGELOG.md docs samples` → empty.

## Phase 4 — Source comment + final source grep
1. `src/library/services/folders.py` — reword the comment so it no longer names "Dockerfile" (e.g. `(LICENSE, package.json, .env)`), keeping the git-ambiguity-rule meaning.
2. `grep -rniE "docker|ghcr" frontend/src src .env.example` → empty.

**Gate D**: greps pass; `uv run ruff check src tests` → clean.

## Phase 5 — Full verification
1. `uv run ruff check src tests`
2. `uv run pytest tests/ -q`
3. `cd frontend && npm run lint && npm run build`
4. Smoke test: start backend (`library serve`, local `.env` supplies LLM key) and hit `/health`; confirm it boots.
5. `git status` / `git diff --stat` review — 4 deletions + doc/source edits only.

## Phase 6 — Spec update + commit
1. Check `.trellis/spec/*` for docker references; update if present (unlikely — generic guides).
2. Commit message: `Remove Docker assets and Docker release pipeline`.
3. Archive task via `task.py finish`.

## Rollback points
- After any phase: `git restore --staged . && git restore .` returns the tree to pre-change state (deleted files recoverable from git history).
- No behavioral runtime change; the only irreversible-in-effect step is pushing the `release.yml` deletion (restorable from history if ever needed).
