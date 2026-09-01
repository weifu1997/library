# Slice review protocol (read-only)

Active task: `.trellis/tasks/09-02-full-code-review`
Repo: `/home/huangwf/project/library` branch `v4.0`
Rule: **do not modify any product code, tests, docs, or configs**. Write only under
`.trellis/tasks/09-02-full-code-review/research/`.

## Output file

Write exactly one markdown file named as assigned (`slice-<name>-findings.md`).

## Required sections

1. **Coverage**
   - Reviewed files (every path from the slice list, marked `line-read` / `structural` / `skipped`)
   - Unreviewed files with reason
2. **Findings** (only rows with `file:line` AND a concrete failure scenario)
   - ID, severity (High/Medium/Low), confidence (CONFIRMED/PLAUSIBLE)
   - Defect, failure scenario, suggested fix direction, suggested test
3. **Old-ID re-check** for any overlapping prior IDs (treat as hypotheses)
4. **Cross-cutting ticks** (yes/no/n/a with one-line note): injection, TOCTOU, races, resource leaks, swallowed exceptions, live settings vs import freeze, N+1/unbounded read, secret logging, i18n, docs drift
5. **Clean areas** (explicitly checked, no issue) so later readers do not re-hunt

## Discipline

- No finding without file:line + failure scenario.
- Do not invent defense for impossible states.
- Old reports under `.trellis/tasks/archive/` are hypotheses until you re-read current code.
- High requires a reconstructed failure path; otherwise PLAUSIBLE or downgrade.
- Prefer current HEAD over 2026-08-31 reports.
- Vendor `src/library/vendor/headroom/**` is third-party-ish; still scan for injection / unbounded CPU if used on user data.
