# Library skills

Three workflow-oriented skills for any LLM that drives the Library
CLI (Claude Code, Cursor, pi, etc.). Skills are progressive-disclosure
instructions — the agent loads the relevant one when the user's intent
matches the description. Each skill declares `allowed-tools` and
`compatibility` in its frontmatter, per the Agent Skills standard.

## Layout

```
skills/
├── ingest-vault/SKILL.md           # bulk-load files into the db
├── research-with-library/SKILL.md  # ask, follow citations, export
└── discover-and-curate/SKILL.md    # explore relations, build lists
```

## Installing into Claude Code / pi

Either copy or symlink each directory into your agent's skills root:

```bash
# Linux/macOS — Claude Code
ln -s "$(pwd)/skills/ingest-vault" ~/.claude/skills/ingest-vault

# pi
ln -s "$(pwd)/skills/ingest-vault" ~/.pi/agent/skills/ingest-vault

# Windows (run as administrator for symlinks, or just copy the folder)
mklink /D "%USERPROFILE%\.claude\skills\ingest-vault" "%CD%\skills\ingest-vault"
```

Then re-launch the agent so it picks up the new skill descriptions.

## Skills and MCP

These skills drive the existing CLI — they don't expose new tools.
That keeps the surface tiny: each skill is one markdown file the agent
reads when relevant. MCP is available for clients that prefer structured
tool calls: it exposes workflow tools for asking Library, upload,
download, export, search, and metadata reads.

## Backend discovery

Skills should invoke the `library` CLI and let it find the backend. The CLI
uses this order:

1. explicit `--server URL`
2. `LIBRARY_SERVER`
3. `LIBRARY_HOME/runtime/server.json` written by `library serve`, after a
   `/health` check
4. embedded in-process backend if nothing is running

Do not hard-code the port in a skill. `.env` can pin `LIBRARY_API_PORT`, but
runtime state still comes from `runtime/server.json`.

The MCP server follows the same order. If no running backend is discovered, it
starts an embedded backend in the MCP process, matching the CLI fallback.

## One-shot commands

Each skill includes a **One-shot commands** section listing the equivalent
`library ...` invocations that an external agent can run via `bash`
without entering the REPL. Use `--json` for machine-parseable output.
