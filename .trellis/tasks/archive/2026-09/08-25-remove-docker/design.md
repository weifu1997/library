# Design — Remove Docker assets

## Boundary

This change touches **packaging, CI/CD, and docs only**. The backend has zero runtime coupling to Docker:

- `main.py` is a plain FastAPI app; `library serve` / `uvicorn library.main:app` runs it identically outside a container.
- No backend code imports or detects a container runtime (the grep for `docker/container/ghcr` in `src/` matched only a filename in a comment in `services/folders.py`).

So deletion is runtime-safe; the only "loss" is the containerized deploy/release path.

## What is removed

| Asset | Reason |
|---|---|
| `Dockerfile` | Only consumer is docker-build CI + release.yml compose build |
| `docker-compose.yml` | Dev stack (Postgres + MinIO + api + worker); not needed for local dev (SQLite + mirror storage are the defaults) |
| `.dockerignore` | Only meaningful to `docker build` |
| `.github/workflows/release.yml` | Entirely Docker publish (image → ghcr) + release-notes. No artifact ⇒ no workflow (user confirmed) |
| `ci.yml` `docker-build` job | Exists solely to catch Dockerfile rot; meaningless once Dockerfile is gone |

## What stays

- `.env.example` infra keys (`DB_BACKEND`, `POSTGRES_*`, `STORAGE_BACKEND`, `S3_*`): valid for bare-Python Postgres/S3 deployments; not docker-specific.
- Frontend `frontend/` Vite build: no docker coupling; untouched.
- `tests/test_propose_views_e2e.py`: "docker" is a content-topic fixture word (docker/devops/kubernetes) used to test topic classification — semantically required, excluded from grep.
- `scripts/` (UPSTREAM.md) and `alembic/`: no docker refs (verified), untouched.

## Doc text strategy

Where a doc presents a bare-Python path **and** a Docker path, drop the Docker path and keep the bare one. Where a doc's run instructions are Docker-only (README quickstart), replace with `uv sync` + `library serve` (or `uvicorn library.main:app`). Preserve surrounding structure.

## Residual docker text allowed (final grep exclusions)

- `tests/` — content-topic fixture words (docker/devops/kubernetes)
- `.trellis/tasks/*` — internal planning docs
- `conversation-*.zip` — untracked
- git history itself (not a shipped artifact)

## Rollback

All steps are `git rm` + text edits — `git restore --staged . && git restore .` reverts any phase. `release.yml` deletion only takes effect on push; restoring it from git history re-enables image publishing. No data/state touched.
