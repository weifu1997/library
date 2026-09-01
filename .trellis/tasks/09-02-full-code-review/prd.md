# Full-repo code review (2026-09-02)

## Goal

Produce a graded review report plus a coverage manifest for `/home/huangwf/project/library` on branch `v4.0`. Review only; no product-code changes.

## Constraints

- Do not modify application source, tests, or docs except review artifacts under `.trellis/tasks/09-02-full-code-review/` and the session workspace.
- Old findings from `08-31-full-code-review` and `08-31-feature-code-review` are hypotheses until re-verified.
- High findings require a reproduced failure path or they are downgraded.
- Every table row needs `file:line` and a failure scenario.

## Acceptance

1. Baseline: ruff, pytest, frontend lint reported (dirty baseline called out).
2. Manifest: every in-scope file listed as reviewed / skipped with reason; report N / X / Y.
3. Graded table: High / Medium / Low with CONFIRMED vs PLAUSIBLE.
4. Old-ID verification: fixed / still present / never true.
5. Suggested spec additions.
