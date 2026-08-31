# Prior findings (regression vs still-open)

Source: archived `08-31-full-code-review` and `08-31-audit-agent-runtime` (branch `v4.0` @ `a35f654`, then 10 fix children).
This file is evidence for the new review. Do not re-open a **fixed** item as a new finding unless the fix is incomplete or has regressed.

## Fixed — regression check only

| ID | Topic | Fix child | Owning review child |
|---|---|---|---|
| H-1 | CORS middleware innermost; 401/413 lose CORS headers | `08-31-fix-cors-middleware-order` | `review-cross-cutting` |
| M-5 | CORS origins hardcoded to Vite ports | `08-31-fix-cors-middleware-order` | `review-cross-cutting` |
| H-2 | No Host allowlist; DNS rebinding on default no-token | `08-31-add-host-allowlist` | `review-cross-cutting` |
| M-1 | Irreversible Alembic `downgrade()` was silent `pass` | `08-31-harden-migration-downgrades` | `review-cross-cutting` |
| M-2 / M-3 / L-5 / L-6 | SSE reconnect false errors, missing cursor dedupe, abort listener leak, body not cancelled | `08-31-fix-chat-stream-resume` | `review-agent-chat` |
| A-3 | Frontend lint script was tsc-only; no react-hooks | `08-31-frontend-eslint-baseline` | `review-frontend-pages` |
| AH-1 | WebDAV import could create folder cycles; `_folder_path` infinite loop | `08-31-fix-folder-cycle-guard` | `review-webdav` |
| AH-2 | PDF OCR per-page failure swallowed; file marked success | `08-31-fix-ocr-partial-failure` | `review-ingest-pipelines` |
| — | Frontend ingest coverage / partial-failure surface | `08-31-frontend-coverage-surface` | `review-frontend-pages` |
| — | `user_files` import cycle | `08-31-break-user-files-import-cycle` | `review-upload-scan-sync` |

Regression check means: confirm the fix is still present, tests still exist, and the original failure scenario no longer holds. If it still holds, file it as a **regression** with a pointer to the old ID. Do not create a duplicate "new" finding.

## Previously reported, not known to be fixed

Re-verify in the owning child. If still true, include in that child's `report.md` (same ID prefix allowed).

| ID | Topic | Owning review child |
|---|---|---|
| M-4 | `get_session` vs `session_scope` rollback contract mismatch | `review-cross-cutting` |
| L-1 | `hmac.compare_digest` TypeError on non-ASCII token | `review-cross-cutting` |
| L-2 | `/health` unauthenticated build/deploy fields | `review-cross-cutting` |
| L-3 | `_mask` leaks API key prefix/suffix | `review-settings` |
| L-4 | `claim_pending_ids` docstring undersells CAS safety | `review-worker-tasks` |
| AM-1 | `OCR_MAX_PAGES` evaluated at import; GUI change needs restart | `review-ingest-pipelines` |
| AM-2 | Each OCR batch re-parses the whole PDF | `review-ingest-pipelines` |
| AL-1 | `finish_research` `dup_prior` branch dead | `review-agent-chat` |
| AL-2 | Exhausted-turn log prints `max_execute_turns` not `max_total_turns` | `review-agent-chat` |
| A-1 | Oversized functions in runtime / webdav / pdf / semantic / settings | owning feature child |
| A-2 | 199 `except Exception`; ruff `BLE001` globally ignored | `review-cross-cutting` notes density; feature children own concrete swallows |
| — | OpenAPI responses typed `dict[str, Any]`; settings key drift | `review-frontend-pages` + `review-settings` |

## Honest coverage gaps from the prior scan

The prior parent review did **not** line-read most feature code. Prior "already checked, no issue" conclusions (path traversal, zip slip, SQL injection, secrets in logs) are **starting hypotheses**, not skip tickets. Feature children must re-check their own surface.
