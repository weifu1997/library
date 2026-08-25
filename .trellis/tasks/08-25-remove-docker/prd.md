# 移除项目 Docker 相关资产（瘦身）

## Goal

Remove every Docker artifact from the shipped project — build files (`Dockerfile`, `docker-compose.yml`, `.dockerignore`), the CI docker-build job, and the entire Docker release pipeline (`release.yml`) — and clean docker references from docs. Backend remains fully runnable via bare Python (`library serve` / `uvicorn library.main:app`), paving the way for git-based server deployment.

Decisions confirmed with the user:

1. **Delete `release.yml` entirely** — no more ghcr.io image publishing, no auto GitHub Release. (User picked "删除整个 release.yml".)
2. **`conversation-*.zip` not in scope** — untracked local files, not part of the repo.
3. **`.env.example` infra config stays** — `DB_BACKEND` / `POSTGRES_*` / `STORAGE_BACKEND` / `S3_*` are generic backend config that also work with bare-Python Postgres/S3; not docker-specific.
4. **CHANGELOG purged of docker mentions** — consistent with the remove-desktop precedent (thorough cleanup).
5. **`tests/test_propose_views_e2e.py` "docker" keyword kept** — it's a content-topic fixture (docker/devops/kubernetes), not infra; excluded from the final grep.

## Requirements

### Remove (delete files)
- `Dockerfile` (multi-stage backend image)
- `docker-compose.yml` (api + worker + Postgres + MinIO dev stack)
- `.dockerignore`
- `.github/workflows/release.yml` (entire workflow: lock-check, multi-arch docker build→ghcr, publish-release)

### Modify
- `.github/workflows/ci.yml` — remove the `docker-build` job (header comment line "4. docker-build" + job block) so PR CI no longer builds the Dockerfile
- `src/library/services/folders.py` — reword a comment that names "Dockerfile" as an example filename (cosmetic; keeps the final grep clean)
- Docs (10 files): remove docker / docker-compose / ghcr mentions, replacing the docker run path with the bare-Python path where the doc gives both:
  - `README.md`, `README.zh-CN.md` — replace the `docker compose up` quickstart with `uv sync` / `library serve`
  - `USAGE.zh-CN.md` (English `USAGE.md` already has no docker refs)
  - `DESIGN.md`, `CHANGELOG.md` (purge historical mentions too)
  - `docs/GUI_TUTORIAL.md` (line ~308 "or run it with Docker:"), `docs/GUI_TUTORIAL.zh-CN.md`, `docs/LAUNCH.md`, `docs/UPGRADE-PLAN.md`, `samples/architecture.md`

### Explicitly NOT modified
- `.env.example` config keys (generic, non-docker)
- `tests/test_propose_views_e2e.py` (content fixtures)
- `.trellis/tasks/*` internal planning docs (incl. this task)
- `alembic/` migrations, `CHANGELOG.md`→ only docker mentions removed, historical structure kept
- `conversation-*.zip` (untracked)

## Acceptance Criteria

- [ ] `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.github/workflows/release.yml` deleted from git
- [ ] `.github/workflows/ci.yml` has no `docker-build` job or docker step; header comment updated
- [ ] `grep -rniE "docker|ghcr|docker-compose" README.md README.zh-CN.md USAGE.zh-CN.md DESIGN.md CHANGELOG.md docs samples .github` → **no matches**
- [ ] `grep -rniE "docker|ghcr" frontend/src src .env.example` → **no matches** (after `folders.py` comment reword)
- [ ] Backend unaffected: `uv run ruff check src tests` passes; `uv run pytest tests/ -q` passes
- [ ] Frontend unaffected: `cd frontend && npm run lint && npm run build` passes
- [ ] No functional regression: backend starts via `library serve` (or `uvicorn library.main:app`), `/health` responds

## Notes

- The backend has **no runtime code dependency** on Docker — the same app runs via `library serve` / uvicorn; removal is runtime-safe.
- Removing `release.yml` means future version tags no longer produce a ghcr.io image. Server deploys switch to git-based (`git fetch && git checkout <branch>` then build/run).
- This is a complex task → has `design.md` + `implement.md`.
