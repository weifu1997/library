# Review report — 横切

Parent: `08-31-feature-code-review`. Report-only. No product code was modified.

This child runs last. Findings already owned by children 1–10 are **cited, not re-counted**.

---

## 0. Dedup against children 1–10

Do **not** treat these as new CROSS-* items:

| Owner | IDs |
|---|---|
| agent-chat | CHAT-H1, CHAT-H2, CHAT-M1–M3, AL-1, AL-2, CHAT-L* |
| ingest | INGEST-H1, AM-1, AM-2, INGEST-M1–M5, INGEST-L* |
| webdav | WEBDAV-H1–H3, WEBDAV-M1–M3, WEBDAV-L* |
| search | SEARCH-1–8 |
| upload | UPLOAD-1–6 |
| library-org | ORG-H1, ORG-M1–M2, ORG-L* |
| worker | WORKER-H1, WORKER-M1–M2, WORKER-L* |
| settings | SET-M1–M2, L-3 / SET-L* |
| access | ACCESS-M1–M3, ACCESS-L* |
| frontend-pages | FE-M1–M2, FE-L*, A-3 residual |

Compressed-archive RAM (CHAT-M3 / INGEST whole-blob) and zip-in-memory (UPLOAD-3 / ACCESS-M3) stay with those children. Path `..` in eval/MCP (ACCESS-M2) and `index_name=..` (SEARCH-3) stay there. Catalog cycle on WebDAV import is WEBDAV-H3.

---

## 1. Coverage and method

Line-read: `main.py` middleware/auth/CORS/Host/health; `db/session.py`; `storage/local.py` `_path`, `mirror.py` `_abs`, `sanitize.py`, `decompress.py` bomb/zip-slip; `provider_http.py` `provider_clients.py`; alembic `downgrade()` of 0002–0005, 0008, 0012–0014. Structural: `bootstrap.py` (two schema authorities — architecture audit), `capacity.py` `model_rate_limit.py`, `http_headers.py`.

`uv run ruff check src tests scripts` → **All checks passed**.

---

## 2. Regression (fixed items)

| ID | Status | Evidence |
|---|---|---|
| **H-1** CORS innermost | **Still fixed** | CORS registered last (`main.py:390-416`); comment + `test_cors_middleware_order_unit.py`. |
| **M-5** CORS origins hardcoded | **Still fixed** | `_cors_origins` reads `library_cors_origins` (`:227-238`), default Vite ports. |
| **H-2** Host allowlist | **Still present** | `host_allowlist` (`:353-387`); loopback + `LIBRARY_API_HOST` + `LIBRARY_TRUSTED_HOSTS`; `*` disables; `test_host_allowlist_unit.py`. Residual: empty Host — CROSS-M1. |
| **M-1** silent `downgrade()` | **Still fixed** for the schema-changing ones named in the original report | `0003`/`0005`/`0014`/`0002`/`0012` raise `NotImplementedError`. `0004`/`0013` are data-only no-ops with comments (not schema drift). Additive index migrations (`0008` etc.) have real DROP INDEX downgrades. `test_migration_downgrade_policy_unit.py`. |

---

## 3. Re-verify still-open (prior)

### M-4 — `get_session` vs `session_scope` rollback

**Still true (docs/contract, not a leak).**

`session_scope` (`session.py:12-20`) `except: rollback; raise`. `get_session` (`:23-27`) only `async with factory(): yield`. Close-on-exit still rolls back an uncommitted transaction in SQLAlchemy 2. No evidence of committed-on-error. Keep as **CROSS-L1** (document the contract in `database-guidelines.md`, which is still a stub).

### L-1 — non-ASCII `LIBRARY_API_TOKEN` → TypeError

**Still true.** `compare_digest(auth[len(prefix):], token)` (`main.py:255`) on `str` requires ASCII. `config.py:35` `library_api_token: str | None = None` has no ASCII validator. **CROSS-M2**.

### L-2 — `/health` unauthenticated build/deploy fields

**Still true.** `PUBLIC_PROBE_PATHS` includes `/health` (`:49`). Payload has `git_sha`, `build_id`, `environment`, `storage_backend` (`:440-450`). `/live` is the liveness probe. Host allowlist **exempts** probe paths (`:374-375`), so DNS-rebinding can still read `/health`. **CROSS-L2** (info leak, not data).

### A-2 — `except Exception` density

**Still true.** `src/library` still has **199** `except Exception` (same order as the first scan). Concrete swallows belong to feature children (INGEST-H1 contrast, mine_relations ORG-L2, etc.). No new CROSS finding per swallow.

---

## 4. New findings (this child only)

### Critical

None.

### High

None new. Default no-token + loopback is mitigated by Host allowlist (H-2). Non-loopback without token still warns (`_warn_if_unauthenticated_bind`). `LIBRARY_TRUSTED_HOSTS=*` turns the guard off — operator choice.

### Medium

#### CROSS-M1 — Empty `Host` header skips the allowlist

