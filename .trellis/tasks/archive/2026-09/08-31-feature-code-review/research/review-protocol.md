# Review protocol (shared by all children)

Parent design: `.trellis/tasks/08-31-feature-code-review/design.md`.
This file is the jsonl-loadable copy of the protocol.

## This round is report-only

- Do not modify product code, tests, configs, OpenAPI, or frontend.
- Allowed writes: the child's `report.md` and files under that child's `research/`.
- `git status` for product paths must stay clean.

## Five angles (every child, every in-scope file)

1. **Correctness** — logic bugs, boundary cases, concurrency/transactions, error handling, resource leaks.
2. **Security** — authz on this surface, path traversal, injection, SSRF, secret leakage, untrusted input.
3. **Architecture / maintainability** — layer violations, duplication, oversized functions, dead code.
4. **Spec / contract** — `.trellis/spec/` conventions, naming, OpenAPI/frontend type agreement for this surface.
5. **Tests** — missing coverage, tests with no assertions, skipped tests, tautological tests.

A child may add extra angles (example: agent tool_use/tool_result pairing) but may not drop any of the five.

## Evidence rules

- Every finding needs `file:line`, a concrete failure scenario, and a suggested fix.
- "Already checked, no issue" must be explicit. Silence is not a pass.
- Do not treat internal manifests or trusted generated IDs as attacker-controlled without tracing the source.
- Do not flag documented intentional behavior as a bug.
- Budget ~35% false-positive rate; verify against the actual code before ranking Critical/High.

## Severity

- **Critical** — data loss, RCE, auth bypass, infinite loop/OOM in a default path.
- **High** — exploitable or user-visible correctness failure with a realistic trigger.
- **Medium** — real bug or contract hole with a narrower trigger, or silent degradation.
- **Low** — docs, dead code, log wrong number, maintainability that does not currently fail.

## Overlap

- Feature children own their routes / services / handlers / UI.
- `review-cross-cutting` owns process-wide auth, Host/CORS, storage backends, DB session/migrations/bootstrap, and leftover test gaps. It runs last and must not duplicate a finding already in another child's `report.md`; it may reference it.
- Worker child owns claim/retry/lifecycle/tend/runner. Feature-specific handlers (`ingest_file`, `webdav_publish`, `rebuild_semantic_index`, mining, …) belong to the feature child.
- Frontend Chat belongs to `review-agent-chat`. Settings page belongs to `review-settings`. Library / Search / Overview belong to `review-frontend-pages`.

## Report shape (`report.md`)

1. Coverage and method (what was line-read vs pattern-scanned).
2. Regression check of prior fixes in this child's scope.
3. Findings by severity.
4. Explicit "checked, no issue" list.
5. Test-gap list.
6. Suggested follow-up fix children (title + owning files + why). Do not create those tasks in this round.