- **Where:** `main.py:376-377` `if host and host not in trusted`. Empty/`Host` missing → `host == ""` → condition false → request proceeds.
- **Failure scenario:** HTTP/1.0 or a client that omits `Host` (curl `--http1.0`, some health scanners, HTTP/2 edge cases after a bad proxy). DNS-rebinding browsers always send Host, so this is **not** a rebinding bypass. It is an unauthenticated loopback API with no Host check for non-browser clients on the same machine / mis-proxied traffic.
- **Suggested fix:** If `trusted is not None` and Host is missing/empty, 421. Keep probe-path exemption. Test: request without Host → 421.

#### CROSS-M2 — L-1 re-verified: non-ASCII token crashes every request

- **Where:** `main.py:255` `compare_digest` on two `str`s; no config validator.
- **Failure scenario:** User sets `LIBRARY_API_TOKEN=令牌` or includes emoji. Every authenticated path raises `TypeError` in middleware → 500, no 401. GUI shows fetch failed.
- **Suggested fix:** Validate ASCII in `config.py`, or `compare_digest(a.encode(), b.encode())` after normalizing. Test: non-ASCII token → 401 or startup ValidationError, never 500.

### Low

#### CROSS-L1 — M-4 session rollback contract undocumented

- **Where:** `db/session.py`. Spec `database-guidelines.md` is still “To fill” except the `parent_id` cycle section.
- **Suggested fix:** One paragraph: FastAPI `get_session` relies on `AsyncSession.close()` rollback; background work uses `session_scope`.

#### CROSS-L2 — L-2 `/health` still public

- **Where:** `main.py:440-450`.
- **Suggested fix:** Move identity fields to `/v1/stats` or require token when `LIBRARY_API_TOKEN` is set. Keep `/live` empty.

#### CROSS-L3 — `0.0.0.0` is in `LOCAL_HOST_NAMES`

- **Where:** `main.py:307`. A request with `Host: 0.0.0.0` is accepted. Unusual, not a typical rebinding name.
- **Suggested fix:** Drop `0.0.0.0` from the allowlist (bind address ≠ Host).

---

## 5. Checked, no issue (this surface)

- **Path traversal (storage):** `LocalStorage._path` and `MirrorStorage._abs` resolve + `relative_to(root)`. Absolute keys rejected.
- **Zip slip / bomb:** `decompress.py` `..` / absolute / drive-letter → `unsafe_basenames`; post-extract 200 MB cap; tempdir `rmtree` in `finally` (ingest/agent already cited).
- **Header injection:** `http_headers.py:25` `quote(name, safe='')`.
- **Provider HTTP:** shared client timeout 60s (`provider_clients.py:13,37`). `raise_for_provider_status` truncates error bodies to 2000 chars. Outbound URL is admin `base_url` (settings), not request path — SSRF is “user configured the provider,” not an unauthenticated injector.
- **S3 keys** are object names, not filesystem paths; no `../` resolve. Endpoint is settings.
- **Ruff** clean on `src tests scripts`.
- **Skips:** 6 `pytest.skip` (FTS5 trigram ×5, rar CLI ×1). No assertion-free tests found in this pass beyond what children already listed.

---

## 6. Test-gap rollup (unclaimed only)

Feature children already listed their own gaps. Left for this child:

| Gap | Why |
|---|---|
| Request with empty/missing `Host` | CROSS-M1 |
| Non-ASCII `LIBRARY_API_TOKEN` | CROSS-M2 |
| `get_session` exception path documented/tested vs `session_scope` | CROSS-L1 |
| `/health` vs `/live` field split | CROSS-L2 |
| No frontend test runner | FE child; still the largest **cross-cutting** quality hole |

---

## 7. Suggested follow-up fix children

Do **not** create these in this round.

| Title | Files | Why |
|---|---|---|
| Reject missing Host when allowlist is on | `main.py` host_allowlist | CROSS-M1 |
| ASCII-safe API token compare | `main.py`, `config.py` | CROSS-M2 / L-1 |
| Document get_session rollback | `db/session.py`, `database-guidelines.md` | CROSS-L1 |
| Shrink `/health` when token is set | `main.py` | CROSS-L2 |

---

## 8. Five-angle conclusions

| Angle | Conclusion |
|---|---|
| **Correctness** | CORS order, Host allowlist, irreversible migration policy hold. Session rollback is implicit on close (M-4). Empty Host is a hole (CROSS-M1). |
| **Security** | Rebinding is blocked when Host is present. Non-ASCII token 500s the API (CROSS-M2). Storage path + zip-slip remain solid. Default no-token is still the product default; Host is the compensating control. |
| **Architecture** | Middleware stack documented. Bootstrap vs Alembic dual schema authority unchanged (architecture-audit task). 199 `except Exception` still a debt pile (A-2). |
| **Spec / contract** | Cycle contract is in `database-guidelines.md`; session/migration contracts are not. OpenAPI `dict[str, Any]` leftovers owned by frontend/settings. |
| **Tests** | CORS/Host/downgrade unit tests exist. Empty Host and non-ASCII token do not. Frontend still has no runner. |

---

## Verification

```
git status --short -- src tests frontend openapi
# clean

uv run ruff check src tests scripts
# All checks passed
```
